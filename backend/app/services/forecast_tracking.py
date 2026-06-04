from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.forecast_tracking import GradeForecastOutcome, GradeForecastSnapshot
from app.schemas.forecast_tracking import (
    ForecastCalibrationRead,
    ForecastEvaluationRead,
    ForecastOutcomeCreate,
    ForecastOutcomeRead,
    ForecastSnapshotCreate,
    ForecastSnapshotRead,
)
from app.schemas.grade_modeling import GradeThresholdProbabilityRead
from app.services.grade_modeling import build_grade_forecast


class ForecastTrackingError(RuntimeError):
    pass


@dataclass(frozen=True)
class Evaluation:
    snapshot: GradeForecastSnapshot
    outcome: GradeForecastOutcome
    signed_error: float
    absolute_error: float
    squared_error: float
    inside_interval: bool
    target_met: bool
    brier_score: float
    log_loss: float


def _decode_thresholds(snapshot: GradeForecastSnapshot) -> list[GradeThresholdProbabilityRead]:
    return [
        GradeThresholdProbabilityRead.model_validate(item)
        for item in json.loads(snapshot.thresholds_payload)
    ]


def _decode_assumptions(snapshot: GradeForecastSnapshot) -> list[str]:
    return list(json.loads(snapshot.assumptions_payload))


def snapshot_to_read(
    snapshot: GradeForecastSnapshot,
    outcome: GradeForecastOutcome | None,
) -> ForecastSnapshotRead:
    outcome_read = None
    if outcome is not None:
        outcome_read = ForecastOutcomeRead(
            id=outcome.id,
            actual_grade=outcome.actual_grade,
            occurred_at=outcome.occurred_at,
            created_at=outcome.created_at,
        )
    return ForecastSnapshotRead(
        id=snapshot.id,
        course_id=snapshot.course_id,
        label=snapshot.label,
        exam_date=snapshot.exam_date,
        forecast_model=snapshot.forecast_model,
        probability_status=snapshot.probability_status,
        max_grade=snapshot.max_grade,
        study_hours=snapshot.study_hours,
        target_grade=snapshot.target_grade,
        expected_grade=snapshot.expected_grade,
        standard_deviation=snapshot.standard_deviation,
        interval_probability=snapshot.interval_probability,
        likely_range_low=snapshot.likely_range_low,
        likely_range_high=snapshot.likely_range_high,
        target_probability=snapshot.target_probability,
        evidence_quality=snapshot.evidence_quality,
        evidence_confidence=snapshot.evidence_confidence,
        thresholds=_decode_thresholds(snapshot),
        assumptions=_decode_assumptions(snapshot),
        created_at=snapshot.created_at,
        outcome=outcome_read,
    )


