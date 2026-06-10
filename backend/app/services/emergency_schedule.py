from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import TopicMastery
from app.models.emergency_schedule import (
    EmergencyStudySchedule,
    EmergencyStudyScheduleBlock,
    EmergencyStudyScheduleRevision,
)
from app.schemas.emergency_planning import EmergencyPlanRequest
from app.schemas.emergency_schedule import (
    EmergencyScheduleBlockRead,
    EmergencyScheduleCompleteBlockRequest,
    EmergencyScheduleCreateRequest,
    EmergencyScheduleRead,
    EmergencyScheduleRescheduleRequest,
    EmergencyScheduleRevisionRead,
    EmergencyScheduleSkipBlockRequest,
)
from app.services.emergency_planning import (
    _load_topics,
    _next_mastery,
    build_emergency_plan,
)

_MASTERY_BASIS_CURRENT = "current-evidence-v1"
_MASTERY_BASIS_PROJECTED = "current-evidence+completed-study-projection-v1"


class EmergencyScheduleNotFoundError(RuntimeError):
    pass


class EmergencyScheduleConflictError(RuntimeError):
    pass


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _now() -> datetime:
    return datetime.now(UTC)


def _current_wall_minutes(schedule: EmergencyStudySchedule, now: datetime) -> int | None:
    if schedule.exam_deadline_at is None:
        return None
    deadline = _utc(schedule.exam_deadline_at)
    return max(0, int((deadline - now).total_seconds() // 60))


def _completed_minutes(db: Session, schedule_id: str) -> int:
    rows = list(
        db.scalars(
            select(EmergencyStudyScheduleBlock).where(
                EmergencyStudyScheduleBlock.schedule_id == schedule_id,
                EmergencyStudyScheduleBlock.status == "completed",
            )
        ).all()
    )
    return sum(row.actual_minutes or 0 for row in rows)


def _remaining_minutes(
    db: Session,
    schedule: EmergencyStudySchedule,
    *,
    now: datetime,
) -> int:
    budget_remaining = max(
        0,
        schedule.initial_available_minutes
        - _completed_minutes(db, schedule.id)
        - schedule.lost_minutes,
    )
    wall_remaining = _current_wall_minutes(schedule, now)
    if wall_remaining is not None:
        budget_remaining = min(budget_remaining, wall_remaining)
    return budget_remaining


def _current_blocks(
    db: Session,
    schedule: EmergencyStudySchedule,
) -> list[EmergencyStudyScheduleBlock]:
    return list(
        db.scalars(
            select(EmergencyStudyScheduleBlock)
            .where(
                EmergencyStudyScheduleBlock.schedule_id == schedule.id,
                EmergencyStudyScheduleBlock.revision == schedule.current_revision,
            )
            .order_by(EmergencyStudyScheduleBlock.sequence)
        ).all()
    )


def _get_schedule(
    db: Session,
    course_id: str,
    schedule_id: str,
) -> EmergencyStudySchedule:
    schedule = db.get(EmergencyStudySchedule, schedule_id)
    if schedule is None or schedule.course_id != course_id:
        raise EmergencyScheduleNotFoundError("Emergency study schedule not found")
    return schedule


def _get_current_block(
    db: Session,
    schedule: EmergencyStudySchedule,
    block_id: str,
) -> EmergencyStudyScheduleBlock:
    block = db.get(EmergencyStudyScheduleBlock, block_id)
    if (
        block is None
        or block.schedule_id != schedule.id
        or block.revision != schedule.current_revision
    ):
        raise EmergencyScheduleNotFoundError("Current emergency study block not found")
    return block


def _hours_until_exam(schedule: EmergencyStudySchedule, now: datetime) -> float | None:
    if schedule.exam_deadline_at is None:
        return None
    return max(0.0, (_utc(schedule.exam_deadline_at) - now).total_seconds() / 3600.0)


def _base_request(
    schedule: EmergencyStudySchedule,
    remaining_minutes: int,
    now: datetime,
    *,
    topic_mastery: dict[str, float] | None = None,
) -> EmergencyPlanRequest:
    return EmergencyPlanRequest(
        available_hours=remaining_minutes / 60.0,
        target_grade=schedule.target_grade,
        hours_until_exam=_hours_until_exam(schedule, now),
        block_minutes=schedule.block_minutes,
        skip_threshold_marks_per_hour=schedule.skip_threshold_marks_per_hour,
        baseline_mastery=schedule.baseline_mastery,
        topic_mastery=(
            topic_mastery
            if topic_mastery is not None
            else dict(schedule.topic_mastery_overrides)
        ),
        use_stored_mastery=schedule.use_stored_mastery,
    )


def _completed_blocks_by_topic(
    db: Session,
    schedule: EmergencyStudySchedule,
) -> dict[str, list[EmergencyStudyScheduleBlock]]:
    result: dict[str, list[EmergencyStudyScheduleBlock]] = {}
    rows = list(
        db.scalars(
            select(EmergencyStudyScheduleBlock).where(
                EmergencyStudyScheduleBlock.schedule_id == schedule.id,
                EmergencyStudyScheduleBlock.status == "completed",
                EmergencyStudyScheduleBlock.topic_id.is_not(None),
            )
        ).all()
    )
    for row in rows:
        if row.topic_id is not None:
            result.setdefault(row.topic_id, []).append(row)
    return result


def _projected_mastery_overrides(
    db: Session,
    course: Course,
    schedule: EmergencyStudySchedule,
    remaining_minutes: int,
    now: datetime,
) -> tuple[dict[str, float], str]:
    base_request = _base_request(schedule, remaining_minutes, now)
    topics, stored_mastery, _ = _load_topics(db, course, base_request)
    completed = _completed_blocks_by_topic(db, schedule)
    course_topics = {
        topic.id: topic
        for topic in db.scalars(
            select(CourseTopic).where(CourseTopic.course_id == course.id)
        ).all()
    }
    overrides = dict(schedule.topic_mastery_overrides)
    applied_projection = False

    for topic in topics:
        rows = completed.get(topic.id, [])
        if not rows:
            continue

        course_topic = course_topics.get(topic.id)
        explicit_override = topic.id in schedule.topic_mastery_overrides
        if course_topic is not None:
            explicit_override = explicit_override or (
                course_topic.normalized_name in schedule.topic_mastery_overrides
            )

        cutoff = _utc(schedule.created_at)
        mastery_row: TopicMastery | None = stored_mastery.get(topic.id)
        if (
            not explicit_override
            and schedule.use_stored_mastery
            and mastery_row is not None
            and _utc(mastery_row.updated_at) > cutoff
        ):
            cutoff = _utc(mastery_row.updated_at)

        minutes = sum(
            row.actual_minutes or 0
            for row in rows
            if row.completed_at is not None and _utc(row.completed_at) > cutoff
        )
        if minutes <= 0:
            continue

        overrides[topic.id] = _next_mastery(
            topic.mastery,
            minutes / 60.0,
            topic.learning_scale_hours,
        )
        applied_projection = True

    return (
        overrides,
        _MASTERY_BASIS_PROJECTED if applied_projection else _MASTERY_BASIS_CURRENT,
    )


def _supersede_unfinished(db: Session, schedule: EmergencyStudySchedule) -> None:
    for block in _current_blocks(db, schedule):
        if block.status in {"planned", "in_progress"}:
            block.status = "superseded"


def _persist_revision(
    db: Session,
    schedule: EmergencyStudySchedule,
    *,
    reason: str,
    remaining_minutes: int,
    plan,
    mastery_basis: str,
    revision: int,
) -> None:
    db.add(
        EmergencyStudyScheduleRevision(
            schedule_id=schedule.id,
            revision=revision,
            reason=reason,
            remaining_minutes=remaining_minutes,
            current_estimated_grade=plan.current_estimated_grade,
            projected_grade=plan.projected_grade,
            expected_mark_gain=plan.expected_mark_gain,
            target_gap_after=plan.target_gap_after,
            mastery_basis=mastery_basis,
        )
    )
    for block in plan.schedule:
        db.add(
            EmergencyStudyScheduleBlock(
                schedule_id=schedule.id,
                topic_id=block.topic_id,
                topic_name=block.topic_name,
                revision=revision,
                sequence=block.sequence,
                status="planned",
                planned_minutes=block.duration_minutes,
                starting_mastery=block.starting_mastery,
                ending_mastery=block.ending_mastery,
                expected_mark_gain=block.expected_mark_gain,
                expected_marks_per_hour=block.expected_marks_per_hour,
            )
        )


def _finish_if_no_time(
    db: Session,
    schedule: EmergencyStudySchedule,
    *,
    remaining_minutes: int,
    now: datetime,
) -> bool:
    schedule.remaining_available_minutes = remaining_minutes
    schedule.updated_at = now
    if remaining_minutes > 0:
        return False
    _supersede_unfinished(db, schedule)
    schedule.status = "completed"
    schedule.completed_at = now
    db.commit()
    return True


def _reschedule(
    db: Session,
    course: Course,
    schedule: EmergencyStudySchedule,
    *,
    reason: str,
    remaining_cap: int | None = None,
) -> EmergencyStudySchedule:
    if schedule.status != "active":
        raise EmergencyScheduleConflictError("Emergency study schedule is already completed")

    now = _now()
    remaining = _remaining_minutes(db, schedule, now=now)
    if remaining_cap is not None:
        if remaining_cap > remaining:
            raise EmergencyScheduleConflictError(
                "remaining_available_minutes cannot increase the remaining study budget"
            )
        schedule.lost_minutes += remaining - remaining_cap
        remaining = remaining_cap

    if _finish_if_no_time(db, schedule, remaining_minutes=remaining, now=now):
        return schedule

    overrides, mastery_basis = _projected_mastery_overrides(
        db,
        course,
        schedule,
        remaining,
        now,
    )
    request = _base_request(
        schedule,
        remaining,
        now,
        topic_mastery=overrides,
    )
    plan = build_emergency_plan(db, course, request)

    _supersede_unfinished(db, schedule)
    revision = schedule.current_revision + 1
    schedule.current_revision = revision
    schedule.remaining_available_minutes = remaining
    schedule.updated_at = now
    _persist_revision(
        db,
        schedule,
        reason=reason,
        remaining_minutes=remaining,
        plan=plan,
        mastery_basis=mastery_basis,
        revision=revision,
    )
    db.commit()
    db.refresh(schedule)
    return schedule


def create_emergency_schedule(
    db: Session,
    course: Course,
    payload: EmergencyScheduleCreateRequest,
) -> EmergencyStudySchedule:
    plan = build_emergency_plan(db, course, EmergencyPlanRequest(**payload.model_dump()))
    now = _now()
    exam_deadline = (
        now + timedelta(hours=payload.hours_until_exam)
        if payload.hours_until_exam is not None
        else None
    )
    initial_minutes = round(payload.available_hours * 60)
    schedule = EmergencyStudySchedule(
        course_id=course.id,
        status="active",
        target_grade=plan.target_grade,
        max_grade=plan.max_grade,
        initial_available_minutes=initial_minutes,
        remaining_available_minutes=initial_minutes,
        lost_minutes=0,
        block_minutes=payload.block_minutes,
        skip_threshold_marks_per_hour=payload.skip_threshold_marks_per_hour,
        baseline_mastery=payload.baseline_mastery,
        topic_mastery_overrides=dict(payload.topic_mastery),
        use_stored_mastery=payload.use_stored_mastery,
        exam_deadline_at=exam_deadline,
        current_revision=1,
        created_at=now,
        updated_at=now,
    )
    db.add(schedule)
    db.flush()
    _persist_revision(
        db,
        schedule,
        reason="initial",
        remaining_minutes=initial_minutes,
        plan=plan,
        mastery_basis=_MASTERY_BASIS_CURRENT,
        revision=1,
    )
    db.commit()
    db.refresh(schedule)
    return schedule


def start_schedule_block(
    db: Session,
    course_id: str,
    schedule_id: str,
    block_id: str,
) -> EmergencyStudySchedule:
    schedule = _get_schedule(db, course_id, schedule_id)
    if schedule.status != "active":
        raise EmergencyScheduleConflictError("Emergency study schedule is already completed")
    block = _get_current_block(db, schedule, block_id)
    if block.status != "planned":
        raise EmergencyScheduleConflictError("Only a planned block can be started")
    if any(item.status == "in_progress" for item in _current_blocks(db, schedule)):
        raise EmergencyScheduleConflictError("Another study block is already in progress")

    block.status = "in_progress"
    block.started_at = _now()
    schedule.updated_at = block.started_at
    db.commit()
    db.refresh(schedule)
    return schedule


def complete_schedule_block(
    db: Session,
    course: Course,
    schedule_id: str,
    block_id: str,
    payload: EmergencyScheduleCompleteBlockRequest,
) -> EmergencyStudySchedule:
    schedule = _get_schedule(db, course.id, schedule_id)
    if schedule.status != "active":
        raise EmergencyScheduleConflictError("Emergency study schedule is already completed")
    block = _get_current_block(db, schedule, block_id)
    if block.status not in {"planned", "in_progress"}:
        raise EmergencyScheduleConflictError("Only an unfinished current block can be completed")

    now = _now()
    block.status = "completed"
    block.actual_minutes = payload.actual_minutes
    block.note = payload.note
    block.completed_at = now
    if block.started_at is None:
        block.started_at = now
    db.flush()

    if payload.actual_minutes < block.planned_minutes:
        reason = "completed_early"
    elif payload.actual_minutes > block.planned_minutes:
        reason = "completed_late"
    else:
        reason = "completed_on_time"
    return _reschedule(db, course, schedule, reason=reason)


def skip_schedule_block(
    db: Session,
    course: Course,
    schedule_id: str,
    block_id: str,
    payload: EmergencyScheduleSkipBlockRequest,
) -> EmergencyStudySchedule:
    schedule = _get_schedule(db, course.id, schedule_id)
    if schedule.status != "active":
        raise EmergencyScheduleConflictError("Emergency study schedule is already completed")
    block = _get_current_block(db, schedule, block_id)
    if block.status not in {"planned", "in_progress"}:
        raise EmergencyScheduleConflictError("Only an unfinished current block can be skipped")

    now = _now()
    block.status = "skipped"
    block.actual_minutes = 0
    block.note = payload.note
    block.completed_at = now
    lost_minutes = payload.lost_minutes
    if lost_minutes is None:
        lost_minutes = block.planned_minutes
    schedule.lost_minutes += lost_minutes
    db.flush()
    return _reschedule(db, course, schedule, reason="missed_block")


def manually_reschedule(
    db: Session,
    course: Course,
    schedule_id: str,
    payload: EmergencyScheduleRescheduleRequest,
) -> EmergencyStudySchedule:
    schedule = _get_schedule(db, course.id, schedule_id)
    if any(item.status == "in_progress" for item in _current_blocks(db, schedule)):
        raise EmergencyScheduleConflictError(
            "Finish or skip the in-progress block before rescheduling"
        )
    return _reschedule(
        db,
        course,
        schedule,
        reason="manual_refresh",
        remaining_cap=payload.remaining_available_minutes,
    )


def _block_read(block: EmergencyStudyScheduleBlock) -> EmergencyScheduleBlockRead:
    return EmergencyScheduleBlockRead(
        id=block.id,
        revision=block.revision,
        sequence=block.sequence,
        topic_id=block.topic_id,
        topic_name=block.topic_name,
        status=block.status,
        planned_minutes=block.planned_minutes,
        actual_minutes=block.actual_minutes,
        starting_mastery=block.starting_mastery,
        ending_mastery=block.ending_mastery,
        expected_mark_gain=block.expected_mark_gain,
        expected_marks_per_hour=block.expected_marks_per_hour,
        note=block.note,
        started_at=block.started_at,
        completed_at=block.completed_at,
    )


def read_emergency_schedule(
    db: Session,
    course_id: str,
    schedule_id: str,
) -> EmergencyScheduleRead:
    schedule = _get_schedule(db, course_id, schedule_id)
    revision_rows = list(
        db.scalars(
            select(EmergencyStudyScheduleRevision)
            .where(EmergencyStudyScheduleRevision.schedule_id == schedule.id)
            .order_by(EmergencyStudyScheduleRevision.revision)
        ).all()
    )
    block_rows = list(
        db.scalars(
            select(EmergencyStudyScheduleBlock)
            .where(EmergencyStudyScheduleBlock.schedule_id == schedule.id)
            .order_by(
                EmergencyStudyScheduleBlock.revision,
                EmergencyStudyScheduleBlock.sequence,
            )
        ).all()
    )
    blocks_by_revision: dict[int, list[EmergencyStudyScheduleBlock]] = {}
    for block in block_rows:
        blocks_by_revision.setdefault(block.revision, []).append(block)

    current = blocks_by_revision.get(schedule.current_revision, [])
    next_block = next(
        (block for block in current if block.status in {"in_progress", "planned"}),
        None,
    )
    completed_minutes = sum(
        block.actual_minutes or 0 for block in block_rows if block.status == "completed"
    )

    return EmergencyScheduleRead(
        id=schedule.id,
        course_id=schedule.course_id,
        status=schedule.status,
        target_grade=schedule.target_grade,
        max_grade=schedule.max_grade,
        initial_available_minutes=schedule.initial_available_minutes,
        remaining_available_minutes=schedule.remaining_available_minutes,
        completed_study_minutes=completed_minutes,
        lost_minutes=schedule.lost_minutes,
        block_minutes=schedule.block_minutes,
        exam_deadline_at=schedule.exam_deadline_at,
        current_revision=schedule.current_revision,
        next_block_id=next_block.id if next_block is not None else None,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
        completed_at=schedule.completed_at,
        revisions=[
            EmergencyScheduleRevisionRead(
                revision=row.revision,
                reason=row.reason,
                remaining_minutes=row.remaining_minutes,
                current_estimated_grade=row.current_estimated_grade,
                projected_grade=row.projected_grade,
                expected_mark_gain=row.expected_mark_gain,
                target_gap_after=row.target_gap_after,
                mastery_basis=row.mastery_basis,
                created_at=row.created_at,
                blocks=[_block_read(block) for block in blocks_by_revision.get(row.revision, [])],
            )
            for row in revision_rows
        ],
    )
