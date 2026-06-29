from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import TopicMastery
from app.models.semester_queue import (
    SemesterStudyQueue,
    SemesterStudyQueueBlock,
    SemesterStudyQueueRevision,
)
from app.schemas.emergency_planning import EmergencyPlanRequest
from app.schemas.multi_course_planning import MultiCourseCourseRequest, MultiCoursePlanRequest
from app.schemas.semester_queue import (
    SemesterQueueBlockRead,
    SemesterQueueCompleteBlockRequest,
    SemesterQueueCreateRequest,
    SemesterQueueRead,
    SemesterQueueRefreshRequest,
    SemesterQueueRevisionRead,
    SemesterQueueSkipBlockRequest,
)
from app.services.emergency_planning import _load_topics, _next_mastery
from app.services.multi_course_planning import build_multi_course_plan


class SemesterQueueNotFoundError(RuntimeError):
    pass


class SemesterQueueConflictError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _utc(datetime.fromisoformat(value))


def _completed_minutes(db: Session, queue_id: str) -> int:
    rows = db.scalars(
        select(SemesterStudyQueueBlock).where(
            SemesterStudyQueueBlock.queue_id == queue_id,
            SemesterStudyQueueBlock.status == "completed",
        )
    ).all()
    return sum(row.actual_minutes or 0 for row in rows)


def _remaining_minutes(db: Session, queue: SemesterStudyQueue) -> int:
    return max(
        0,
        queue.initial_available_minutes - _completed_minutes(db, queue.id) - queue.lost_minutes,
    )


def _current_blocks(db: Session, queue: SemesterStudyQueue) -> list[SemesterStudyQueueBlock]:
    return list(
        db.scalars(
            select(SemesterStudyQueueBlock)
            .where(
                SemesterStudyQueueBlock.queue_id == queue.id,
                SemesterStudyQueueBlock.revision == queue.current_revision,
            )
            .order_by(SemesterStudyQueueBlock.sequence)
        ).all()
    )


def _get_queue(db: Session, queue_id: str) -> SemesterStudyQueue:
    queue = db.get(SemesterStudyQueue, queue_id)
    if queue is None:
        raise SemesterQueueNotFoundError("Semester study queue not found")
    return queue


def _get_current_block(
    db: Session, queue: SemesterStudyQueue, block_id: str
) -> SemesterStudyQueueBlock:
    block = db.get(SemesterStudyQueueBlock, block_id)
    if block is None or block.queue_id != queue.id or block.revision != queue.current_revision:
        raise SemesterQueueNotFoundError("Current semester study block not found")
    return block


def _next_unfinished(db: Session, queue: SemesterStudyQueue) -> SemesterStudyQueueBlock | None:
    return next(
        (
            block
            for block in _current_blocks(db, queue)
            if block.status in {"planned", "in_progress"}
        ),
        None,
    )


def _assert_next_block(
    db: Session, queue: SemesterStudyQueue, block: SemesterStudyQueueBlock
) -> None:
    next_block = _next_unfinished(db, queue)
    if next_block is None or next_block.id != block.id:
        raise SemesterQueueConflictError("Blocks must be executed in queue order")


def _course_configs(payload: SemesterQueueCreateRequest, now: datetime) -> list[dict]:
    configs: list[dict] = []
    for item in payload.courses:
        values = item.model_dump()
        hours = values.pop("hours_until_exam")
        values["deadline_at"] = (
            (now + timedelta(hours=hours)).isoformat() if hours is not None else None
        )
        configs.append(values)
    return configs


def _completed_by_course_topic(
    db: Session, queue: SemesterStudyQueue
) -> dict[tuple[str, str], list[SemesterStudyQueueBlock]]:
    result: dict[tuple[str, str], list[SemesterStudyQueueBlock]] = {}
    rows = db.scalars(
        select(SemesterStudyQueueBlock).where(
            SemesterStudyQueueBlock.queue_id == queue.id,
            SemesterStudyQueueBlock.status == "completed",
            SemesterStudyQueueBlock.course_id.is_not(None),
            SemesterStudyQueueBlock.topic_id.is_not(None),
        )
    ).all()
    for row in rows:
        if row.course_id is not None and row.topic_id is not None:
            result.setdefault((row.course_id, row.topic_id), []).append(row)
    return result


