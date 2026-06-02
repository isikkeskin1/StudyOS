from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import TopicMastery
from app.models.exam_intelligence import ExamAnalysis
from app.schemas.grade_modeling import (
    GradeForecastRead,
    GradeForecastRequest,
    GradeForecastScenarioRead,
    GradeThresholdProbabilityRead,
    RequiredHoursRead,
)
from app.schemas.planning import StudyPlanRequest
from app.services.calibration import CourseCalibration, get_course_calibration
from app.services.planning import StudyPlanRead, build_study_plan
from app.services.retention import retention_snapshot

_FORECAST_MODEL = "probabilistic-v1"
_PROBABILITY_STATUS = "provisional"
_INTERVAL_DEFAULT = 0.80
_REQUIRED_HOURS_SENSITIVITY = 0.15


class GradeForecastUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvidenceSummary:
    quality: float
    confidence: str
    topic_count: int
    measured_topic_count: int
    exam_signal: float
    longitudinal_signal: float


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _inverse_normal_cdf(probability: float) -> float:
    low = -8.0
    high = 8.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        if _normal_cdf(midpoint) < probability:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def _probability_at_or_above(
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
    z_score = (threshold - mean) / standard_deviation
    return max(0.0, min(1.0, 1.0 - _normal_cdf(z_score)))


def _score_interval(
    mean: float,
    standard_deviation: float,
    probability: float,
    max_grade: float,
) -> tuple[float, float]:
    z_score = _inverse_normal_cdf(0.5 + probability / 2.0)
    low = max(0.0, mean - z_score * standard_deviation)
    high = min(max_grade, mean + z_score * standard_deviation)
    return round(low, 2), round(high, 2)


def _standard_deviation(
    max_grade: float,
    evidence_quality: float,
    study_hours: float,
    *,
    width_multiplier: float = 1.0,
) -> float:
    base_ratio = 0.14 - 0.075 * evidence_quality
    horizon_ratio = min(0.015, max(0.0, study_hours) * 0.0005)
    ratio = max(0.05, base_ratio + horizon_ratio)
    return round(max_grade * ratio * width_multiplier, 4)


def _evidence_summary(
    db: Session,
    course: Course,
    payload: GradeForecastRequest,
    calibration: CourseCalibration,
) -> EvidenceSummary:
    topic_ids = list(
        db.scalars(
            select(CourseTopic.id).where(CourseTopic.course_id == course.id)
        ).all()
    )
    topic_count = len(topic_ids)
    if topic_count == 0:
        return EvidenceSummary(0.0, "low", 0, 0, 0.0, 0.0)

    mastery_rows = []
    if payload.use_stored_mastery:
        mastery_rows = list(
            db.scalars(
                select(TopicMastery).where(TopicMastery.course_id == course.id)
            ).all()
        )
    calibration_by_id = {item.topic_id: item for item in calibration.topics}
    effective_confidences: list[float] = []
    for mastery in mastery_rows:
        calibrated = calibration_by_id.get(mastery.topic_id)
        half_life = (
            calibrated.retention_half_life_days if calibrated is not None else None
        )
        snapshot = retention_snapshot(mastery, half_life_days=half_life)
        effective_confidences.append(snapshot.effective_confidence)

    coverage = min(1.0, len(mastery_rows) / topic_count)
    average_confidence = (
        sum(effective_confidences) / len(effective_confidences)
        if effective_confidences
        else 0.0
    )

    exam_analysis = db.get(ExamAnalysis, course.id)
    exam_signal = 0.0
    if exam_analysis is not None and exam_analysis.question_count > 0:
        volume = min(1.0, exam_analysis.question_count / 8.0)
        marked_ratio = exam_analysis.marked_question_count / exam_analysis.question_count
        exam_signal = 0.60 * volume + 0.40 * marked_ratio

    learning_coverage = calibration.calibrated_learning_topic_count / topic_count
    retention_coverage = calibration.calibrated_retention_topic_count / topic_count
    longitudinal_signal = min(1.0, 0.70 * learning_coverage + 0.30 * retention_coverage)

    quality = (
        0.40 * coverage
        + 0.35 * average_confidence
        + 0.15 * exam_signal
        + 0.10 * longitudinal_signal
    )
    quality = max(0.0, min(1.0, quality))
    confidence = "medium" if quality >= 0.55 else "low"
    return EvidenceSummary(
        quality=round(quality, 4),
        confidence=confidence,
        topic_count=topic_count,
        measured_topic_count=len(mastery_rows),
        exam_signal=round(exam_signal, 4),
        longitudinal_signal=round(longitudinal_signal, 4),
    )


def _plan_request(
    payload: GradeForecastRequest,
    *,
    target_grade: float,
    available_hours: float | None,
) -> StudyPlanRequest:
    return StudyPlanRequest(
        target_grade=target_grade,
        available_hours=available_hours,
        baseline_mastery=payload.baseline_mastery,
        topic_mastery=payload.topic_mastery,
        use_stored_mastery=payload.use_stored_mastery,
    )


def _hours_for_mean_target(
    db: Session,
    course: Course,
    payload: GradeForecastRequest,
    mean_target: float,
) -> float | None:
    if mean_target >= course.max_grade - 1e-9:
        return None
    plan = build_study_plan(
        db,
        course,
        _plan_request(
            payload,
            target_grade=mean_target,
            available_hours=None,
        ),
    )
    return plan.estimated_hours_to_target


def _required_hours(
    db: Session,
    course: Course,
    payload: GradeForecastRequest,
    base_plan: StudyPlanRead,
    target_grade: float,
    evidence_quality: float,
) -> RequiredHoursRead:
    if target_grade <= 0:
        return RequiredHoursRead(
            target_grade=0.0,
            desired_probability=payload.desired_probability,
            estimated_hours=0.0,
            optimistic_hours=0.0,
            conservative_hours=0.0,
            achievable_under_model=True,
            note="A non-positive target is already satisfied by the score scale.",
        )

    reference_hours = base_plan.estimated_hours_to_target
    if reference_hours is None:
        reference_hours = payload.study_hours
    reference_sd = _standard_deviation(
        course.max_grade,
        evidence_quality,
        reference_hours,
    )
    z_score = _inverse_normal_cdf(payload.desired_probability)

    def estimate(width_multiplier: float) -> float | None:
        required_mean = target_grade + z_score * reference_sd * width_multiplier
        return _hours_for_mean_target(db, course, payload, required_mean)

    optimistic = estimate(1.0 - _REQUIRED_HOURS_SENSITIVITY)
    central = estimate(1.0)
    conservative = estimate(1.0 + _REQUIRED_HOURS_SENSITIVITY)
    return RequiredHoursRead(
        target_grade=round(target_grade, 2),
        desired_probability=payload.desired_probability,
        estimated_hours=central,
        optimistic_hours=optimistic,
        conservative_hours=conservative,
        achievable_under_model=central is not None,
        note=(
            "The hour band is a sensitivity range using a ±15% uncertainty-width change; "
            "it is not a statistical confidence interval for study time."
        ),
    )


def _scenario_reads(
    plan: StudyPlanRead,
    target_grade: float,
    max_grade: float,
    evidence_quality: float,
    interval_probability: float,
) -> list[GradeForecastScenarioRead]:
    rows: list[GradeForecastScenarioRead] = []
    for scenario in plan.scenarios:
        standard_deviation = _standard_deviation(
            max_grade,
            evidence_quality,
            scenario.study_hours,
        )
        low, high = _score_interval(
            scenario.projected_grade,
            standard_deviation,
            interval_probability,
            max_grade,
        )
        rows.append(
            GradeForecastScenarioRead(
                study_hours=scenario.study_hours,
                expected_grade=scenario.projected_grade,
                likely_range_low=low,
                likely_range_high=high,
                target_probability=round(
                    _probability_at_or_above(
                        target_grade,
                        scenario.projected_grade,
                        standard_deviation,
                        max_grade,
                    ),
                    4,
                ),
            )
        )
    return rows


def build_grade_forecast(
    db: Session,
    course: Course,
    payload: GradeForecastRequest,
) -> GradeForecastRead:
    target_grade = payload.target_grade if payload.target_grade is not None else course.target_grade
    if target_grade is None:
        raise GradeForecastUnavailableError(
            "Set a target grade on the course or in the forecast request"
        )
    if target_grade > course.max_grade:
        raise GradeForecastUnavailableError("Target grade cannot exceed the course maximum grade")
    if any(threshold > course.max_grade for threshold in payload.thresholds):
        raise GradeForecastUnavailableError("Forecast thresholds cannot exceed the maximum grade")

    calibration = get_course_calibration(db, course.id)
    evidence = _evidence_summary(db, course, payload, calibration)
    plan = build_study_plan(
        db,
        course,
        _plan_request(
            payload,
            target_grade=target_grade,
            available_hours=payload.study_hours,
        ),
    )
    expected_grade = plan.projected_grade_with_available_hours
    if expected_grade is None:
        expected_grade = plan.current_estimated_grade

    standard_deviation = _standard_deviation(
        course.max_grade,
        evidence.quality,
        payload.study_hours,
    )
    low, high = _score_interval(
        expected_grade,
        standard_deviation,
        payload.interval_probability,
        course.max_grade,
    )

    threshold_values = sorted({round(target_grade, 6), *payload.thresholds})
    threshold_rows = [
        GradeThresholdProbabilityRead(
            grade=round(threshold, 2),
            probability_at_or_above=round(
                _probability_at_or_above(
                    threshold,
                    expected_grade,
                    standard_deviation,
                    course.max_grade,
                ),
                4,
            ),
        )
        for threshold in threshold_values
    ]
    target_probability = _probability_at_or_above(
        target_grade,
        expected_grade,
        standard_deviation,
        course.max_grade,
    )

    return GradeForecastRead(
        course_id=course.id,
        forecast_model=_FORECAST_MODEL,
        probability_status=_PROBABILITY_STATUS,
        evidence_quality=evidence.quality,
        evidence_confidence=evidence.confidence,
        study_hours=round(payload.study_hours, 2),
        expected_grade=round(expected_grade, 2),
        standard_deviation=round(standard_deviation, 2),
        interval_probability=payload.interval_probability,
        likely_range_low=low,
        likely_range_high=high,
        target_grade=round(target_grade, 2),
        target_probability=round(target_probability, 4),
        thresholds=threshold_rows,
        required_hours=_required_hours(
            db,
            course,
            payload,
            plan,
            target_grade,
            evidence.quality,
        ),
        scenarios=_scenario_reads(
            plan,
            target_grade,
            course.max_grade,
            evidence.quality,
            payload.interval_probability,
        ),
        assumptions=[
            (
                "The expected score comes from the current heuristic-v5 study planner; the "
                "probability layer does not turn that planner into ground truth."
            ),
            (
                "Score uncertainty uses a bounded planning heuristic around a normal "
                "approximation and contracts as measured evidence quality improves."
            ),
            (
                "Probability outputs are provisional until they are calibrated against "
                "held-out real exam outcomes."
            ),
            (
                "Longer future study horizons add a small uncertainty penalty because "
                "learning-rate projections become less certain farther from observed data."
            ),
        ],
    )
