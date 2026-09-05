from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.semester_queue import SemesterQueueRead


class CalendarPlanCreateRequest(BaseModel):
    start_at: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    break_minutes: int = Field(default=5, ge=0, le=60)


class CalendarEventRead(BaseModel):
    uid: str
    block_id: str
    sequence: int
    course_id: str | None
    course_name: str
    topic_id: str | None
    topic_name: str
    planned_minutes: int
    starts_at: datetime
    ends_at: datetime


class CalendarPlanRead(BaseModel):
    id: str
    queue_id: str
    revision: int
    current_revision: int
    status: Literal["current", "stale"]
    timezone: str
    start_at: datetime
    break_minutes: int
    event_count: int
    events: list[CalendarEventRead]
    created_at: datetime


class FocusStartRequest(BaseModel):
    expected_block_id: str | None = None


class FocusCompleteRequest(BaseModel):
    actual_minutes: int | None = Field(default=None, ge=1, le=720)
    note: str | None = Field(default=None, max_length=500)


class FocusSkipRequest(BaseModel):
    lost_minutes: int | None = Field(default=None, ge=0, le=720)
    note: str | None = Field(default=None, max_length=500)


class FocusSessionRead(BaseModel):
    id: str
    queue_id: str
    block_id: str
    queue_revision: int
    status: Literal["active", "completed", "skipped"]
    planned_minutes: int
    started_at: datetime
    target_end_at: datetime
    completed_at: datetime | None
    actual_minutes: int | None
    note: str | None


class FocusActionRead(BaseModel):
    session: FocusSessionRead
    queue: SemesterQueueRead
