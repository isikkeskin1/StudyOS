from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecast_tracking import (
    GradeForecastOutcome,
    GradeForecastRecalibrationArtifact,
    GradeForecastSnapshot,
)
from app.schemas.forecast_validation import (
    ForecastValidationDeltasRead,
    ForecastValidationMetricsRead,
    ForecastValidationRead,
    HeldOutForecastRead,
    ReliabilityBucketRead,
)
from app.services.forecast_recalibration import (
    ForecastOutcomeRow,
    adjustment_from_rows,
    probability_at_or_above,
    raw_values,
    score_interval,
)

_BUCKETS = [
    (0.0, 0.2),
    (0.2, 0.4),
    (0.4, 0.6),
    (0.6, 0.8),
    (0.8, 1.0),
]
_MIN_TRAINING_OUTCOMES = 5


@dataclass(frozen=True)
class PredictionEvaluation:
    forecast_snapshot_id: str
    label: str | None
    training_outcome_count: int
    expected_grade: float
    standard_deviation: float
    interval_probability: float
    likely_range_low: float
    likely_range_high: float
    target_probability: float
    actual_grade: float
    target_met: bool

    @property
    def signed_error(self) -> float:
        return self.expected_grade - self.actual_grade

    @property
    def inside_interval(self) -> bool:
        return self.likely_range_low <= self.actual_grade <= self.likely_range_high


def _rows(db: Session, course_id: str) -> list[ForecastOutcomeRow]:
    return list(
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
            .order_by(GradeForecastSnapshot.created_at, GradeForecastSnapshot.id)
        ).all()
    )


def _raw_probability(
    snapshot: GradeForecastSnapshot,
    artifact: GradeForecastRecalibrationArtifact | None,
) -> float:
    if artifact is None:
        return snapshot.target_probability
    return artifact.raw_target_probability


def _raw_interval(
    snapshot: GradeForecastSnapshot,
    artifact: GradeForecastRecalibrationArtifact | None,
) -> tuple[float, float]:
    if artifact is None:
        return snapshot.likely_range_low, snapshot.likely_range_high
    return artifact.raw_likely_range_low, artifact.raw_likely_range_high


def _raw_evaluation(row: ForecastOutcomeRow, training_count: int = 0) -> PredictionEvaluation:
    snapshot, outcome, artifact = row
    mean, standard_deviation = raw_values(snapshot, artifact)
    low, high = _raw_interval(snapshot, artifact)
    return PredictionEvaluation(
        forecast_snapshot_id=snapshot.id,
        label=snapshot.label,
        training_outcome_count=training_count,
        expected_grade=mean,
        standard_deviation=standard_deviation,
        interval_probability=snapshot.interval_probability,
        likely_range_low=low,
        likely_range_high=high,
        target_probability=_raw_probability(snapshot, artifact),
        actual_grade=outcome.actual_grade,
        target_met=outcome.actual_grade >= snapshot.target_grade,
    )


def _recalibrated_evaluation(
    row: ForecastOutcomeRow,
    training_rows: list[ForecastOutcomeRow],
) -> PredictionEvaluation:
    snapshot, outcome, artifact = row
    raw_mean, raw_sd = raw_values(snapshot, artifact)
    adjustment = adjustment_from_rows(training_rows, snapshot.max_grade)
    mean = max(
        0.0,
        min(snapshot.max_grade, raw_mean + adjustment.applied_bias_marks),
    )
    standard_deviation = raw_sd * adjustment.applied_width_multiplier
    low, high = score_interval(
        mean,
        standard_deviation,
        snapshot.interval_probability,
        snapshot.max_grade,
    )
    target_probability = probability_at_or_above(
        snapshot.target_grade,
        mean,
        standard_deviation,
        snapshot.max_grade,
    )
    return PredictionEvaluation(
        forecast_snapshot_id=snapshot.id,
        label=snapshot.label,
        training_outcome_count=len(training_rows),
        expected_grade=mean,
        standard_deviation=standard_deviation,
        interval_probability=snapshot.interval_probability,
        likely_range_low=low,
        likely_range_high=high,
        target_probability=target_probability,
        actual_grade=outcome.actual_grade,
        target_met=outcome.actual_grade >= snapshot.target_grade,
    )


