from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.course import Course
from app.schemas.emergency_planning import EmergencyPlanRequest
from app.schemas.multi_course_planning import (
    MultiCourseCourseRead,
    MultiCourseCourseRequest,
    MultiCoursePlanRead,
    MultiCoursePlanRequest,
    MultiCourseStudyBlockRead,
)
from app.services.emergency_planning import (
    _expected_mark_gain,
    _hours_to_target,
    _load_topics,
)
from app.services.planning import PlanningTopic, _plan_confidence, _weighted_mastery

_OPTIMIZATION_MODEL = "normalized-target-utility-greedy-v1"
_CONFIDENCE_MULTIPLIERS = {"low": 0.80, "medium": 0.90, "high": 1.00}


class MultiCoursePlanUnavailableError(RuntimeError):
    pass


class MultiCourseCourseNotFoundError(RuntimeError):
    pass


@dataclass
class _CourseState:
    course: Course
    request: MultiCourseCourseRequest
    topics: list[PlanningTopic]
    mastery: dict[str, float]
    target_grade: float
    current_grade: float
    projected_grade: float
    plan_confidence: str
    confidence_multiplier: float
    deadline_source: str
    hours_until_exam: float | None
    days_until_exam: int | None
    estimated_hours_to_target_before: float | None
    allocated_hours: float = 0.0


@dataclass(frozen=True)
class _Candidate:
    state: _CourseState
    topic: PlanningTopic
    duration_hours: float
    next_mastery: float
    expected_mark_gain: float
    normalized_target_gap_reduction: float
    deadline_multiplier: float
    utility_score: float


def _resolve_deadline(
    course: Course,
    request: MultiCourseCourseRequest,
    as_of: datetime,
) -> tuple[str, float | None, int | None]:
    days_until_exam = None
    if course.exam_date is not None:
        days_until_exam = (course.exam_date - as_of.date()).days
    if request.hours_until_exam is not None:
        return "request_hours", request.hours_until_exam, days_until_exam
    if course.exam_date is not None:
        return "course_exam_date", None, days_until_exam
    return "unknown", None, None


def _date_deadline_multiplier(days_until_exam: int | None) -> float:
    if days_until_exam is None:
        return 1.0
    if days_until_exam < 0:
        return 0.0
    if days_until_exam == 0:
        return 1.60
    if days_until_exam == 1:
        return 1.40
    if days_until_exam <= 3:
        return 1.25
    if days_until_exam <= 7:
        return 1.12
    return 1.0


def _deadline_multiplier(
    state: _CourseState,
    *,
    elapsed_hours: float,
    block_hours: float,
) -> float:
    if state.deadline_source == "course_exam_date":
        return _date_deadline_multiplier(state.days_until_exam)
    if state.hours_until_exam is None:
        return 1.0

    remaining = max(0.0, state.hours_until_exam - elapsed_hours)
    if remaining <= 1e-9:
        return 0.0
    time_pressure = 24.0 / (remaining + 24.0)
    required = state.estimated_hours_to_target_before
    work_pressure = 0.0
    if required is not None and required > 0:
        work_pressure = min(2.0, required / max(remaining, block_hours))
    return min(2.15, 1.0 + 0.45 * time_pressure + 0.35 * work_pressure)


def _course_candidate(
    state: _CourseState,
    *,
    duration_hours: float,
    elapsed_hours: float,
) -> _Candidate | None:
    gap = max(0.0, state.target_grade - state.projected_grade)
    if gap <= 1e-9:
        return None

    if state.hours_until_exam is not None:
        remaining = state.hours_until_exam - elapsed_hours
        if remaining + 1e-9 < duration_hours:
            return None
    if state.deadline_source == "course_exam_date" and (state.days_until_exam or 0) < 0:
        return None

    deadline_multiplier = _deadline_multiplier(
        state,
        elapsed_hours=elapsed_hours,
        block_hours=duration_hours,
    )
    if deadline_multiplier <= 0:
        return None

    choices: list[tuple[float, PlanningTopic, float]] = []
    for topic in state.topics:
        gain, next_mastery = _expected_mark_gain(
            topic,
            state.mastery[topic.id],
            duration_hours,
            state.course.max_grade,
        )
        choices.append((gain, topic, next_mastery))
    if not choices:
        return None

    gain, best_topic, next_mastery = max(choices, key=lambda item: item[0])
    target_reduction = min(gain, gap)
    normalized_reduction = target_reduction / state.course.max_grade
    utility_score = (
        normalized_reduction * deadline_multiplier * state.confidence_multiplier
    )
    if utility_score <= 1e-12:
        return None
    return _Candidate(
        state=state,
        topic=best_topic,
        duration_hours=duration_hours,
        next_mastery=next_mastery,
        expected_mark_gain=gain,
        normalized_target_gap_reduction=normalized_reduction,
        deadline_multiplier=deadline_multiplier,
        utility_score=utility_score,
    )


