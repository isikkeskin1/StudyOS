from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EmergencyPlanRequest(BaseModel):
    available_hours: float = Field(gt=0, le=72)
    target_grade: float | None = Field(default=None, ge=0)
    hours_until_exam: float | None = Field(default=None, ge=0, le=720)
    block_minutes: int = Field(default=30, ge=15, le=120)
    skip_threshold_marks_per_hour: float = Field(default=0.10, ge=0, le=10)
    baseline_mastery: float = Field(default=0.5, ge=0, le=1)
    topic_mastery: dict[str, float] = Field(default_factory=dict)
    use_stored_mastery: bool = True

    @model_validator(mode="after")
    def validate_inputs(self) -> EmergencyPlanRequest:
        invalid = [key for key, value in self.topic_mastery.items() if not 0 <= value <= 1]
        if invalid:
            raise ValueError("topic_mastery values must be between 0 and 1")
        if self.block_minutes % 15 != 0:
            raise ValueError("block_minutes must be a multiple of 15")
        if self.hours_until_exam is not None and self.available_hours > self.hours_until_exam:
            raise ValueError("available_hours cannot exceed hours_until_exam")
        return self


class EmergencyStudyBlockRead(BaseModel):
    sequence: int
    topic_id: str
    topic_name: str
    duration_minutes: int
    starting_mastery: float
    ending_mastery: float
    expected_mark_gain: float
    expected_marks_per_hour: float
    cumulative_expected_mark_gain: float


class EmergencyTopicValueRead(BaseModel):
    topic_id: str
    topic_name: str
    exam_weight: float
    current_mastery: float
    mastery_source: str
    allocated_hours: float
    expected_mark_gain: float
    average_marks_per_hour: float
    next_block_expected_mark_gain: float
    next_hour_expected_mark_gain: float
    initial_marks_per_hour: float
    post_plan_marginal_marks_per_hour: float
    decision: Literal["study", "defer", "skip"]
    decision_reason: str
    mistake_focus: list[str] = Field(default_factory=list)
    learning_scale_hours: float
    calibration_source: str


class EmergencyNextActionRead(BaseModel):
    topic_id: str
    topic_name: str
    duration_minutes: int
    expected_mark_gain: float
    expected_marks_per_hour: float


class EmergencyPlanRead(BaseModel):
    course_id: str
    optimization_model: str
    confidence: str
    urgency: Literal["unknown", "standard", "elevated", "high", "critical"]
    hours_until_exam: float | None
    available_hours: float
    block_minutes: int
    target_grade: float
    max_grade: float
    current_estimated_grade: float
    projected_grade: float
    expected_mark_gain: float
    target_gap_before: float
    target_gap_after: float
    target_reachable_with_available_time: bool
    estimated_hours_to_target: float | None
    emergency_skip_cutoff_marks_per_hour: float
    next_action: EmergencyNextActionRead | None
    schedule: list[EmergencyStudyBlockRead]
    topics: list[EmergencyTopicValueRead]
    assumptions: list[str]
