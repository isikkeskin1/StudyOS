from __future__ import annotations

import json
import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecast_tracking import (
    GradeForecastOutcome,
    GradeForecastRecalibrationArtifact,
    GradeForecastSnapshot,
)
from app.schemas.grade_modeling import (
    CalibratedGradeForecastRead,
    EmpiricalRecalibrationRead,
    GradeForecastRequest,
    GradeForecastScenarioRead,
    GradeThresholdProbabilityRead,
)
from app.services.grade_modeling import build_grade_forecast

_RECALIBRATION_MODEL = "empirical-v1"
_MIN_ACTIVE_OUTCOMES = 5
_FULL_WEIGHT_OUTCOMES = 20
_MAX_BIAS_RATIO = 0.05
_MIN_WIDTH_MULTIPLIER = 0.75
_MAX_WIDTH_MULTIPLIER = 1.35

ForecastOutcomeRow = tuple[
    GradeForecastSnapshot,
    GradeForecastOutcome,
    GradeForecastRecalibrationArtifact | None,
]


@dataclass(frozen=True)
class EmpiricalAdjustment:
    active: bool
    calibration_model: str
    calibration_status: str
    paired_outcome_count: int
    shrinkage_weight: float
    raw_bias_marks: float
    applied_bias_marks: float
    raw_width_multiplier: float
    applied_width_multiplier: float


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def inverse_normal_cdf(probability: float) -> float:
    low = -8.0
    high = 8.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        if normal_cdf(midpoint) < probability:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def probability_at_or_above(
    threshold: float,
    mean: float,
    standard_deviation: float,
    max_grade: float,
) -> float:
    if threshold <= 0:
        return 1.0
    if threshold > max_grade:
        return 0.0
    if standard_deviation <= 1e-9:
        return 1.0 if mean >= threshold else 0.0
    return max(
        0.0,
        min(1.0, 1.0 - normal_cdf((threshold - mean) / standard_deviation)),
    )


def score_interval(
    mean: float,
    standard_deviation: float,
    probability: float,
    max_grade: float,
) -> tuple[float, float]:
    z_score = inverse_normal_cdf(0.5 + probability / 2.0)
    return (
        round(max(0.0, mean - z_score * standard_deviation), 2),
        round(min(max_grade, mean + z_score * standard_deviation), 2),
    )


def _status(count: int) -> str:
    if count < _MIN_ACTIVE_OUTCOMES:
        return "inactive"
    if count < 10:
        return "guarded"
    if count < 30:
        return "developing"
    return "measured"


def raw_values(
    snapshot: GradeForecastSnapshot,
    artifact: GradeForecastRecalibrationArtifact | None,
) -> tuple[float, float]:
    if artifact is None:
        return snapshot.expected_grade, max(1e-6, snapshot.standard_deviation)
    return artifact.raw_expected_grade, max(1e-6, artifact.raw_standard_deviation)


def adjustment_from_rows(
    rows: list[ForecastOutcomeRow],
    max_grade: float,
) -> EmpiricalAdjustment:
    count = len(rows)
    if count == 0:
        return EmpiricalAdjustment(
            active=False,
            calibration_model=_RECALIBRATION_MODEL,
            calibration_status="inactive",
            paired_outcome_count=0,
            shrinkage_weight=0.0,
            raw_bias_marks=0.0,
            applied_bias_marks=0.0,
            raw_width_multiplier=1.0,
            applied_width_multiplier=1.0,
        )

    residuals: list[float] = []
    raw_sds: list[float] = []
    for snapshot, outcome, artifact in rows:
        raw_mean, raw_sd = raw_values(snapshot, artifact)
        residuals.append(outcome.actual_grade - raw_mean)
        raw_sds.append(raw_sd)

    mean_residual = sum(residuals) / count
    normalized_variance = sum(
        ((residual - mean_residual) / raw_sd) ** 2
        for residual, raw_sd in zip(residuals, raw_sds, strict=True)
    ) / count
    empirical_width = math.sqrt(max(0.0, normalized_variance))
    empirical_width = max(
        _MIN_WIDTH_MULTIPLIER,
        min(_MAX_WIDTH_MULTIPLIER, empirical_width),
    )

    active = count >= _MIN_ACTIVE_OUTCOMES
    weight = min(1.0, count / _FULL_WEIGHT_OUTCOMES) if active else 0.0
    bias_cap = max_grade * _MAX_BIAS_RATIO
    capped_bias = max(-bias_cap, min(bias_cap, mean_residual))
    applied_bias = weight * capped_bias
    applied_width = 1.0 + weight * (empirical_width - 1.0)

    return EmpiricalAdjustment(
        active=active,
        calibration_model=_RECALIBRATION_MODEL,
        calibration_status=_status(count),
        paired_outcome_count=count,
        shrinkage_weight=round(weight, 4),
        raw_bias_marks=round(mean_residual, 4),
        applied_bias_marks=round(applied_bias, 4),
        raw_width_multiplier=round(empirical_width, 4),
        applied_width_multiplier=round(applied_width, 4),
    )


def empirical_adjustment(
    db: Session,
    course_id: str,
    max_grade: float,
) -> EmpiricalAdjustment:
    rows = list(
        db.execute(
            select(
                GradeForecastSnapshot,
                GradeForecastOutcome,
                GradeForecastRecalibrationArtifact,
            )
            .join(
                GradeForecastOutcome,
                GradeForecastOutcome.forecast_snapshot_id == GradeForecastSnapshot.id,
            )
            .outerjoin(
                GradeForecastRecalibrationArtifact,
                GradeForecastRecalibrationArtifact.forecast_snapshot_id
                == GradeForecastSnapshot.id,
            )
            .where(GradeForecastSnapshot.course_id == course_id)
        ).all()
    )
    return adjustment_from_rows(rows, max_grade)


