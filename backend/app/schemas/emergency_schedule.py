from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.emergency_planning import EmergencyPlanRequest


class EmergencyScheduleCreateRequest(EmergencyPlanRequest):
    pass


class EmergencyScheduleCompleteBlockRequest(BaseModel):
    actual_minutes: int = Field(ge=1, le=720)
    note: str | None = Field(default=None, max_length=500)


class EmergencyScheduleSkipBlockRequest(BaseModel):
    lost_minutes: int | None = Field(default=None, ge=0, le=720)
    note: str | None = Field(default=None, max_length=500)


class EmergencyScheduleRescheduleRequest(BaseModel):
    remaining_available_minutes: int | None = Field(default=None, ge=0, le=4320)
    note: str | None = Field(default=None, max_length=500)


class EmergencyScheduleBlockRead(BaseModel):
    id: str
    revision: int
    sequence: int
    topic_id: str | None
    topic_name: str
    status: Literal["planned", "in_progress", "completed", "skipped", "superseded"]
    planned_minutes: int
    actual_minutes: int | None
    starting_mastery: float
    ending_mastery: float
    expected_mark_gain: float
    expected_marks_per_hour: float
    note: str | None
    started_at: datetime | None
    completed_at: datetime | None


class EmergencyScheduleRevisionRead(BaseModel):
    revision: int
    reason: str
    remaining_minutes: int
    current_estimated_grade: float
    projected_grade: float
    expected_mark_gain: float
    target_gap_after: float
    mastery_basis: str
    created_at: datetime
    blocks: list[EmergencyScheduleBlockRead]


class EmergencyScheduleRead(BaseModel):
    id: str
    course_id: str
    status: Literal["active", "completed"]
    target_grade: float
    max_grade: float
    initial_available_minutes: int
    remaining_available_minutes: int
    completed_study_minutes: int
    lost_minutes: int
    block_minutes: int
    exam_deadline_at: datetime | None
    current_revision: int
    next_block_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    revisions: list[EmergencyScheduleRevisionRead]