def _load_course_state(
    db: Session,
    request: MultiCourseCourseRequest,
    *,
    block_hours: float,
    as_of: datetime,
) -> _CourseState:
    course = db.get(Course, request.course_id)
    if course is None:
        raise MultiCourseCourseNotFoundError(
            f"Course {request.course_id} was not found"
        )

    target_grade = request.target_grade if request.target_grade is not None else course.target_grade
    if target_grade is None:
        raise MultiCoursePlanUnavailableError(
            f"Set a target grade for course '{course.name}' or provide a request override"
        )
    if target_grade > course.max_grade:
        raise MultiCoursePlanUnavailableError(
            f"Target grade for course '{course.name}' cannot exceed its maximum grade"
        )

    emergency_request = EmergencyPlanRequest(
        available_hours=block_hours,
        target_grade=target_grade,
        hours_until_exam=request.hours_until_exam,
        block_minutes=round(block_hours * 60),
        baseline_mastery=request.baseline_mastery,
        topic_mastery=request.topic_mastery,
        use_stored_mastery=request.use_stored_mastery,
    )
    topics, stored_mastery, mastery_as_of = _load_topics(db, course, emergency_request)
    mastery = {topic.id: topic.mastery for topic in topics}
    current_grade = _weighted_mastery(topics, mastery) * course.max_grade
    plan_confidence = _plan_confidence(topics, stored_mastery, mastery_as_of)
    confidence_multiplier = _CONFIDENCE_MULTIPLIERS.get(plan_confidence, 0.80)
    deadline_source, hours_until_exam, days_until_exam = _resolve_deadline(
        course,
        request,
        as_of,
    )
    estimated_hours = _hours_to_target(
        topics,
        target_grade / course.max_grade,
        course.max_grade,
        block_hours,
    )

    return _CourseState(
        course=course,
        request=request,
        topics=topics,
        mastery=mastery,
        target_grade=target_grade,
        current_grade=current_grade,
        projected_grade=current_grade,
        plan_confidence=plan_confidence,
        confidence_multiplier=confidence_multiplier,
        deadline_source=deadline_source,
        hours_until_exam=hours_until_exam,
        days_until_exam=days_until_exam,
        estimated_hours_to_target_before=estimated_hours,
    )