def create_forecast_snapshot(
    db: Session,
    course: Course,
    payload: ForecastSnapshotCreate,
) -> ForecastSnapshotRead:
    forecast = build_grade_forecast(db, course, payload.forecast)
    snapshot = GradeForecastSnapshot(
        course_id=course.id,
        label=payload.label,
        exam_date=payload.exam_date,
        forecast_model=forecast.forecast_model,
        probability_status=forecast.probability_status,
        max_grade=course.max_grade,
        study_hours=forecast.study_hours,
        target_grade=forecast.target_grade,
        expected_grade=forecast.expected_grade,
        standard_deviation=forecast.standard_deviation,
        interval_probability=forecast.interval_probability,
        likely_range_low=forecast.likely_range_low,
        likely_range_high=forecast.likely_range_high,
        target_probability=forecast.target_probability,
        evidence_quality=forecast.evidence_quality,
        evidence_confidence=forecast.evidence_confidence,
        request_payload=json.dumps(payload.forecast.model_dump(mode="json"), sort_keys=True),
        thresholds_payload=json.dumps(
            [item.model_dump(mode="json") for item in forecast.thresholds],
            sort_keys=True,
        ),
        assumptions_payload=json.dumps(forecast.assumptions),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot_to_read(snapshot, None)


def list_forecast_snapshots(db: Session, course_id: str) -> list[ForecastSnapshotRead]:
    snapshots = list(
        db.scalars(
            select(GradeForecastSnapshot)
            .where(GradeForecastSnapshot.course_id == course_id)
            .order_by(GradeForecastSnapshot.created_at.desc(), GradeForecastSnapshot.id.desc())
        ).all()
    )
    snapshot_ids = [item.id for item in snapshots]
    outcomes_by_snapshot: dict[str, GradeForecastOutcome] = {}
    if snapshot_ids:
        outcomes_by_snapshot = {
            item.forecast_snapshot_id: item
            for item in db.scalars(
                select(GradeForecastOutcome).where(
                    GradeForecastOutcome.forecast_snapshot_id.in_(snapshot_ids)
                )
            ).all()
        }
    return [
        snapshot_to_read(snapshot, outcomes_by_snapshot.get(snapshot.id))
        for snapshot in snapshots
    ]


def record_forecast_outcome(
    db: Session,
    course: Course,
    snapshot_id: str,
    payload: ForecastOutcomeCreate,
) -> ForecastSnapshotRead:
    snapshot = db.get(GradeForecastSnapshot, snapshot_id)
    if snapshot is None or snapshot.course_id != course.id:
        raise ForecastTrackingError("Forecast snapshot not found")
    if payload.actual_grade > snapshot.max_grade:
        raise ForecastTrackingError("Actual grade cannot exceed the forecast score maximum")
    existing = db.scalar(
        select(GradeForecastOutcome).where(
            GradeForecastOutcome.forecast_snapshot_id == snapshot.id
        )
    )
    if existing is not None:
        raise ForecastTrackingError("This forecast snapshot already has an exam outcome")

    outcome = GradeForecastOutcome(
        forecast_snapshot_id=snapshot.id,
        actual_grade=payload.actual_grade,
        occurred_at=payload.occurred_at,
    )
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return snapshot_to_read(snapshot, outcome)


def _evaluation(
    snapshot: GradeForecastSnapshot,
    outcome: GradeForecastOutcome,
) -> Evaluation:
    signed_error = snapshot.expected_grade - outcome.actual_grade
    target_met = outcome.actual_grade >= snapshot.target_grade
    observed = 1.0 if target_met else 0.0
    probability = max(1e-6, min(1.0 - 1e-6, snapshot.target_probability))
    brier_score = (snapshot.target_probability - observed) ** 2
    log_loss = -(
        observed * math.log(probability)
        + (1.0 - observed) * math.log(1.0 - probability)
    )
    return Evaluation(
        snapshot=snapshot,
        outcome=outcome,
        signed_error=signed_error,
        absolute_error=abs(signed_error),
        squared_error=signed_error**2,
        inside_interval=(
            snapshot.likely_range_low <= outcome.actual_grade <= snapshot.likely_range_high
        ),
        target_met=target_met,
        brier_score=brier_score,
        log_loss=log_loss,
    )


def _status(count: int) -> str:
    if count < 3:
        return "insufficient_data"
    if count < 10:
        return "preliminary"
    if count < 30:
        return "developing"
    return "measured"


def build_forecast_calibration(db: Session, course_id: str) -> ForecastCalibrationRead:
    pairs = list(
        db.execute(
            select(GradeForecastSnapshot, GradeForecastOutcome)
            .join(
                GradeForecastOutcome,
                GradeForecastOutcome.forecast_snapshot_id == GradeForecastSnapshot.id,
            )
            .where(GradeForecastSnapshot.course_id == course_id)
            .order_by(GradeForecastSnapshot.created_at, GradeForecastSnapshot.id)
        ).all()
    )
    evaluations = [_evaluation(snapshot, outcome) for snapshot, outcome in pairs]
    count = len(evaluations)
    if count == 0:
        return ForecastCalibrationRead(
            course_id=course_id,
            generated_at=datetime.now(UTC),
            paired_forecast_count=0,
            calibration_status="insufficient_data",
            mean_absolute_error=None,
            root_mean_squared_error=None,
            mean_signed_error=None,
            interval_coverage=None,
            average_nominal_interval_probability=None,
            coverage_gap=None,
            average_interval_width=None,
            mean_target_probability=None,
            observed_target_rate=None,
            target_calibration_gap=None,
            brier_score=None,
            log_loss=None,
            uncertainty_direction="insufficient_data",
            evaluations=[],
            notes=[
                "Record outcomes against saved pre-exam forecasts before interpreting calibration.",
                "Calibration metrics are descriptive until enough independent exams accumulate.",
            ],
        )

    mean_absolute_error = sum(item.absolute_error for item in evaluations) / count
    root_mean_squared_error = math.sqrt(
        sum(item.squared_error for item in evaluations) / count
    )
    mean_signed_error = sum(item.signed_error for item in evaluations) / count
    interval_coverage = sum(item.inside_interval for item in evaluations) / count
    nominal = sum(item.snapshot.interval_probability for item in evaluations) / count
    average_width = sum(
        item.snapshot.likely_range_high - item.snapshot.likely_range_low
        for item in evaluations
    ) / count
    mean_probability = sum(item.snapshot.target_probability for item in evaluations) / count
    observed_rate = sum(item.target_met for item in evaluations) / count
    calibration_gap = mean_probability - observed_rate
    mean_brier = sum(item.brier_score for item in evaluations) / count
    mean_log_loss = sum(item.log_loss for item in evaluations) / count
    coverage_gap = interval_coverage - nominal

    if count < 3:
        direction = "insufficient_data"
    elif coverage_gap < -0.05:
        direction = "widen"
    elif coverage_gap > 0.05:
        direction = "narrow"
    else:
        direction = "stable"

    return ForecastCalibrationRead(
        course_id=course_id,
        generated_at=datetime.now(UTC),
        paired_forecast_count=count,
        calibration_status=_status(count),
        mean_absolute_error=round(mean_absolute_error, 4),
        root_mean_squared_error=round(root_mean_squared_error, 4),
        mean_signed_error=round(mean_signed_error, 4),
        interval_coverage=round(interval_coverage, 4),
        average_nominal_interval_probability=round(nominal, 4),
        coverage_gap=round(coverage_gap, 4),
        average_interval_width=round(average_width, 4),
        mean_target_probability=round(mean_probability, 4),
        observed_target_rate=round(observed_rate, 4),
        target_calibration_gap=round(calibration_gap, 4),
        brier_score=round(mean_brier, 4),
        log_loss=round(mean_log_loss, 4),
        uncertainty_direction=direction,
        evaluations=[
            ForecastEvaluationRead(
                forecast_snapshot_id=item.snapshot.id,
                label=item.snapshot.label,
                expected_grade=item.snapshot.expected_grade,
                actual_grade=item.outcome.actual_grade,
                signed_error=round(item.signed_error, 4),
                absolute_error=round(item.absolute_error, 4),
                squared_error=round(item.squared_error, 4),
                inside_interval=item.inside_interval,
                interval_probability=item.snapshot.interval_probability,
                target_grade=item.snapshot.target_grade,
                target_probability=item.snapshot.target_probability,
                target_met=item.target_met,
                brier_score=round(item.brier_score, 4),
                log_loss=round(item.log_loss, 4),
            )
            for item in evaluations
        ],
        notes=[
            "Signed error is forecast minus actual grade; positive values indicate overprediction.",
            (
                "Interval coverage should be compared with the average nominal interval level; "
                "coverage below nominal suggests uncertainty may be too narrow."
            ),
            (
                "Brier score and log loss evaluate target-threshold probabilities; lower is better."
            ),
            "Do not treat preliminary calibration from a few exams as statistically stable.",
        ],
    )
