from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.calendar_focus import FocusSession, SemesterCalendarPlan
from app.models.semester_queue import SemesterStudyQueue, SemesterStudyQueueBlock
from app.schemas.calendar_focus import (
    CalendarEventRead,
    CalendarPlanCreateRequest,
    CalendarPlanRead,
    FocusCompleteRequest,
    FocusSessionRead,
    FocusSkipRequest,
    FocusStartRequest,
)
from app.schemas.semester_queue import (
    SemesterQueueCompleteBlockRequest,
    SemesterQueueSkipBlockRequest,
)
from app.services.semester_queue import (
    SemesterQueueConflictError,
    SemesterQueueNotFoundError,
    complete_semester_block,
    read_semester_queue,
    skip_semester_block,
)


class CalendarFocusInputError(RuntimeError):
    pass


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _queue(db: Session, queue_id: str) -> SemesterStudyQueue:
    queue = db.get(SemesterStudyQueue, queue_id)
    if queue is None:
        raise SemesterQueueNotFoundError("Semester study queue not found")
    return queue


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


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise CalendarFocusInputError(f"Unknown timezone: {name}") from exc


def _resolve_start(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def _deadline_by_course(queue: SemesterStudyQueue) -> dict[str, datetime]:
    deadlines: dict[str, datetime] = {}
    for config in queue.course_configs:
        value = config.get("deadline_at")
        if value:
            deadlines[config["course_id"]] = _utc(datetime.fromisoformat(value))
    return deadlines


def create_calendar_plan(
    db: Session,
    queue_id: str,
    payload: CalendarPlanCreateRequest,
) -> SemesterCalendarPlan:
    read_semester_queue(db, queue_id)
    queue = _queue(db, queue_id)
    if queue.status != "active":
        raise SemesterQueueConflictError("Semester study queue is already completed")

    blocks = [
        block for block in _current_blocks(db, queue) if block.status in {"planned", "in_progress"}
    ]
    if not blocks:
        raise SemesterQueueConflictError("Semester study queue has no unfinished blocks")

    zone = _timezone(payload.timezone)
    cursor = _resolve_start(payload.start_at, zone)
    deadlines = _deadline_by_course(queue)
    events: list[CalendarEventRead] = []

    for block in blocks:
        if block.status == "in_progress" and block.started_at is not None:
            starts_at = _utc(block.started_at).astimezone(zone)
        else:
            starts_at = cursor
        ends_at = starts_at + timedelta(minutes=block.planned_minutes)

        deadline = deadlines.get(block.course_id or "")
        if deadline is not None and ends_at.astimezone(UTC) > deadline:
            raise SemesterQueueConflictError(
                f"Calendar plan would place {block.course_name} study after its exact exam deadline"
            )

        events.append(
            CalendarEventRead(
                uid=f"studyos-{queue.id}-{queue.current_revision}-{block.id}@studyos",
                block_id=block.id,
                sequence=block.sequence,
                course_id=block.course_id,
                course_name=block.course_name,
                topic_id=block.topic_id,
                topic_name=block.topic_name,
                planned_minutes=block.planned_minutes,
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )
        cursor = ends_at + timedelta(minutes=payload.break_minutes)

    row = SemesterCalendarPlan(
        queue_id=queue.id,
        revision=queue.current_revision,
        timezone=payload.timezone,
        start_at=events[0].starts_at,
        break_minutes=payload.break_minutes,
        event_count=len(events),
        events=[event.model_dump(mode="json") for event in events],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def read_calendar_plan(db: Session, row: SemesterCalendarPlan) -> CalendarPlanRead:
    queue = _queue(db, row.queue_id)
    return CalendarPlanRead(
        id=row.id,
        queue_id=row.queue_id,
        revision=row.revision,
        current_revision=queue.current_revision,
        status="current" if row.revision == queue.current_revision else "stale",
        timezone=row.timezone,
        start_at=row.start_at,
        break_minutes=row.break_minutes,
        event_count=row.event_count,
        events=[CalendarEventRead.model_validate(item) for item in row.events],
        created_at=row.created_at,
    )


def list_calendar_plans(db: Session, queue_id: str) -> list[CalendarPlanRead]:
    _queue(db, queue_id)
    rows = db.scalars(
        select(SemesterCalendarPlan)
        .where(SemesterCalendarPlan.queue_id == queue_id)
        .order_by(SemesterCalendarPlan.created_at.desc())
    ).all()
    return [read_calendar_plan(db, row) for row in rows]


def get_calendar_plan(db: Session, queue_id: str, plan_id: str) -> SemesterCalendarPlan:
    _queue(db, queue_id)
    row = db.get(SemesterCalendarPlan, plan_id)
    if row is None or row.queue_id != queue_id:
        raise SemesterQueueNotFoundError("Calendar plan not found")
    return row


def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _ics_timestamp(value: datetime) -> str:
    return _utc(value).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def calendar_plan_ics(row: SemesterCalendarPlan) -> str:
    events = [CalendarEventRead.model_validate(item) for item in row.events]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//StudyOS//Calendar Focus//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:StudyOS Study Plan",
    ]
    stamp = _ics_timestamp(row.created_at)
    for event in events:
        summary = _ics_escape(f"StudyOS: {event.course_name} — {event.topic_name}")
        description = _ics_escape(
            f"Queue {row.queue_id}; block {event.sequence}; planned {event.planned_minutes} minutes"
        )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event.uid}",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{_ics_timestamp(event.starts_at)}",
                f"DTEND:{_ics_timestamp(event.ends_at)}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _focus(db: Session, queue_id: str, session_id: str) -> FocusSession:
    _queue(db, queue_id)
    row = db.get(FocusSession, session_id)
    if row is None or row.queue_id != queue_id:
        raise SemesterQueueNotFoundError("Focus session not found")
    return row


def read_focus_session(row: FocusSession) -> FocusSessionRead:
    return FocusSessionRead(
        id=row.id,
        queue_id=row.queue_id,
        block_id=row.block_id,
        queue_revision=row.queue_revision,
        status=row.status,
        planned_minutes=row.planned_minutes,
        started_at=row.started_at,
        target_end_at=row.target_end_at,
        completed_at=row.completed_at,
        actual_minutes=row.actual_minutes,
        note=row.note,
    )


def list_focus_sessions(db: Session, queue_id: str) -> list[FocusSessionRead]:
    _queue(db, queue_id)
    rows = db.scalars(
        select(FocusSession)
        .where(FocusSession.queue_id == queue_id)
        .order_by(FocusSession.started_at.desc())
    ).all()
    return [read_focus_session(row) for row in rows]


def start_focus_session(
    db: Session,
    queue_id: str,
    payload: FocusStartRequest,
) -> FocusSession:
    read_semester_queue(db, queue_id)
    queue = _queue(db, queue_id)
    if queue.status != "active":
        raise SemesterQueueConflictError("Semester study queue is already completed")

    block = next(
        (
            item
            for item in _current_blocks(db, queue)
            if item.status in {"planned", "in_progress"}
        ),
        None,
    )
    if block is None:
        raise SemesterQueueConflictError("Semester study queue has no unfinished blocks")
    if payload.expected_block_id is not None and payload.expected_block_id != block.id:
        raise SemesterQueueConflictError("Expected focus block is no longer the next queue action")

    active = db.scalar(select(FocusSession).where(FocusSession.active_key == queue.id))
    if active is not None:
        if active.block_id == block.id:
            return active
        raise SemesterQueueConflictError("Another focus session is already active for this queue")

    now = datetime.now(UTC)
    if block.status == "planned":
        block.status = "in_progress"
        block.started_at = now
    started_at = _utc(block.started_at or now)
    queue.updated_at = now
    row = FocusSession(
        queue_id=queue.id,
        block_id=block.id,
        queue_revision=queue.current_revision,
        status="active",
        active_key=queue.id,
        planned_minutes=block.planned_minutes,
        started_at=started_at,
        target_end_at=started_at + timedelta(minutes=block.planned_minutes),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def complete_focus_session(
    db: Session,
    queue_id: str,
    session_id: str,
    payload: FocusCompleteRequest,
) -> tuple[FocusSession, SemesterStudyQueue]:
    row = _focus(db, queue_id, session_id)
    if row.status != "active":
        raise SemesterQueueConflictError("Only an active focus session can be completed")

    now = datetime.now(UTC)
    if payload.actual_minutes is None:
        elapsed_seconds = max(0.0, (now - _utc(row.started_at)).total_seconds())
        actual_minutes = max(1, min(720, round(elapsed_seconds / 60)))
    else:
        actual_minutes = payload.actual_minutes

    row.status = "completed"
    row.active_key = None
    row.completed_at = now
    row.actual_minutes = actual_minutes
    row.note = payload.note
    db.flush()
    queue = complete_semester_block(
        db,
        queue_id,
        row.block_id,
        SemesterQueueCompleteBlockRequest(actual_minutes=actual_minutes, note=payload.note),
    )
    db.refresh(row)
    return row, queue


def skip_focus_session(
    db: Session,
    queue_id: str,
    session_id: str,
    payload: FocusSkipRequest,
) -> tuple[FocusSession, SemesterStudyQueue]:
    row = _focus(db, queue_id, session_id)
    if row.status != "active":
        raise SemesterQueueConflictError("Only an active focus session can be skipped")

    now = datetime.now(UTC)
    row.status = "skipped"
    row.active_key = None
    row.completed_at = now
    row.actual_minutes = 0
    row.note = payload.note
    db.flush()
    queue = skip_semester_block(
        db,
        queue_id,
        row.block_id,
        SemesterQueueSkipBlockRequest(lost_minutes=payload.lost_minutes, note=payload.note),
    )
    db.refresh(row)
    return row, queue
