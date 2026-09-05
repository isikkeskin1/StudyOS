from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.semester_queue import SemesterQueueBlockRead


class SemesterCourseStatus(BaseModel):
    course_id: str
    course_name: str
    exam_date: date | None
    days_until_exam: int | None
    deadline_pressure: Literal["unknown", "past", "today", "soon", "upcoming", "later"]
    target_grade: float | None
    max_grade: float
    current_estimated_grade: float | None
    target_gap: float | None
    normalized_target_gap: float | None
    target_status: Literal["unconfigured", "unmeasured", "below_target", "at_target"]
    confidence: str
    topic_count: int
    measured_topic_count: int
    due_review_count: int


class SemesterQueueStatus(BaseModel):
    queue_id: str
    status: str
    revision: int
    remaining_available_minutes: int
    completed_study_minutes: int
    needs_refresh: bool
    refresh_reasons: list[str]
    planned_minutes: int


class SemesterDashboardRead(BaseModel):
    generated_at: datetime
    course_count: int
    upcoming_exam_count: int
    below_target_count: int
    unmeasured_course_count: int
    due_review_count: int
    courses: list[SemesterCourseStatus]
    queues: list[SemesterQueueStatus]
    selected_queue_id: str | None
    next_action: SemesterQueueBlockRead | None
    assumptions: list[str]