def _projected_overrides(
    db: Session,
    queue: SemesterStudyQueue,
    config: dict,
    *,
    remaining_minutes: int,
    now: datetime,
    completed: dict[tuple[str, str], list[SemesterStudyQueueBlock]],
) -> dict[str, float]:
    course_id = config["course_id"]
    course = db.get(Course, course_id)
    if course is None:
        return dict(config["topic_mastery"])
    target = config["target_grade"] if config["target_grade"] is not None else course.target_grade
    request = EmergencyPlanRequest(
        available_hours=queue.block_minutes / 60,
        target_grade=target,
        hours_until_exam=None,
        block_minutes=queue.block_minutes,
        baseline_mastery=config["baseline_mastery"],
        topic_mastery=config["topic_mastery"],
        use_stored_mastery=config["use_stored_mastery"],
    )
    topics, stored_mastery, _ = _load_topics(db, course, request)
    course_topics = {
        topic.id: topic
        for topic in db.scalars(select(CourseTopic).where(CourseTopic.course_id == course_id)).all()
    }
    overrides = dict(config["topic_mastery"])
    for topic in topics:
        rows = completed.get((course_id, topic.id), [])
        if not rows:
            continue
        course_topic = course_topics.get(topic.id)
        explicit = topic.id in overrides or (
            course_topic is not None and course_topic.normalized_name in overrides
        )
        cutoff = _utc(queue.created_at)
        measured = stored_mastery.get(topic.id)
        if (
            not explicit
            and config["use_stored_mastery"]
            and measured is not None
            and _utc(measured.updated_at) > cutoff
        ):
            cutoff = _utc(measured.updated_at)
        minutes = sum(
            row.actual_minutes or 0
            for row in rows
            if row.completed_at is not None and _utc(row.completed_at) > cutoff
        )
        if minutes > 0:
            overrides[topic.id] = _next_mastery(
                topic.mastery, minutes / 60, topic.learning_scale_hours
            )
    return overrides


def _plan_request(
    db: Session,
    queue: SemesterStudyQueue,
    *,
    remaining_minutes: int,
    now: datetime,
) -> MultiCoursePlanRequest:
    completed = _completed_by_course_topic(db, queue)
    courses: list[MultiCourseCourseRequest] = []
    for config in queue.course_configs:
        deadline = _parse_datetime(config.get("deadline_at"))
        courses.append(
            MultiCourseCourseRequest(
                course_id=config["course_id"],
                target_grade=config["target_grade"],
                hours_until_exam=(
                    max(0.0, (deadline - now).total_seconds() / 3600)
                    if deadline is not None
                    else None
                ),
                baseline_mastery=config["baseline_mastery"],
                topic_mastery=_projected_overrides(
                    db,
                    queue,
                    config,
                    remaining_minutes=remaining_minutes,
                    now=now,
                    completed=completed,
                ),
                use_stored_mastery=config["use_stored_mastery"],
            )
        )
    return MultiCoursePlanRequest(
        available_hours=remaining_minutes / 60,
        block_minutes=queue.block_minutes,
        courses=courses,
    )


