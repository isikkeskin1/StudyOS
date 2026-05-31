from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import TopicMastery
from app.models.exam_intelligence import ExamTopicStat
from app.schemas.planning import (
    GradeScenarioRead,
    StudyPlanRead,
    StudyPlanRequest,
    TopicStudyAllocationRead,
)
from app.services.calibration import TopicCalibration, get_course_calibration
from app.services.mistake_intelligence import topic_mistake_signals
from app.services.retention import RetentionSnapshot, retention_snapshot

_STEP_HOURS = 0.25
_MAX_ESTIMATE_HOURS = 300.0
_MISTAKE_PRIORITY_BOOST = 0.35


class StudyPlanUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class MasteryResolution:
    value: float
    source: str
    raw_value: float | None
    retention: RetentionSnapshot | None


@dataclass(frozen=True)
class PlanningTopic:
    id: str
    name: str
    weight: float
    mastery: float
    mastery_source: str
    raw_mastery: float | None
    retention: RetentionSnapshot | None
    mistake_burden: float
    mistake_focus: list[str]
    learning_rate_multiplier: float
    learning_scale_hours: float
    learning_calibration_confidence: str
    retention_calibration_confidence: str
    calibration_source: str


def _next_mastery(current: float, hours: float, learning_scale_hours: float) -> float:
    if hours <= 0:
        return current
    scale = max(0.5, learning_scale_hours)
    return 1.0 - (1.0 - current) * math.exp(-hours / scale)


def _weighted_mastery(topics: list[PlanningTopic], mastery: dict[str, float]) -> float:
    return sum(topic.weight * mastery[topic.id] for topic in topics)


def _marginal_priority(topic: PlanningTopic, mastery_value: float) -> float:
    mistake_factor = 1.0 + _MISTAKE_PRIORITY_BOOST * topic.mistake_burden
    return (
        topic.weight
        * (1.0 - mastery_value)
        * mistake_factor
        / max(0.5, topic.learning_scale_hours)
    )


def _allocate(
    topics: list[PlanningTopic],
    hours: float,
) -> tuple[dict[str, float], dict[str, float]]:
    allocations = {topic.id: 0.0 for topic in topics}
    mastery = {topic.id: topic.mastery for topic in topics}
    remaining = max(0.0, hours)

    while remaining >= _STEP_HOURS - 1e-9:
        best = max(
            topics,
            key=lambda topic: _marginal_priority(topic, mastery[topic.id]),
        )
        allocations[best.id] += _STEP_HOURS
        mastery[best.id] = _next_mastery(
            mastery[best.id],
            _STEP_HOURS,
            best.learning_scale_hours,
        )
        remaining -= _STEP_HOURS

    if remaining > 1e-6:
        best = max(
            topics,
            key=lambda topic: _marginal_priority(topic, mastery[topic.id]),
        )
        allocations[best.id] += remaining
        mastery[best.id] = _next_mastery(
            mastery[best.id],
            remaining,
            best.learning_scale_hours,
        )

    return allocations, mastery


def _hours_to_target(topics: list[PlanningTopic], target_ratio: float) -> float | None:
    mastery = {topic.id: topic.mastery for topic in topics}
    if _weighted_mastery(topics, mastery) >= target_ratio:
        return 0.0

    elapsed = 0.0
    while elapsed < _MAX_ESTIMATE_HOURS:
        best = max(
            topics,
            key=lambda topic: _marginal_priority(topic, mastery[topic.id]),
        )
        mastery[best.id] = _next_mastery(
            mastery[best.id],
            _STEP_HOURS,
            best.learning_scale_hours,
        )
        elapsed += _STEP_HOURS
        if _weighted_mastery(topics, mastery) >= target_ratio:
            return round(elapsed, 2)
    return None


def _projection(topics: list[PlanningTopic], hours: float, max_grade: float) -> float:
    _, mastery = _allocate(topics, hours)
    return round(_weighted_mastery(topics, mastery) * max_grade, 2)


def _resolve_mastery(
    topic: CourseTopic,
    request: StudyPlanRequest,
    stored: dict[str, TopicMastery],
    as_of: datetime,
    calibration: TopicCalibration | None,
) -> MasteryResolution:
    if topic.id in request.topic_mastery:
        return MasteryResolution(request.topic_mastery[topic.id], "override", None, None)
    if topic.normalized_name in request.topic_mastery:
        return MasteryResolution(
            request.topic_mastery[topic.normalized_name],
            "override",
            None,
            None,
        )
    if request.use_stored_mastery and topic.id in stored:
        half_life = calibration.retention_half_life_days if calibration is not None else None
        snapshot = retention_snapshot(
            stored[topic.id],
            as_of=as_of,
            half_life_days=half_life,
        )
        return MasteryResolution(
            snapshot.effective_mastery,
            "diagnostic",
            snapshot.raw_mastery,
            snapshot,
        )
    return MasteryResolution(request.baseline_mastery, "baseline", None, None)


