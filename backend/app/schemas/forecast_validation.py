from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ReliabilityBucketRead(BaseModel):
    lower_bound: float
    upper_bound: float
    label: str
    count: int
    mean_predicted_probability: float | None
    observed_success_rate: float | None
    calibration_gap: float | None


class ForecastValidationMetricsRead(BaseModel):
    count: int
    mean_absolute_error: float | None
    root_mean_squared_error: float | None
    mean_signed_error: float | None
    interval_coverage: float | None
    nominal_interval_probability: float | None
    coverage_gap: float | None
    average_interval_width: float | None
    mean_target_probability: float | None
    observed_target_rate: float | None
    brier_score: float | None
    log_loss: float | None


class ForecastValidationDeltasRead(BaseModel):
    mean_absolute_error: float | None
    root_mean_squared_error: float | None
    absolute_coverage_gap: float | None
    brier_score: float | None
    log_loss: float | None


class HeldOutForecastRead(BaseModel):
    forecast_snapshot_id: str
    label: str | None
    training_outcome_count: int
    actual_grade: float
    target_met: bool
    raw_expected_grade: float
    recalibrated_expected_grade: float
    raw_target_probability: float
    recalibrated_target_probability: float
    raw_inside_interval: bool
    recalibrated_inside_interval: bool


class ForecastValidationRead(BaseModel):
    course_id: str
    generated_at: datetime
    completed_pair_count: int
    held_out_count: int
    validation_status: Literal[
        "insufficient_data",
        "preliminary",
        "developing",
        "measured",
    ]
    validation_method: str
    raw_reliability: list[ReliabilityBucketRead]
    held_out_raw_reliability: list[ReliabilityBucketRead]
    held_out_recalibrated_reliability: list[ReliabilityBucketRead]
    raw_metrics: ForecastValidationMetricsRead
    recalibrated_metrics: ForecastValidationMetricsRead
    deltas: ForecastValidationDeltasRead
    verdict: Literal[
        "insufficient_data",
        "improving",
        "stable",
        "mixed",
        "degrading",
    ]
    held_out_forecasts: list[HeldOutForecastRead]
    notes: list[str]