def build_multi_course_plan(
    db: Session,
    request: MultiCoursePlanRequest,
) -> MultiCoursePlanRead:
    block_hours = request.block_minutes / 60.0
    as_of = datetime.now(UTC)
    states = [
        _load_course_state(
            db,
            course_request,
            block_hours=block_hours,
            as_of=as_of,
        )
        for course_request in request.courses
    ]

    initial_candidates: dict[str, _Candidate | None] = {
        state.course.id: _course_candidate(
            state,
            duration_hours=min(block_hours, request.available_hours),
            elapsed_hours=0.0,
        )
        for state in states
    }
    initial_deadline_multipliers = {
        state.course.id: _deadline_multiplier(
            state,
            elapsed_hours=0.0,
            block_hours=block_hours,
        )
        for state in states
    }

    raw_schedule: list[tuple[_Candidate, float]] = []
    remaining = request.available_hours
    elapsed = 0.0
    total_utility = 0.0

    while remaining > 1e-9:
        duration = min(block_hours, remaining)
        candidates = [
            candidate
            for state in states
            if (
                candidate := _course_candidate(
                    state,
                    duration_hours=duration,
                    elapsed_hours=elapsed,
                )
            )
            is not None
        ]
        if not candidates:
            break

        best = max(
            candidates,
            key=lambda item: (
                item.utility_score,
                item.normalized_target_gap_reduction,
                item.expected_mark_gain / item.state.course.max_grade,
            ),
        )
        best.state.mastery[best.topic.id] = best.next_mastery
        best.state.projected_grade = (
            _weighted_mastery(best.state.topics, best.state.mastery)
            * best.state.course.max_grade
        )
        best.state.allocated_hours += duration
        total_utility += best.utility_score
        raw_schedule.append((best, total_utility))
        remaining -= duration
        elapsed += duration

    schedule: list[MultiCourseStudyBlockRead] = []
    for sequence, (candidate, cumulative_utility) in enumerate(raw_schedule, start=1):
        state = candidate.state
        schedule.append(
            MultiCourseStudyBlockRead(
                sequence=sequence,
                course_id=state.course.id,
                course_name=state.course.name,
                topic_id=candidate.topic.id,
                topic_name=candidate.topic.name,
                duration_minutes=round(candidate.duration_hours * 60),
                expected_mark_gain=round(candidate.expected_mark_gain, 3),
                normalized_target_gap_reduction=round(
                    candidate.normalized_target_gap_reduction,
                    5,
                ),
                deadline_multiplier=round(candidate.deadline_multiplier, 4),
                confidence_multiplier=round(state.confidence_multiplier, 4),
                utility_score=round(candidate.utility_score, 6),
                cumulative_utility_score=round(cumulative_utility, 6),
                projected_course_grade=round(state.projected_grade, 2),
                remaining_target_gap=round(
                    max(0.0, state.target_grade - state.projected_grade),
                    2,
                ),
            )
        )

    course_rows: list[MultiCourseCourseRead] = []
    for state in states:
        initial = initial_candidates[state.course.id]
        initial_gain = initial.expected_mark_gain if initial is not None else 0.0
        initial_normalized = (
            initial.normalized_target_gap_reduction if initial is not None else 0.0
        )
        initial_utility = initial.utility_score if initial is not None else 0.0
        initial_duration = initial.duration_hours if initial is not None else block_hours
        course_rows.append(
            MultiCourseCourseRead(
                course_id=state.course.id,
                course_name=state.course.name,
                exam_date=state.course.exam_date,
                deadline_source=state.deadline_source,
                hours_until_exam=(
                    round(state.hours_until_exam, 2)
                    if state.hours_until_exam is not None
                    else None
                ),
                days_until_exam=state.days_until_exam,
                target_grade=round(state.target_grade, 2),
                max_grade=round(state.course.max_grade, 2),
                current_estimated_grade=round(state.current_grade, 2),
                projected_grade=round(state.projected_grade, 2),
                expected_mark_gain=round(
                    max(0.0, state.projected_grade - state.current_grade),
                    2,
                ),
                target_gap_before=round(
                    max(0.0, state.target_grade - state.current_grade),
                    2,
                ),
                target_gap_after=round(
                    max(0.0, state.target_grade - state.projected_grade),
                    2,
                ),
                target_reached=state.projected_grade >= state.target_grade,
                allocated_hours=round(state.allocated_hours, 2),
                plan_confidence=state.plan_confidence,
                confidence_multiplier=round(state.confidence_multiplier, 4),
                initial_deadline_multiplier=round(
                    initial_deadline_multipliers[state.course.id],
                    4,
                ),
                initial_best_block_expected_mark_gain=round(initial_gain, 3),
                initial_best_block_normalized_target_reduction=round(
                    initial_normalized,
                    5,
                ),
                initial_utility_per_hour=round(
                    initial_utility / initial_duration if initial_duration > 0 else 0.0,
                    6,
                ),
                estimated_hours_to_target_before=state.estimated_hours_to_target_before,
            )
        )

    course_rows.sort(key=lambda item: (-item.allocated_hours, item.course_name.lower()))
    total_gap_before = sum(
        max(0.0, state.target_grade - state.current_grade) / state.course.max_grade
        for state in states
    )
    total_gap_after = sum(
        max(0.0, state.target_grade - state.projected_grade) / state.course.max_grade
        for state in states
    )
    allocated_hours = request.available_hours - remaining

    return MultiCoursePlanRead(
        optimization_model=_OPTIMIZATION_MODEL,
        available_hours=round(request.available_hours, 2),
        allocated_hours=round(allocated_hours, 2),
        unallocated_hours=round(remaining, 2),
        block_minutes=request.block_minutes,
        total_normalized_target_gap_before=round(total_gap_before, 5),
        total_normalized_target_gap_after=round(total_gap_after, 5),
        total_normalized_target_gap_reduction=round(
            max(0.0, total_gap_before - total_gap_after),
            5,
        ),
        total_utility_score=round(total_utility, 6),
        next_action=schedule[0] if schedule else None,
        schedule=schedule,
        courses=course_rows,
        assumptions=[
            (
                "Cross-course utility is based on normalized reduction in each course's remaining "
                "target gap, so raw marks from different grading scales are not compared directly."
            ),
            (
                "Exact hours_until_exam values are hard scheduling cutoffs. Course exam_date "
                "values are date-only and therefore provide coarse urgency weighting, not an "
                "invented exam time."
            ),
            (
                "Deadline pressure increases near an exam and when the estimated hours needed to "
                "reach the target consume a large share of the remaining exact horizon."
            ),
            (
                "Low-confidence expected gains are conservatively shrunk. Study projections remain "
                "planning estimates and do not write synthetic mastery evidence."
            ),
            (
                "A course stops receiving scarce time once its target is reached. Any leftover "
                "time is returned as unallocated rather than silently optimizing beyond the "
                "stated target."
            ),
        ],
    )