def _source_fingerprint(db: Session, queue: SemesterStudyQueue, now: datetime) -> dict:
    courses: list[dict] = []
    for config in queue.course_configs:
        course_id = config["course_id"]
        course = db.get(Course, course_id)
        mastery = list(
            db.scalars(
                select(TopicMastery)
                .where(TopicMastery.course_id == course_id)
                .order_by(TopicMastery.topic_id)
            ).all()
        )
        deadline = _parse_datetime(config.get("deadline_at"))
        courses.append(
            {
                "course_id": course_id,
                "course": (
                    None
                    if course is None
                    else {
                        "exam_date": course.exam_date.isoformat() if course.exam_date else None,
                        "target_grade": course.target_grade,
                        "max_grade": course.max_grade,
                    }
                ),
                "exact_deadline_slots": (
                    max(0, int((deadline - now).total_seconds() // 60))
                    // queue.block_minutes
                    if deadline is not None
                    else None
                ),
                "mastery": [
                    {
                        "topic_id": row.topic_id,
                        "mastery": row.mastery,
                        "confidence": row.confidence,
                        "evidence_weight": row.evidence_weight,
                        "updated_at": _utc(row.updated_at).isoformat(),
                    }
                    for row in mastery
                ],
            }
        )
    return {"courses": courses}


def _supersede_unfinished(db: Session, queue: SemesterStudyQueue) -> None:
    for block in _current_blocks(db, queue):
        if block.status in {"planned", "in_progress"}:
            block.status = "superseded"


def _persist_revision(
    db: Session,
    queue: SemesterStudyQueue,
    *,
    reason: str,
    plan,
    now: datetime,
) -> None:
    allocated_minutes = round(plan.allocated_hours * 60)
    db.add(
        SemesterStudyQueueRevision(
            queue_id=queue.id,
            revision=queue.current_revision,
            reason=reason,
            optimization_model=plan.optimization_model,
            remaining_minutes=queue.remaining_available_minutes,
            allocated_minutes=allocated_minutes,
            total_normalized_target_gap_before=plan.total_normalized_target_gap_before,
            total_normalized_target_gap_after=plan.total_normalized_target_gap_after,
            total_utility_score=plan.total_utility_score,
            course_results=[course.model_dump(mode="json") for course in plan.courses],
            source_fingerprint=_source_fingerprint(db, queue, now),
            created_at=now,
        )
    )
    for block in plan.schedule:
        db.add(
            SemesterStudyQueueBlock(
                queue_id=queue.id,
                course_id=block.course_id,
                course_name=block.course_name,
                topic_id=block.topic_id,
                topic_name=block.topic_name,
                revision=queue.current_revision,
                sequence=block.sequence,
                status="planned",
                planned_minutes=block.duration_minutes,
                expected_mark_gain=block.expected_mark_gain,
                normalized_target_gap_reduction=block.normalized_target_gap_reduction,
                utility_score=block.utility_score,
                created_at=now,
            )
        )


def _replan(
    db: Session,
    queue: SemesterStudyQueue,
    *,
    reason: str,
    remaining_cap: int | None = None,
) -> SemesterStudyQueue:
    if queue.status != "active":
        raise SemesterQueueConflictError("Semester study queue is already completed")
    if any(block.status == "in_progress" for block in _current_blocks(db, queue)):
        raise SemesterQueueConflictError("Finish or skip the in-progress block before refreshing")
    now = _now()
    remaining = _remaining_minutes(db, queue)
    if remaining_cap is not None:
        if remaining_cap > remaining:
            raise SemesterQueueConflictError(
                "remaining_available_minutes cannot increase the remaining study budget"
            )
        queue.lost_minutes += remaining - remaining_cap
        remaining = remaining_cap
    _supersede_unfinished(db, queue)
    queue.remaining_available_minutes = remaining
    queue.updated_at = now
    if remaining <= 0:
        queue.status = "completed"
        queue.completed_at = now
        db.commit()
        return queue

    plan = build_multi_course_plan(
        db, _plan_request(db, queue, remaining_minutes=remaining, now=now)
    )
    queue.current_revision += 1
    _persist_revision(db, queue, reason=reason, plan=plan, now=now)
    if not plan.schedule:
        queue.status = "completed"
        queue.completed_at = now
    db.commit()
    db.refresh(queue)
    return queue


def create_semester_queue(
    db: Session, payload: SemesterQueueCreateRequest
) -> SemesterStudyQueue:
    now = _now()
    plan = build_multi_course_plan(db, MultiCoursePlanRequest(**payload.model_dump()))
    initial_minutes = round(payload.available_hours * 60)
    queue = SemesterStudyQueue(
        user_id=db.info["user_id"],
        status="active" if plan.schedule else "completed",
        initial_available_minutes=initial_minutes,
        remaining_available_minutes=initial_minutes,
        lost_minutes=0,
        block_minutes=payload.block_minutes,
        course_configs=_course_configs(payload, now),
        current_revision=1,
        created_at=now,
        updated_at=now,
        completed_at=None if plan.schedule else now,
    )
    db.add(queue)
    db.flush()
    _persist_revision(db, queue, reason="initial", plan=plan, now=now)
    db.commit()
    db.refresh(queue)
    return queue


def start_semester_block(
    db: Session, queue_id: str, block_id: str
) -> SemesterStudyQueue:
    queue = _get_queue(db, queue_id)
    if queue.status != "active":
        raise SemesterQueueConflictError("Semester study queue is already completed")
    block = _get_current_block(db, queue, block_id)
    _assert_next_block(db, queue, block)
    if block.status != "planned":
        raise SemesterQueueConflictError("Only a planned block can be started")
    block.status = "in_progress"
    block.started_at = _now()
    queue.updated_at = block.started_at
    db.commit()
    db.refresh(queue)
    return queue


def complete_semester_block(
    db: Session,
    queue_id: str,
    block_id: str,
    payload: SemesterQueueCompleteBlockRequest,
) -> SemesterStudyQueue:
    queue = _get_queue(db, queue_id)
    if queue.status != "active":
        raise SemesterQueueConflictError("Semester study queue is already completed")
    block = _get_current_block(db, queue, block_id)
    _assert_next_block(db, queue, block)
    if block.status not in {"planned", "in_progress"}:
        raise SemesterQueueConflictError("Only an unfinished block can be completed")
    now = _now()
    block.status = "completed"
    block.actual_minutes = payload.actual_minutes
    block.note = payload.note
    block.started_at = block.started_at or now
    block.completed_at = now
    db.flush()
    if payload.actual_minutes < block.planned_minutes:
        reason = "completed_early"
    elif payload.actual_minutes > block.planned_minutes:
        reason = "completed_late"
    else:
        reason = "completed_on_time"
    return _replan(db, queue, reason=reason)


def skip_semester_block(
    db: Session,
    queue_id: str,
    block_id: str,
    payload: SemesterQueueSkipBlockRequest,
) -> SemesterStudyQueue:
    queue = _get_queue(db, queue_id)
    if queue.status != "active":
        raise SemesterQueueConflictError("Semester study queue is already completed")
    block = _get_current_block(db, queue, block_id)
    _assert_next_block(db, queue, block)
    if block.status not in {"planned", "in_progress"}:
        raise SemesterQueueConflictError("Only an unfinished block can be skipped")
    now = _now()
    block.status = "skipped"
    block.actual_minutes = 0
    block.note = payload.note
    block.completed_at = now
    queue.lost_minutes += (
        payload.lost_minutes if payload.lost_minutes is not None else block.planned_minutes
    )
    db.flush()
    return _replan(db, queue, reason="missed_block")


def refresh_semester_queue(
    db: Session, queue_id: str, payload: SemesterQueueRefreshRequest
) -> SemesterStudyQueue:
    return _replan(
        db,
        _get_queue(db, queue_id),
        reason="manual_refresh",
        remaining_cap=payload.remaining_available_minutes,
    )


def refresh_if_stale(db: Session, queue: SemesterStudyQueue) -> SemesterStudyQueue:
    if queue.status != "active" or any(
        block.status == "in_progress" for block in _current_blocks(db, queue)
    ):
        return queue
    revision = db.scalar(
        select(SemesterStudyQueueRevision).where(
            SemesterStudyQueueRevision.queue_id == queue.id,
            SemesterStudyQueueRevision.revision == queue.current_revision,
        )
    )
    if revision is not None and revision.source_fingerprint != _source_fingerprint(
        db, queue, _now()
    ):
        return _replan(db, queue, reason="source_change")
    return queue


def _block_read(block: SemesterStudyQueueBlock) -> SemesterQueueBlockRead:
    return SemesterQueueBlockRead(
        id=block.id,
        revision=block.revision,
        sequence=block.sequence,
        course_id=block.course_id,
        course_name=block.course_name,
        topic_id=block.topic_id,
        topic_name=block.topic_name,
        status=block.status,
        planned_minutes=block.planned_minutes,
        actual_minutes=block.actual_minutes,
        expected_mark_gain=block.expected_mark_gain,
        normalized_target_gap_reduction=block.normalized_target_gap_reduction,
        utility_score=block.utility_score,
        note=block.note,
        started_at=block.started_at,
        completed_at=block.completed_at,
    )


def read_semester_queue(
    db: Session, queue_id: str, *, auto_refresh: bool = True
) -> SemesterQueueRead:
    queue = _get_queue(db, queue_id)
    if auto_refresh:
        queue = refresh_if_stale(db, queue)
    revisions = list(
        db.scalars(
            select(SemesterStudyQueueRevision)
            .where(SemesterStudyQueueRevision.queue_id == queue.id)
            .order_by(SemesterStudyQueueRevision.revision)
        ).all()
    )
    blocks = list(
        db.scalars(
            select(SemesterStudyQueueBlock)
            .where(SemesterStudyQueueBlock.queue_id == queue.id)
            .order_by(SemesterStudyQueueBlock.revision, SemesterStudyQueueBlock.sequence)
        ).all()
    )
    by_revision: dict[int, list[SemesterStudyQueueBlock]] = {}
    for block in blocks:
        by_revision.setdefault(block.revision, []).append(block)
    next_block = _next_unfinished(db, queue) if queue.status == "active" else None
    return SemesterQueueRead(
        id=queue.id,
        status=queue.status,
        initial_available_minutes=queue.initial_available_minutes,
        remaining_available_minutes=queue.remaining_available_minutes,
        completed_study_minutes=_completed_minutes(db, queue.id),
        lost_minutes=queue.lost_minutes,
        block_minutes=queue.block_minutes,
        course_ids=[config["course_id"] for config in queue.course_configs],
        current_revision=queue.current_revision,
        next_block_id=next_block.id if next_block else None,
        created_at=queue.created_at,
        updated_at=queue.updated_at,
        completed_at=queue.completed_at,
        revisions=[
            SemesterQueueRevisionRead(
                revision=revision.revision,
                reason=revision.reason,
                optimization_model=revision.optimization_model,
                remaining_minutes=revision.remaining_minutes,
                allocated_minutes=revision.allocated_minutes,
                total_normalized_target_gap_before=(
                    revision.total_normalized_target_gap_before
                ),
                total_normalized_target_gap_after=revision.total_normalized_target_gap_after,
                total_utility_score=revision.total_utility_score,
                courses=revision.course_results,
                created_at=revision.created_at,
                blocks=[_block_read(block) for block in by_revision.get(revision.revision, [])],
            )
            for revision in revisions
        ],
    )
