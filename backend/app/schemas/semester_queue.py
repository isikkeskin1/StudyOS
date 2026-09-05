from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.multi_course_planning import MultiCourseCourseRead, MultiCoursePlanRequest


class SemesterQueueCreateRequest(MultiCoursePlanRequest):
    pass


class SemesterQueueCompleteBlockRequest(BaseModel):
    actual_minutes: int = Field(ge=1, le=720)
    note: str | None = Field(default=None, max_length=500)


class SemesterQueueSkipBlockRequest(BaseModel):
    lost_minutes: int | None = Field(default=None, ge=0, le=720)
    note: str | None = Field(default=None, max_length=500)


class SemesterQueueRefreshRequest(BaseModel):
    remaining_available_minutes: int | None = Field(default=None, ge=0, le=24 * 60 * 14)


class SemesterQueueBlockRead(BaseModel):
    id: str
    revision: int
    sequence: int
    course_id: str | None
    course_name: str
    topic_id: str | None
    topic_name: str
    status: Literal["planned", "in_progress", "completed", "skipped", "superseded"]
    planned_minutes: int
    actual_minutes: int | None
    expected_mark_gain: float
    normalized_target_gap_reduction: float
    utility_score: float
    note: str | None
    started_at: datetime | None
    completed_at: datetime | None


class SemesterQueueRevisionRead(BaseModel):
    revision: int
    reason: str
    optimization_model: str
    remaining_minutes: int
    allocated_minutes: int
    total_normalized_target_gap_before: float
    total_normalized_target_gap_after: float
    total_utility_score: float
    courses: list[MultiCourseCourseRead]
    created_at: datetime
    blocks: list[SemesterQueueBlockRead]


class SemesterQueueRead(BaseModel):
    id: str
    status: Literal["active", "completed"]
    initial_available_minutes: int
    remaining_available_minutes: int
    completed_study_minutes: int
    lost_minutes: int
    block_minutes: int
    course_ids: list[str]
    current_revision: int
    next_block_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    revisions: list[SemesterQueueRevisionRead]
