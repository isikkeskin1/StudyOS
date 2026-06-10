from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import TopicMastery
from app.models.exam_intelligence import ExamTopicStat
from app.schemas.emergency_planning import (
    EmergencyNextActionRead,
    EmergencyPlanRead,
    EmergencyPlanRequest,
    EmergencyStudyBlockRead,
    EmergencyTopicValueRead,
)
from app.schemas.planning import StudyPlanRequest
from app.services.calibration import get_course_calibration
from app.services.mistake_intelligence import topic_mistake_signals
from app.services.planning import (
    PlanningTopic,
    _next_mastery,
    _plan_confidence,
    _resolve_mastery,
    _weighted_mastery,
)

_MAX_TARGET_ESTIMATE_HOURS = 300.0
_RELATIVE_SKIP_FLOOR = 0.25
_OPTIMIZATION_MODEL = "expected-marks-greedy-v1"


class EmergencyPlanUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class _RawBlock:
    topic_id: str
    topic_name: str
    duration_hours: float
    starting_mastery: float
    ending_mastery: float
    expected_mark_gain: float


def _urgency(hours_until_exam: float | None) -> str:
    if hours_until_exam is None:
        return "unknown"
    if hours_until_exam <= 12:
        return "critical"
    if hours_until_exam <= 24:
        return "high"
    if hours_until_exam <= 72:
        return "elevated"
    return "standard"


def _expected_mark_gain(
    topic: PlanningTopic,
    mastery_value: float,
    hours: float,
    max_grade: float,
) -> tuple[float, float]:
    next_mastery = _next_mastery(
        mastery_value,
        hours,
        topic.learning_scale_hours,
    )
    gain = topic.weight * (next_mastery - mastery_value) * max_grade
    return max(0.0, gain), next_mastery


