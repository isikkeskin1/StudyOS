from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MultiCourseCourseRequest(BaseModel):
    course_id: str = Field(min_length=1)
    target_grade: float | None = Field(default=None, ge=0)
    hours_until_exam: float | None = Field(default=None, ge=0, le=24 * 365)
    baseline_mastery: float = Field(default=0.5, ge=0, le=1)
    topic_mastery: dict[str, float] = Field(default_factory=dict)
    use_stored_mastery: bool = True

    @model_validator(mode="after")
    def validate_topic_mastery(self) -> MultiCourseCourseRequest:
        invalid = [key for key, value in self.topic_mastery.items() if not 0 <= value <= 1]
        if invalid:
            raise ValueError("topic_mastery values must be between 0 and 1")
        return self


class MultiCoursePlanRequest(BaseModel):
    available_hours: float = Field(gt=0, le=24 * 14)
    block_minutes: int = Field(default=30, ge=15, le=120)
    courses: list[MultiCourseCourseRequest] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_inputs(self) -> MultiCoursePlanRequest:
        if self.block_minutes % 15 != 0:
            raise ValueError("block_minutes must be a multiple of 15")
        ids = [item.course_id for item in self.courses]
        if len(ids) != len(set(ids)):
            raise ValueError("courses must not contain duplicate course_id values")
        return self


class MultiCourseStudyBlockRead(BaseModel):
    sequence: int
    course_id: str
    course_name: str
    topic_id: str
    topic_name: str
    duration_minutes: int
    expected_mark_gain: float
    normalized_target_gap_reduction: float
    deadline_multiplier: float
    confidence_multiplier: float
    utility_score: float
    cumulative_utility_score: float
    projected_course_grade: float
    remaining_target_gap: float


class MultiCourseCourseRead(BaseModel):
    course_id: str
    course_name: str
    exam_date: date | None
    deadline_source: Literal["request_hours", "course_exam_date", "unknown"]
    hours_until_exam: float | None
    days_until_exam: int | None
    target_grade: float
    max_grade: float
    current_estimated_grade: float
    projected_grade: float
    expected_mark_gain: float
    target_gap_before: float
    target_gap_after: float
    target_reached: bool
    allocated_hours: float
    plan_confidence: Literal["low", "medium", "high"]
    confidence_multiplier: float
    initial_deadline_multiplier: float
    initial_best_block_expected_mark_gain: float
    initial_best_block_normalized_target_reduction: float
    initial_utility_per_hour: float
    estimated_hours_to_target_before: float | None


class MultiCoursePlanRead(BaseModel):
    optimization_model: str
    available_hours: float
    allocated_hours: float
    unallocated_hours: float
    block_minutes: int
    total_normalized_target_gap_before: float
    total_normalized_target_gap_after: float
    total_normalized_target_gap_reduction: float
    total_utility_score: float
    next_action: MultiCourseStudyBlockRead | None
    schedule: list[MultiCourseStudyBlockRead]
    courses: list[MultiCourseCourseRead]
    assumptions: list[str]