def _metrics(items: list[PredictionEvaluation]) -> ForecastValidationMetricsRead:
    count = len(items)
    if count == 0:
        return ForecastValidationMetricsRead(
            count=0,
            mean_absolute_error=None,
            root_mean_squared_error=None,
            mean_signed_error=None,
            interval_coverage=None,
            nominal_interval_probability=None,
            coverage_gap=None,
            average_interval_width=None,
            mean_target_probability=None,
            observed_target_rate=None,
            brier_score=None,
            log_loss=None,
        )

    signed_errors = [item.signed_error for item in items]
    mae = sum(abs(value) for value in signed_errors) / count
    rmse = math.sqrt(sum(value**2 for value in signed_errors) / count)
    interval_coverage = sum(item.inside_interval for item in items) / count
    nominal = sum(item.interval_probability for item in items) / count
    mean_probability = sum(item.target_probability for item in items) / count
    observed_rate = sum(item.target_met for item in items) / count
    brier = sum(
        (item.target_probability - (1.0 if item.target_met else 0.0)) ** 2
        for item in items
    ) / count
    log_loss = 0.0
    for item in items:
        probability = max(1e-6, min(1.0 - 1e-6, item.target_probability))
        observed = 1.0 if item.target_met else 0.0
        log_loss += -(
            observed * math.log(probability)
            + (1.0 - observed) * math.log(1.0 - probability)
        )
    log_loss /= count

    return ForecastValidationMetricsRead(
        count=count,
        mean_absolute_error=round(mae, 4),
        root_mean_squared_error=round(rmse, 4),
        mean_signed_error=round(sum(signed_errors) / count, 4),
        interval_coverage=round(interval_coverage, 4),
        nominal_interval_probability=round(nominal, 4),
        coverage_gap=round(interval_coverage - nominal, 4),
        average_interval_width=round(
            sum(item.likely_range_high - item.likely_range_low for item in items) / count,
            4,
        ),
        mean_target_probability=round(mean_probability, 4),
        observed_target_rate=round(observed_rate, 4),
        brier_score=round(brier, 4),
        log_loss=round(log_loss, 4),
    )


def _reliability(items: list[PredictionEvaluation]) -> list[ReliabilityBucketRead]:
    result: list[ReliabilityBucketRead] = []
    for index, (lower, upper) in enumerate(_BUCKETS):
        if index == len(_BUCKETS) - 1:
            bucket = [item for item in items if lower <= item.target_probability <= upper]
        else:
            bucket = [item for item in items if lower <= item.target_probability < upper]
        if bucket:
            mean_probability = sum(item.target_probability for item in bucket) / len(bucket)
            observed_rate = sum(item.target_met for item in bucket) / len(bucket)
            gap = mean_probability - observed_rate
        else:
            mean_probability = None
            observed_rate = None
            gap = None
        result.append(
            ReliabilityBucketRead(
                lower_bound=lower,
                upper_bound=upper,
                label=f"{int(lower * 100)}-{int(upper * 100)}%",
                count=len(bucket),
                mean_predicted_probability=(
                    round(mean_probability, 4) if mean_probability is not None else None
                ),
                observed_success_rate=(
                    round(observed_rate, 4) if observed_rate is not None else None
                ),
                calibration_gap=round(gap, 4) if gap is not None else None,
            )
        )
    return result


def _delta(recalibrated: float | None, raw: float | None) -> float | None:
    if recalibrated is None or raw is None:
        return None
    return round(recalibrated - raw, 4)


def _deltas(
    raw: ForecastValidationMetricsRead,
    recalibrated: ForecastValidationMetricsRead,
) -> ForecastValidationDeltasRead:
    coverage_delta = None
    if raw.coverage_gap is not None and recalibrated.coverage_gap is not None:
        coverage_delta = round(abs(recalibrated.coverage_gap) - abs(raw.coverage_gap), 4)
    return ForecastValidationDeltasRead(
        mean_absolute_error=_delta(
            recalibrated.mean_absolute_error,
            raw.mean_absolute_error,
        ),
        root_mean_squared_error=_delta(
            recalibrated.root_mean_squared_error,
            raw.root_mean_squared_error,
        ),
        absolute_coverage_gap=coverage_delta,
        brier_score=_delta(recalibrated.brier_score, raw.brier_score),
        log_loss=_delta(recalibrated.log_loss, raw.log_loss),
    )