def adjustment_to_read(adjustment: EmpiricalAdjustment) -> EmpiricalRecalibrationRead:
    return EmpiricalRecalibrationRead(
        active=adjustment.active,
        calibration_model=adjustment.calibration_model,
        calibration_status=adjustment.calibration_status,
        paired_outcome_count=adjustment.paired_outcome_count,
        shrinkage_weight=adjustment.shrinkage_weight,
        raw_bias_marks=adjustment.raw_bias_marks,
        applied_bias_marks=adjustment.applied_bias_marks,
        raw_width_multiplier=adjustment.raw_width_multiplier,
        applied_width_multiplier=adjustment.applied_width_multiplier,
        note=(
            "Empirical corrections activate after five completed forecast/outcome pairs, "
            "are shrunk toward no correction, and remain provisional."
        ),
    )


def _adjust_scenario(
    scenario: GradeForecastScenarioRead,
    adjustment: EmpiricalAdjustment,
    target_grade: float,
    max_grade: float,
    interval_probability: float,
) -> GradeForecastScenarioRead:
    raw_mean = scenario.expected_grade
    raw_sd = max(
        0.01,
        (scenario.likely_range_high - scenario.likely_range_low)
        / (2.0 * inverse_normal_cdf(0.5 + interval_probability / 2.0)),
    )
    mean = max(0.0, min(max_grade, raw_mean + adjustment.applied_bias_marks))
    standard_deviation = raw_sd * adjustment.applied_width_multiplier
    low, high = score_interval(
        mean,
        standard_deviation,
        interval_probability,
        max_grade,
    )
    return GradeForecastScenarioRead(
        study_hours=scenario.study_hours,
        expected_grade=round(mean, 2),
        likely_range_low=low,
        likely_range_high=high,
        target_probability=round(
            probability_at_or_above(
                target_grade,
                mean,
                standard_deviation,
                max_grade,
            ),
            4,
        ),
    )


def _inactive_read(raw, adjustment: EmpiricalAdjustment) -> CalibratedGradeForecastRead:
    return CalibratedGradeForecastRead(
        course_id=raw.course_id,
        forecast_model=f"{raw.forecast_model}+{_RECALIBRATION_MODEL}",
        probability_status="provisional_empirical",
        raw_forecast=raw,
        recalibration=adjustment_to_read(adjustment),
        expected_grade=raw.expected_grade,
        standard_deviation=raw.standard_deviation,
        interval_probability=raw.interval_probability,
        likely_range_low=raw.likely_range_low,
        likely_range_high=raw.likely_range_high,
        target_grade=raw.target_grade,
        target_probability=raw.target_probability,
        thresholds=raw.thresholds,
        scenarios=raw.scenarios,
        assumptions=[
            *raw.assumptions,
            (
                "Empirical recalibration is inactive until five completed forecast/outcome "
                "pairs exist; all forecast values are therefore identical to the raw model."
            ),
        ],
    )


def build_calibrated_grade_forecast(
    db: Session,
    course,
    payload: GradeForecastRequest,
) -> CalibratedGradeForecastRead:
    raw = build_grade_forecast(db, course, payload)
    adjustment = empirical_adjustment(db, course.id, course.max_grade)
    if not adjustment.active:
        return _inactive_read(raw, adjustment)

    expected_grade = max(
        0.0,
        min(course.max_grade, raw.expected_grade + adjustment.applied_bias_marks),
    )
    standard_deviation = raw.standard_deviation * adjustment.applied_width_multiplier
    low, high = score_interval(
        expected_grade,
        standard_deviation,
        raw.interval_probability,
        course.max_grade,
    )
    thresholds = [
        GradeThresholdProbabilityRead(
            grade=item.grade,
            probability_at_or_above=round(
                probability_at_or_above(
                    item.grade,
                    expected_grade,
                    standard_deviation,
                    course.max_grade,
                ),
                4,
            ),
        )
        for item in raw.thresholds
    ]
    target_probability = probability_at_or_above(
        raw.target_grade,
        expected_grade,
        standard_deviation,
        course.max_grade,
    )
    scenarios = [
        _adjust_scenario(
            scenario,
            adjustment,
            raw.target_grade,
            course.max_grade,
            raw.interval_probability,
        )
        for scenario in raw.scenarios
    ]

    return CalibratedGradeForecastRead(
        course_id=course.id,
        forecast_model=f"{raw.forecast_model}+{_RECALIBRATION_MODEL}",
        probability_status="provisional_empirical",
        raw_forecast=raw,
        recalibration=adjustment_to_read(adjustment),
        expected_grade=round(expected_grade, 2),
        standard_deviation=round(standard_deviation, 2),
        interval_probability=raw.interval_probability,
        likely_range_low=low,
        likely_range_high=high,
        target_grade=raw.target_grade,
        target_probability=round(target_probability, 4),
        thresholds=thresholds,
        scenarios=scenarios,
        assumptions=[
            *raw.assumptions,
            (
                "Empirical recalibration is trained only on saved forecast/outcome pairs and "
                "uses raw pre-recalibration predictions to avoid feedback loops."
            ),
            (
                "Bias and uncertainty corrections are capped and confidence-shrunk; fewer than "
                "five outcomes leaves the raw forecast unchanged."
            ),
        ],
    )


def artifact_raw_thresholds(
    artifact: GradeForecastRecalibrationArtifact,
) -> list[GradeThresholdProbabilityRead]:
    return [
        GradeThresholdProbabilityRead.model_validate(item)
        for item in json.loads(artifact.raw_thresholds_payload)
    ]
