from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.grade_modeling import GradeForecastRequest, GradeThresholdProbabilityRead


class ForecastSnapshotCreate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    exam_date: date | None = None
    forecast: GradeForecastRequest = Field(default_factory=GradeForecastRequest)


class ForecastOutcomeCreate(BaseModel):
    actual_grade: float = Field(ge=0)
    occurred_at: date | None = None


class ForecastOutcomeRead(BaseModel):
    id: str
    actual_grade: float
    occurred_at: date | None
    created_at: datetime


class ForecastSnapshotRead(BaseModel):
    id: str
    course_id: str
    label: str | None
    exam_date: date | None
    forecast_model: str
    probability_status: str
    max_grade: float
    study_hours: float
    target_grade: float
    expected_grade: float
    standard_deviation: float
    interval_probability: float
    likely_range_low: float
    likely_range_high: float
    target_probability: float
    evidence_quality: float
    evidence_confidence: str
    thresholds: list[GradeThresholdProbabilityRead]
    assumptions: list[str]
    created_at: datetime
    outcome: ForecastOutcomeRead | None


class ForecastEvaluationRead(BaseModel):
    forecast_snapshot_id: str
    label: str | None
    expected_grade: float
    actual_grade: float
    signed_error: float
    absolute_error: float
    squared_error: float
    inside_interval: bool
    interval_probability: float
    target_grade: float
    target_probability: float
    target_met: bool
    brier_score: float
    log_loss: float


class ForecastCalibrationRead(BaseModel):
    course_id: str
    generated_at: datetime
    paired_forecast_count: int
    calibration_status: Literal[
        "insufficient_data",
        "preliminary",
        "developing",
        "measured",
    ]
    mean_absolute_error: float | None
    root_mean_squared_error: float | None
    mean_signed_error: float | None
    interval_coverage: float | None
    average_nominal_interval_probability: float | None
    coverage_gap: float | None
    average_interval_width: float | None
    mean_target_probability: float | None
    observed_target_rate: float | None
    target_calibration_gap: float | None
    brier_score: float | None
    log_loss: float | None
    uncertainty_direction: Literal[
        "insufficient_data",
        "widen",
        "stable",
        "narrow",
    ]
    evaluations: list[ForecastEvaluationRead]
    notes: list[str]
