from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import CalendarSubscription
from app.models.semester_queue import SemesterStudyQueue, SemesterStudyQueueBlock
from app.schemas.integrations import (
    CalendarSubscriptionCreated,
    CalendarSubscriptionRead,
)
from app.services.calendar_focus import (
    _deadline_by_course,
    _ics_escape,
    _ics_timestamp,
    _resolve_start,
    _timezone,
    _utc,
)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_calendar_subscription(
    db: Session,
    *,
    user_id: str,
    queue_id: str,
    timezone: str,
    start_at: datetime,
    break_minutes: int,
) -> tuple[CalendarSubscription, str]:
    queue = db.get(SemesterStudyQueue, queue_id)
    if queue is None:
        raise LookupError("Semester study queue not found")

    _timezone(timezone)
    token = secrets.token_urlsafe(36)
    row = CalendarSubscription(
        user_id=user_id,
        queue_id=queue_id,
        token_hash=_token_hash(token),
        timezone=timezone,
        start_at=start_at,
        break_minutes=break_minutes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, token


def read_calendar_subscription(row: CalendarSubscription) -> CalendarSubscriptionRead:
    return CalendarSubscriptionRead(
        id=row.id,
        queue_id=row.queue_id,
        timezone=row.timezone,
        start_at=row.start_at,
        break_minutes=row.break_minutes,
        active=row.revoked_at is None,
        created_at=row.created_at,
    )


def created_calendar_subscription(
    row: CalendarSubscription,
    token: str,
) -> CalendarSubscriptionCreated:
    base = read_calendar_subscription(row)
    return CalendarSubscriptionCreated(
        **base.model_dump(),
        feed_path=f"/calendar/{token}.ics",
    )


def find_calendar_subscription(
    db: Session,
    token: str,
) -> CalendarSubscription | None:
    return db.scalar(
        select(CalendarSubscription).where(
            CalendarSubscription.token_hash == _token_hash(token),
            CalendarSubscription.revoked_at.is_(None),
        )
    )


def revoke_calendar_subscription(db: Session, row: CalendarSubscription) -> None:
    row.revoked_at = datetime.now(UTC)
    db.commit()


def calendar_subscription_ics(
    db: Session,
    row: CalendarSubscription,
) -> str:
    db.info["user_id"] = row.user_id
    queue = db.get(SemesterStudyQueue, row.queue_id)
    if queue is None:
        raise LookupError("Semester study queue not found")

    blocks = list(
        db.scalars(
            select(SemesterStudyQueueBlock)
            .where(
                SemesterStudyQueueBlock.queue_id == queue.id,
                SemesterStudyQueueBlock.revision == queue.current_revision,
                SemesterStudyQueueBlock.status.in_(("planned", "in_progress")),
            )
            .order_by(SemesterStudyQueueBlock.sequence)
        ).all()
    )
    zone = _timezone(row.timezone)
    cursor = _resolve_start(row.start_at, zone)
    deadlines = _deadline_by_course(queue)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//StudyOS//Live Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:StudyOS Live Study Plan",
        f"X-WR-TIMEZONE:{_ics_escape(row.timezone)}",
    ]
    stamp = _ics_timestamp(row.created_at)

    for block in blocks:
        if block.status == "in_progress" and block.started_at is not None:
            starts_at = _utc(block.started_at).astimezone(zone)
        else:
            starts_at = cursor
        ends_at = starts_at + timedelta(minutes=block.planned_minutes)
        deadline = deadlines.get(block.course_id or "")
        if deadline is not None and ends_at.astimezone(UTC) > deadline:
            continue
        uid = f"studyos-live-{row.id}-{block.id}@studyos"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{_ics_timestamp(starts_at)}",
                f"DTEND:{_ics_timestamp(ends_at)}",
                (
                    "SUMMARY:"
                    + _ics_escape(f"StudyOS: {block.course_name} — {block.topic_name}")
                ),
                (
                    "DESCRIPTION:"
                    + _ics_escape(
                        f"Live queue block {block.sequence}; "
                        f"planned {block.planned_minutes} minutes"
                    )
                ),
                "END:VEVENT",
            ]
        )
        cursor = ends_at + timedelta(minutes=row.break_minutes)

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