def _load_topics(
    db: Session,
    course: Course,
    request: EmergencyPlanRequest,
) -> tuple[list[PlanningTopic], dict[str, TopicMastery], datetime]:
    topics = list(
        db.scalars(
            select(CourseTopic)
            .where(CourseTopic.course_id == course.id)
            .order_by(CourseTopic.importance_score.desc())
        ).all()
    )
    if not topics:
        raise EmergencyPlanUnavailableError(
            "Analyze the course before generating an emergency plan"
        )

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

    planning_request = StudyPlanRequest(
        target_grade=request.target_grade,
        available_hours=request.available_hours,
        baseline_mastery=request.baseline_mastery,
        topic_mastery=request.topic_mastery,
        use_stored_mastery=request.use_stored_mastery,
    )

    planning_topics: list[PlanningTopic] = []
    for topic in topics:
        calibration = calibration_by_id.get(topic.id)
        mastery = _resolve_mastery(
            topic,
            planning_request,
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
    return planning_topics, stored_mastery, as_of


def _optimize(
    topics: list[PlanningTopic],
    hours: float,
    max_grade: float,
    block_hours: float,
) -> tuple[list[_RawBlock], dict[str, float], dict[str, float], dict[str, float]]:
    mastery = {topic.id: topic.mastery for topic in topics}
    allocations = {topic.id: 0.0 for topic in topics}
    gains = {topic.id: 0.0 for topic in topics}
    blocks: list[_RawBlock] = []
    remaining = max(0.0, hours)

    while remaining > 1e-9:
        duration = min(block_hours, remaining)
        candidates: list[tuple[float, PlanningTopic, float]] = []
        for topic in topics:
            gain, next_mastery = _expected_mark_gain(
                topic,
                mastery[topic.id],
                duration,
                max_grade,
            )
            candidates.append((gain, topic, next_mastery))
        gain, best, next_mastery = max(candidates, key=lambda item: item[0])
        start_mastery = mastery[best.id]
        mastery[best.id] = next_mastery
        allocations[best.id] += duration
        gains[best.id] += gain
        blocks.append(
            _RawBlock(
                topic_id=best.id,
                topic_name=best.name,
                duration_hours=duration,
                starting_mastery=start_mastery,
                ending_mastery=next_mastery,
                expected_mark_gain=gain,
            )
        )
        remaining -= duration

    return blocks, mastery, allocations, gains


def _hours_to_target(
    topics: list[PlanningTopic],
    target_ratio: float,
    max_grade: float,
    block_hours: float,
) -> float | None:
    mastery = {topic.id: topic.mastery for topic in topics}
    if _weighted_mastery(topics, mastery) >= target_ratio:
        return 0.0

    elapsed = 0.0
    while elapsed < _MAX_TARGET_ESTIMATE_HOURS - 1e-9:
        duration = min(block_hours, _MAX_TARGET_ESTIMATE_HOURS - elapsed)
        choices: list[tuple[float, PlanningTopic, float]] = []
        for topic in topics:
            gain, next_mastery = _expected_mark_gain(
                topic,
                mastery[topic.id],
                duration,
                max_grade,
            )
            choices.append((gain, topic, next_mastery))
        _, best, next_mastery = max(choices, key=lambda item: item[0])
        mastery[best.id] = next_mastery
        elapsed += duration
        if _weighted_mastery(topics, mastery) >= target_ratio:
            return round(elapsed, 2)
    return None


def _schedule_reads(blocks: list[_RawBlock]) -> list[EmergencyStudyBlockRead]:
    if not blocks:
        return []

    grouped: list[_RawBlock] = []
    for block in blocks:
        if grouped and grouped[-1].topic_id == block.topic_id:
            previous = grouped[-1]
            grouped[-1] = _RawBlock(
                topic_id=previous.topic_id,
                topic_name=previous.topic_name,
                duration_hours=previous.duration_hours + block.duration_hours,
                starting_mastery=previous.starting_mastery,
                ending_mastery=block.ending_mastery,
                expected_mark_gain=previous.expected_mark_gain + block.expected_mark_gain,
            )
        else:
            grouped.append(block)

    rows: list[EmergencyStudyBlockRead] = []
    cumulative = 0.0
    for index, block in enumerate(grouped, start=1):
        cumulative += block.expected_mark_gain
        rows.append(
            EmergencyStudyBlockRead(
                sequence=index,
                topic_id=block.topic_id,
                topic_name=block.topic_name,
                duration_minutes=round(block.duration_hours * 60),
                starting_mastery=round(block.starting_mastery, 4),
                ending_mastery=round(block.ending_mastery, 4),
                expected_mark_gain=round(block.expected_mark_gain, 3),
                expected_marks_per_hour=round(
                    block.expected_mark_gain / block.duration_hours,
                    3,
                ),
                cumulative_expected_mark_gain=round(cumulative, 3),
            )
        )
    return rows


def build_emergency_plan(
    db: Session,
    course: Course,
    request: EmergencyPlanRequest,
) -> EmergencyPlanRead:
    target_grade = request.target_grade if request.target_grade is not None else course.target_grade
    if target_grade is None:
        raise EmergencyPlanUnavailableError(
            "Set a target grade on the course or in the emergency-plan request"
        )
    if target_grade > course.max_grade:
        raise EmergencyPlanUnavailableError("Target grade cannot exceed the course maximum grade")

    topics, stored_mastery, as_of = _load_topics(db, course, request)
    block_hours = request.block_minutes / 60.0
    current_mastery = {topic.id: topic.mastery for topic in topics}
    current_grade = _weighted_mastery(topics, current_mastery) * course.max_grade

    raw_blocks, projected_mastery, allocations, gains = _optimize(
        topics,
        request.available_hours,
        course.max_grade,
        block_hours,
    )
    projected_grade = _weighted_mastery(topics, projected_mastery) * course.max_grade
    total_gain = max(0.0, projected_grade - current_grade)

    initial_mph: dict[str, float] = {}
    next_block_gain: dict[str, float] = {}
    next_hour_gain: dict[str, float] = {}
    for topic in topics:
        block_gain, _ = _expected_mark_gain(
            topic,
            topic.mastery,
            block_hours,
            course.max_grade,
        )
        hour_gain, _ = _expected_mark_gain(
            topic,
            topic.mastery,
            1.0,
            course.max_grade,
        )
        next_block_gain[topic.id] = block_gain
        next_hour_gain[topic.id] = hour_gain
        initial_mph[topic.id] = hour_gain

    top_initial_mph = max(initial_mph.values(), default=0.0)
    skip_cutoff = max(
        request.skip_threshold_marks_per_hour,
        top_initial_mph * _RELATIVE_SKIP_FLOOR,
    )

    topic_rows: list[EmergencyTopicValueRead] = []
    for topic in topics:
        allocated = allocations[topic.id]
        gain = gains[topic.id]
        post_gain, _ = _expected_mark_gain(
            topic,
            projected_mastery[topic.id],
            block_hours,
            course.max_grade,
        )
        post_mph = post_gain / block_hours
        if allocated > 1e-9:
            decision = "study"
            reason = (
                f"Allocated {allocated:.2f}h because its marginal expected-mark return "
                "was competitive inside the available time budget."
            )
        elif initial_mph[topic.id] < skip_cutoff:
            decision = "skip"
            reason = (
                f"Initial return {initial_mph[topic.id]:.2f} marks/hour is below the "
                f"emergency cutoff of {skip_cutoff:.2f}."
            )
        else:
            decision = "defer"
            reason = (
                "Potential return is above the skip cutoff, but stronger topics consumed the "
                "current time budget."
            )

        topic_rows.append(
            EmergencyTopicValueRead(
                topic_id=topic.id,
                topic_name=topic.name,
                exam_weight=round(topic.weight, 4),
                current_mastery=round(topic.mastery, 4),
                mastery_source=topic.mastery_source,
                allocated_hours=round(allocated, 2),
                expected_mark_gain=round(gain, 3),
                average_marks_per_hour=round(gain / allocated, 3) if allocated > 1e-9 else 0.0,
                next_block_expected_mark_gain=round(next_block_gain[topic.id], 3),
                next_hour_expected_mark_gain=round(next_hour_gain[topic.id], 3),
                initial_marks_per_hour=round(initial_mph[topic.id], 3),
                post_plan_marginal_marks_per_hour=round(post_mph, 3),
                decision=decision,
                decision_reason=reason,
                mistake_focus=topic.mistake_focus,
                learning_scale_hours=round(topic.learning_scale_hours, 3),
                calibration_source=topic.calibration_source,
            )
        )

    decision_order = {"study": 0, "defer": 1, "skip": 2}
    topic_rows.sort(
        key=lambda item: (
            decision_order[item.decision],
            -item.expected_mark_gain,
            -item.initial_marks_per_hour,
        )
    )

    schedule = _schedule_reads(raw_blocks)
    next_action = None
    if schedule:
        first = schedule[0]
        next_action = EmergencyNextActionRead(
            topic_id=first.topic_id,
            topic_name=first.topic_name,
            duration_minutes=first.duration_minutes,
            expected_mark_gain=first.expected_mark_gain,
            expected_marks_per_hour=first.expected_marks_per_hour,
        )

    estimated_hours = _hours_to_target(
        topics,
        target_grade / course.max_grade,
        course.max_grade,
        block_hours,
    )

    return EmergencyPlanRead(
        course_id=course.id,
        optimization_model=_OPTIMIZATION_MODEL,
        confidence=_plan_confidence(topics, stored_mastery, as_of),
        urgency=_urgency(request.hours_until_exam),
        hours_until_exam=request.hours_until_exam,
        available_hours=round(request.available_hours, 2),
        block_minutes=request.block_minutes,
        target_grade=round(target_grade, 2),
        max_grade=round(course.max_grade, 2),
        current_estimated_grade=round(current_grade, 2),
        projected_grade=round(projected_grade, 2),
        expected_mark_gain=round(total_gain, 2),
        target_gap_before=round(max(0.0, target_grade - current_grade), 2),
        target_gap_after=round(max(0.0, target_grade - projected_grade), 2),
        target_reachable_with_available_time=projected_grade >= target_grade,
        estimated_hours_to_target=estimated_hours,
        emergency_skip_cutoff_marks_per_hour=round(skip_cutoff, 3),
        next_action=next_action,
        schedule=schedule,
        topics=topic_rows,
        assumptions=[
            (
                "Expected marks are heuristic marginal gains from exam/topic weight, current "
                "effective mastery, and the calibrated learning curve; they are not "
                "guaranteed marks."
            ),
            (
                "Mistake patterns remain visible for teaching focus but do not inflate the numeric "
                "expected-mark estimate."
            ),
            (
                "The optimizer greedily assigns each study block to the topic with the largest "
                "current expected mark gain, so diminishing returns can move later blocks "
                "elsewhere."
            ),
            (
                "Current mastery is already retention-adjusted when stored evidence exists; this "
                "short-horizon model does not add extra forgetting, fatigue, or context-switch "
                "costs."
            ),
            (
                "Topics below the emergency cutoff are marked skip only for this time budget, "
                "not as permanently unimportant course material."
            ),
        ],
    )