def _plan_confidence(
    topics: list[PlanningTopic],
    stored: dict[str, TopicMastery],
    as_of: datetime,
) -> str:
    diagnostic_topics = [topic for topic in topics if topic.mastery_source == "diagnostic"]
    if not diagnostic_topics:
        return "low"

    coverage = len(diagnostic_topics) / len(topics)
    effective_confidence: list[float] = []
    for topic in diagnostic_topics:
        half_life = (
            topic.retention.half_life_days if topic.retention is not None else None
        )
        effective_confidence.append(
            retention_snapshot(
                stored[topic.id],
                as_of=as_of,
                half_life_days=half_life,
            ).effective_confidence
        )
    average_confidence = sum(effective_confidence) / len(effective_confidence)
    if coverage >= 0.5 and average_confidence >= 0.35:
        return "medium"
    return "low"


def build_study_plan(db: Session, course: Course, request: StudyPlanRequest) -> StudyPlanRead:
    topics = list(
        db.scalars(
            select(CourseTopic)
            .where(CourseTopic.course_id == course.id)
            .order_by(CourseTopic.importance_score.desc())
        ).all()
    )
    if not topics:
        raise StudyPlanUnavailableError("Analyze the course before generating a study plan")

    target_grade = request.target_grade if request.target_grade is not None else course.target_grade
    if target_grade is None:
        raise StudyPlanUnavailableError("Set a target grade on the course or in the plan request")
    if target_grade > course.max_grade:
        raise StudyPlanUnavailableError("Target grade cannot exceed the course maximum grade")

    exam_stats = {
        stat.topic_id: stat
        for stat in db.scalars(
            select(ExamTopicStat).where(ExamTopicStat.course_id == course.id)
        ).all()
    }
    stored_mastery = {
        item.topic_id: item
        for item in db.scalars(
            select(TopicMastery).where(TopicMastery.course_id == course.id)
        ).all()
    }
    mistake_signals = topic_mistake_signals(db, course.id)
    course_calibration = get_course_calibration(db, course.id)
    calibration_by_id = {item.topic_id: item for item in course_calibration.topics}
    as_of = datetime.now(UTC)

    raw_weights: dict[str, float] = {}
    for topic in topics:
        exam_weight = exam_stats[topic.id].exam_weight if topic.id in exam_stats else 0.0
        raw_weights[topic.id] = (
            0.65 * exam_weight + 0.35 * topic.importance_score
            if exam_stats
            else topic.importance_score
        )
    total_weight = sum(raw_weights.values()) or float(len(topics))

    planning_topics: list[PlanningTopic] = []
    for topic in topics:
        calibration = calibration_by_id.get(topic.id)
        mastery = _resolve_mastery(
            topic,
            request,
            stored_mastery,
            as_of,
            calibration,
        )
        mistake_burden, mistake_focus = mistake_signals.get(topic.id, (0.0, []))
        planning_topics.append(
            PlanningTopic(
                id=topic.id,
                name=topic.name,
                weight=raw_weights[topic.id] / total_weight,
                mastery=mastery.value,
                mastery_source=mastery.source,
                raw_mastery=mastery.raw_value,
                retention=mastery.retention,
                mistake_burden=mistake_burden,
                mistake_focus=mistake_focus,
                learning_rate_multiplier=(
                    calibration.learning_rate_multiplier if calibration is not None else 1.0
                ),
                learning_scale_hours=(
                    calibration.learning_scale_hours if calibration is not None else 2.8
                ),
                learning_calibration_confidence=(
                    calibration.learning_confidence if calibration is not None else "low"
                ),
                retention_calibration_confidence=(
                    calibration.retention_confidence if calibration is not None else "low"
                ),
                calibration_source=(
                    calibration.calibration_source if calibration is not None else "heuristic"
                ),
            )
        )

    target_ratio = target_grade / course.max_grade
    current_mastery = {topic.id: topic.mastery for topic in planning_topics}
    current_grade = round(
        _weighted_mastery(planning_topics, current_mastery) * course.max_grade,
        2,
    )
    estimated_hours = _hours_to_target(planning_topics, target_ratio)

    planning_hours = (
        request.available_hours
        if request.available_hours is not None
        else (estimated_hours if estimated_hours is not None else 0.0)
    )
    allocations, projected_mastery = _allocate(planning_topics, planning_hours)

    allocation_rows = [
        TopicStudyAllocationRead(
            topic_id=topic.id,
            topic_name=topic.name,
            exam_weight=round(topic.weight, 4),
            current_mastery=round(topic.mastery, 4),
            mastery_source=topic.mastery_source,
            raw_mastery=topic.raw_mastery,
            forgetting_loss=(
                topic.retention.forgetting_loss if topic.retention is not None else 0.0
            ),
            forgetting_risk=(
                topic.retention.forgetting_risk if topic.retention is not None else None
            ),
            days_since_evidence=(
                topic.retention.days_since_evidence if topic.retention is not None else None
            ),
            retention_half_life_days=(
                topic.retention.half_life_days if topic.retention is not None else None
            ),
            projected_mastery=round(projected_mastery[topic.id], 4),
            recommended_hours=round(allocations[topic.id], 2),
            priority_score=round(
                _marginal_priority(topic, topic.mastery) * topic.learning_scale_hours,
                4,
            ),
            mistake_burden=round(topic.mistake_burden, 4),
            mistake_focus=topic.mistake_focus,
            learning_rate_multiplier=topic.learning_rate_multiplier,
            learning_scale_hours=topic.learning_scale_hours,
            learning_calibration_confidence=topic.learning_calibration_confidence,
            retention_calibration_confidence=topic.retention_calibration_confidence,
            calibration_source=topic.calibration_source,
        )
        for topic in planning_topics
        if allocations[topic.id] > 0 or topic.weight >= 0.05
    ]
    allocation_rows.sort(
        key=lambda item: (item.recommended_hours, item.priority_score),
        reverse=True,
    )

    scenario_hours = {0.0, 5.0, 10.0, 15.0, 20.0, 30.0}
    if estimated_hours is not None:
        scenario_hours.add(estimated_hours)
    if request.available_hours is not None:
        scenario_hours.add(request.available_hours)

    scenarios: list[GradeScenarioRead] = []
    for hours in sorted(scenario_hours):
        if hours > _MAX_ESTIMATE_HOURS:
            continue
        projected = _projection(planning_topics, hours, course.max_grade)
        scenarios.append(
            GradeScenarioRead(
                study_hours=round(hours, 2),
                projected_grade=projected,
                projected_ratio=round(projected / course.max_grade, 4),
            )
        )

    projected_grade = (
        _projection(planning_topics, request.available_hours, course.max_grade)
        if request.available_hours is not None
        else None
    )
    reachable = projected_grade >= target_grade if projected_grade is not None else None
    used_diagnostics = any(topic.mastery_source == "diagnostic" for topic in planning_topics)
    used_mistakes = any(topic.mistake_burden > 0 for topic in planning_topics)
    used_learning_calibration = course_calibration.calibrated_learning_topic_count > 0
    used_retention_calibration = course_calibration.calibrated_retention_topic_count > 0

    assumptions = [
        (
            "Exam weights use extracted past-paper marks when available and "
            "topic importance otherwise."
        ),
        "Grade projections are planning heuristics, not calibrated predictions or guarantees.",
        (
            "Personalized learning rates are relative adjustments inferred from mastery "
            "history and are shrunk toward the generic curve when evidence is sparse."
        ),
    ]
    if used_diagnostics:
        assumptions.insert(
            0,
            (
                "Measured diagnostic mastery is discounted by a forgetting curve based on "
                "evidence age, confidence, and calibrated retention when available."
            ),
        )
    else:
        assumptions.insert(
            0,
            "No diagnostic evidence is available yet, so baseline mastery is used.",
        )
    if used_mistakes:
        assumptions.append(
            "Classified mistake patterns adjust study priority but do not directly change grades."
        )
    if used_learning_calibration:
        assumptions.append(
            "At least one topic uses observed learning responsiveness from mastery history."
        )
    if used_retention_calibration:
        assumptions.append(
            "At least one retention half-life is blended with time-separated performance evidence."
        )

    return StudyPlanRead(
        course_id=course.id,
        planning_model="heuristic-v5",
        confidence=_plan_confidence(planning_topics, stored_mastery, as_of),
        target_grade=round(target_grade, 2),
        max_grade=round(course.max_grade, 2),
        current_estimated_grade=current_grade,
        estimated_hours_to_target=estimated_hours,
        available_hours=request.available_hours,
        projected_grade_with_available_hours=projected_grade,
        target_reachable_with_available_time=reachable,
        calibrated_learning_topic_count=course_calibration.calibrated_learning_topic_count,
        calibrated_retention_topic_count=course_calibration.calibrated_retention_topic_count,
        allocations=allocation_rows,
        scenarios=scenarios,
        assumptions=assumptions,
    )
