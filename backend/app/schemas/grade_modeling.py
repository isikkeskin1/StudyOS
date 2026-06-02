from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class GradeForecastRequest(BaseModel):
    study_hours: float = Field(default=0.0, ge=0, le=300)
    target_grade: float | None = Field(default=None, ge=0)
    desired_probability: float = Field(default=0.80, ge=0.50, le=0.95)
    interval_probability: float = Field(default=0.80, ge=0.50, le=0.95)
    thresholds: list[float] = Field(default_factory=list)
    baseline_mastery: float = Field(default=0.5, ge=0, le=1)
    topic_mastery: dict[str, float] = Field(default_factory=dict)
    use_stored_mastery: bool = True

    @model_validator(mode="after")
    def validate_inputs(self) -> GradeForecastRequest:
        invalid_mastery = [
            key for key, value in self.topic_mastery.items() if not 0 <= value <= 1
        ]
        if invalid_mastery:
            raise ValueError("topic_mastery values must be between 0 and 1")
        if any(value < 0 for value in self.thresholds):
            raise ValueError("thresholds cannot contain negative grades")
        return self


class GradeThresholdProbabilityRead(BaseModel):
    grade: float
    probability_at_or_above: float


class GradeForecastScenarioRead(BaseModel):
    study_hours: float
    expected_grade: float
    likely_range_low: float
    likely_range_high: float
    target_probability: float


class RequiredHoursRead(BaseModel):
    target_grade: float
    desired_probability: float
    estimated_hours: float | None
    optimistic_hours: float | None
    conservative_hours: float | None
    achievable_under_model: bool
    note: str


class GradeForecastRead(BaseModel):
    course_id: str
    forecast_model: str
    probability_status: str
    evidence_quality: float
    evidence_confidence: str
    study_hours: float
    expected_grade: float
    standard_deviation: float
    interval_probability: float
    likely_range_low: float
    likely_range_high: float
    target_grade: float
    target_probability: float
    thresholds: list[GradeThresholdProbabilityRead]
    required_hours: RequiredHoursRead
    scenarios: list[GradeForecastScenarioRead]
    assumptions: list[str]