def _validation_status(held_out_count: int) -> str:
    if held_out_count == 0:
        return "insufficient_data"
    if held_out_count < 5:
        return "preliminary"
    if held_out_count < 15:
        return "developing"
    return "measured"


def _verdict(
    held_out_count: int,
    deltas: ForecastValidationDeltasRead,
) -> str:
    if held_out_count < 3:
        return "insufficient_data"

    comparisons = [
        (deltas.mean_absolute_error, 0.05),
        (deltas.root_mean_squared_error, 0.05),
        (deltas.absolute_coverage_gap, 0.01),
        (deltas.brier_score, 0.005),
        (deltas.log_loss, 0.01),
    ]
    improving = sum(value is not None and value < -tolerance for value, tolerance in comparisons)
    degrading = sum(value is not None and value > tolerance for value, tolerance in comparisons)
    if improving >= 3 and degrading <= 1:
        return "improving"
    if degrading >= 3 and improving <= 1:
        return "degrading"
    if improving == 0 and degrading == 0:
        return "stable"
    return "mixed"


def build_forecast_validation(db: Session, course_id: str) -> ForecastValidationRead:
    rows = _rows(db, course_id)
    raw_all = [_raw_evaluation(row) for row in rows]

    held_out_raw: list[PredictionEvaluation] = []
    held_out_recalibrated: list[PredictionEvaluation] = []
    held_out_reads: list[HeldOutForecastRead] = []

    for index, row in enumerate(rows):
        snapshot, _, _ = row
        training_rows = [
            prior
            for prior in rows[:index]
            if prior[1].created_at <= snapshot.created_at
        ]
        if len(training_rows) < _MIN_TRAINING_OUTCOMES:
            continue

        raw_item = _raw_evaluation(row, len(training_rows))
        recalibrated_item = _recalibrated_evaluation(row, training_rows)
        held_out_raw.append(raw_item)
        held_out_recalibrated.append(recalibrated_item)
        held_out_reads.append(
            HeldOutForecastRead(
                forecast_snapshot_id=snapshot.id,
                label=snapshot.label,
                training_outcome_count=len(training_rows),
                actual_grade=raw_item.actual_grade,
                target_met=raw_item.target_met,
                raw_expected_grade=round(raw_item.expected_grade, 2),
                recalibrated_expected_grade=round(
                    recalibrated_item.expected_grade,
                    2,
                ),
                raw_target_probability=round(raw_item.target_probability, 4),
                recalibrated_target_probability=round(
                    recalibrated_item.target_probability,
                    4,
                ),
                raw_inside_interval=raw_item.inside_interval,
                recalibrated_inside_interval=recalibrated_item.inside_interval,
            )
        )

    raw_metrics = _metrics(held_out_raw)
    recalibrated_metrics = _metrics(held_out_recalibrated)
    deltas = _deltas(raw_metrics, recalibrated_metrics)
    held_out_count = len(held_out_raw)

    return ForecastValidationRead(
        course_id=course_id,
        generated_at=datetime.now(UTC),
        completed_pair_count=len(rows),
        held_out_count=held_out_count,
        validation_status=_validation_status(held_out_count),
        validation_method="rolling-origin-v1",
        raw_reliability=_reliability(raw_all),
        held_out_raw_reliability=_reliability(held_out_raw),
        held_out_recalibrated_reliability=_reliability(held_out_recalibrated),
        raw_metrics=raw_metrics,
        recalibrated_metrics=recalibrated_metrics,
        deltas=deltas,
        verdict=_verdict(held_out_count, deltas),
        held_out_forecasts=held_out_reads,
        notes=[
            (
                "Held-out recalibration uses only outcomes that had already been recorded before "
                "each evaluated forecast snapshot was created."
            ),
            (
                "Metric deltas are recalibrated minus raw; negative values are better for MAE, "
                "RMSE, absolute coverage gap, Brier score, and log loss."
            ),
            (
                "Reliability buckets need many independent forecasts before their observed rates "
                "should be interpreted as stable calibration estimates."
            ),
        ],
    )
