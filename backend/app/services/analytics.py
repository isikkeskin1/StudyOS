from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from statistics import mean
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.calendar_focus import FocusSession
from app.models.course import Course
from app.models.diagnostics import DiagnosticResponse, DiagnosticSession, TopicMastery
from app.models.forecast_tracking import GradeForecastSnapshot
from app.models.mastery_history import MasterySnapshot
from app.models.semester_queue import SemesterStudyQueueBlock
from app.models.tutor_practice import TutorPracticeAttempt
from app.schemas.analytics import (
    AnalyticsActivityDay,
    AnalyticsCourseRead,
    AnalyticsDashboardRead,
    AnalyticsMistakeCategory,
    AnalyticsSummary,
    AnalyticsTopicRisk,
)
from app.services.mistake_intelligence import summarize_course_mistakes
from app.services.semester_dashboard import _course_status


class AnalyticsCourseNotFoundError(RuntimeError):
    pass


class AnalyticsInputError(RuntimeError):
    pass


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise AnalyticsInputError(f"Unknown timezone: {name}") from exc


def _window(now: datetime, days: int, zone: ZoneInfo) -> tuple[datetime, datetime]:
    local_now = now.astimezone(zone)
    first_day = local_now.date() - timedelta(days=days - 1)
    local_start = datetime.combine(first_day, time.min, tzinfo=zone)
    return local_start.astimezone(UTC), now


def _local_day(value: datetime, zone: ZoneInfo) -> date:
    return _utc(value).astimezone(zone).date()


def _focus_rows(
    db: Session,
    course_ids: set[str],
    start: datetime,
    end: datetime,
) -> list[tuple[FocusSession, SemesterStudyQueueBlock]]:
    if not course_ids:
        return []
    rows = db.execute(
        select(FocusSession, SemesterStudyQueueBlock)
        .join(SemesterStudyQueueBlock, SemesterStudyQueueBlock.id == FocusSession.block_id)
        .where(SemesterStudyQueueBlock.course_id.in_(course_ids))
    ).all()
    return [
        (session, block)
        for session, block in rows
        if session.completed_at is not None
        and start <= _utc(session.completed_at) <= end
    ]


def _diagnostic_rows(
    db: Session,
    course_ids: set[str],
    start: datetime,
    end: datetime,
) -> list[tuple[DiagnosticResponse, str]]:
    if not course_ids:
        return []
    rows = db.execute(
        select(DiagnosticResponse, DiagnosticSession.course_id)
        .join(DiagnosticSession, DiagnosticSession.id == DiagnosticResponse.session_id)
        .where(DiagnosticSession.course_id.in_(course_ids))
    ).all()
    return [
        (response, course_id)
        for response, course_id in rows
        if start <= _utc(response.created_at) <= end
    ]


def _practice_rows(
    db: Session,
    course_ids: set[str],
    start: datetime,
    end: datetime,
) -> list[TutorPracticeAttempt]:
    if not course_ids:
        return []
    rows = db.scalars(
        select(TutorPracticeAttempt).where(TutorPracticeAttempt.course_id.in_(course_ids))
    ).all()
    return [row for row in rows if start <= _utc(row.created_at) <= end]


def _mastery_rows(
    db: Session,
    course_ids: set[str],
    start: datetime,
    end: datetime,
) -> list[MasterySnapshot]:
    if not course_ids:
        return []
    rows = db.scalars(
        select(MasterySnapshot).where(MasterySnapshot.course_id.in_(course_ids))
    ).all()
    return [row for row in rows if start <= _utc(row.recorded_at) <= end]


def _forecast_rows(
    db: Session,
    course_ids: set[str],
    start: datetime,
    end: datetime,
) -> list[GradeForecastSnapshot]:
    if not course_ids:
        return []
    rows = db.scalars(
        select(GradeForecastSnapshot).where(GradeForecastSnapshot.course_id.in_(course_ids))
    ).all()
    return [row for row in rows if start <= _utc(row.created_at) <= end]


def _diagnostic_mastery_delta(
    db: Session,
    course_id: str,
    start: datetime,
    end: datetime,
) -> float | None:
    rows = list(
        db.scalars(
            select(MasterySnapshot)
            .where(MasterySnapshot.course_id == course_id)
            .order_by(MasterySnapshot.topic_id, MasterySnapshot.recorded_at)
        ).all()
    )
    by_topic: dict[str, list[MasterySnapshot]] = defaultdict(list)
    for row in rows:
        if _utc(row.recorded_at) <= end:
            by_topic[row.topic_id].append(row)

    deltas: list[float] = []
    for topic_rows in by_topic.values():
        before = [row for row in topic_rows if _utc(row.recorded_at) < start]
        inside = [row for row in topic_rows if start <= _utc(row.recorded_at) <= end]
        if not inside:
            continue
        baseline = before[-1] if before else inside[0]
        latest = inside[-1]
        if latest.id != baseline.id:
            deltas.append(latest.mastery - baseline.mastery)
    return round(mean(deltas), 4) if deltas else None


def _course_analytics(
    db: Session,
    course: Course,
    now: datetime,
    start: datetime,
    end: datetime,
    focus_rows: list[tuple[FocusSession, SemesterStudyQueueBlock]],
    diagnostic_rows: list[tuple[DiagnosticResponse, str]],
    practice_rows: list[TutorPracticeAttempt],
    forecast_rows: list[GradeForecastSnapshot],
) -> AnalyticsCourseRead:
    status = _course_status(db, course, now)
    focus = [row for row in focus_rows if row[1].course_id == course.id]
    completed_focus = [row for row, _ in focus if row.status == "completed"]
    skipped_focus = [row for row, _ in focus if row.status == "skipped"]
    focus_total = len(completed_focus) + len(skipped_focus)
    focus_minutes = sum(row.actual_minutes or 0 for row in completed_focus)

    diagnostics = [response for response, cid in diagnostic_rows if cid == course.id]
    practices = [row for row in practice_rows if row.course_id == course.id]
    scores = [row.score for row in diagnostics] + [row.score for row in practices]

    mastery = list(
        db.scalars(select(TopicMastery).where(TopicMastery.course_id == course.id)).all()
    )
    current_mean_mastery = round(mean(row.mastery for row in mastery), 4) if mastery else None

    forecasts = sorted(
        [row for row in forecast_rows if row.course_id == course.id],
        key=lambda row: _utc(row.created_at),
    )
    latest = forecasts[-1] if forecasts else None
    forecast_delta = None
    if len(forecasts) >= 2:
        first = forecasts[0]
        last = forecasts[-1]
        forecast_delta = round(
            last.expected_grade / last.max_grade - first.expected_grade / first.max_grade,
            4,
        )

    mistakes = summarize_course_mistakes(db, course.id)
    normalized_current = (
        round(status.current_estimated_grade / course.max_grade, 4)
        if status.current_estimated_grade is not None
        else None
    )
    normalized_target = (
        round(course.target_grade / course.max_grade, 4)
        if course.target_grade is not None
        else None
    )
    return AnalyticsCourseRead(
        course_id=course.id,
        course_name=course.name,
        target_grade=course.target_grade,
        max_grade=course.max_grade,
        current_estimated_grade=status.current_estimated_grade,
        normalized_current_grade=normalized_current,
        normalized_target_grade=normalized_target,
        normalized_target_gap=status.normalized_target_gap,
        target_status=status.target_status,
        confidence=status.confidence,
        topic_count=status.topic_count,
        measured_topic_count=status.measured_topic_count,
        current_mean_mastery=current_mean_mastery,
        diagnostic_mastery_delta=_diagnostic_mastery_delta(db, course.id, start, end),
        focus_minutes=focus_minutes,
        focus_sessions_completed=len(completed_focus),
        focus_sessions_skipped=len(skipped_focus),
        focus_completion_rate=(
            round(len(completed_focus) / focus_total, 4) if focus_total else None
        ),
        answer_count=len(scores),
        average_answer_score=round(mean(scores), 4) if scores else None,
        forecast_count=len(forecasts),
        latest_forecast_grade=round(latest.expected_grade, 2) if latest else None,
        latest_target_probability=round(latest.target_probability, 4) if latest else None,
        normalized_forecast_delta=forecast_delta,
        mistake_classification_coverage=mistakes.classification_coverage,
        top_mistakes=[
            AnalyticsMistakeCategory(
                category=item.category,
                occurrences=item.occurrences,
                weighted_lost_score=item.weighted_lost_score,
                share_of_classified_loss=item.share_of_classified_loss,
            )
            for item in mistakes.categories[:3]
        ],
        highest_risk_topics=[
            AnalyticsTopicRisk(
                topic_id=item.topic_id,
                topic_name=item.topic_name,
                mistake_burden=item.mistake_burden,
                dominant_categories=item.dominant_categories,
            )
            for item in mistakes.topics[:3]
        ],
    )


def build_analytics_dashboard(
    db: Session,
    *,
    days: int = 30,
    course_id: str | None = None,
    timezone: str = "UTC",
) -> AnalyticsDashboardRead:
    if days < 1 or days > 365:
        raise AnalyticsInputError("days must be between 1 and 365")
    zone = _zone(timezone)
    now = datetime.now(UTC)
    start, end = _window(now, days, zone)

    courses = list(db.scalars(select(Course).order_by(Course.name, Course.id)).all())
    if course_id is not None:
        courses = [course for course in courses if course.id == course_id]
        if not courses:
            raise AnalyticsCourseNotFoundError("Course not found")
    course_ids = {course.id for course in courses}

    focus = _focus_rows(db, course_ids, start, end)
    diagnostics = _diagnostic_rows(db, course_ids, start, end)
    practices = _practice_rows(db, course_ids, start, end)
    mastery_updates = _mastery_rows(db, course_ids, start, end)
    forecasts = _forecast_rows(db, course_ids, start, end)

    course_rows = [
        _course_analytics(
            db,
            course,
            now,
            start,
            end,
            focus,
            diagnostics,
            practices,
            forecasts,
        )
        for course in courses
    ]

    activity: dict[date, AnalyticsActivityDay] = {}
    local_start_day = start.astimezone(zone).date()
    for offset in range(days):
        day = local_start_day + timedelta(days=offset)
        activity[day] = AnalyticsActivityDay(
            date=day,
            focus_minutes=0,
            focus_sessions_completed=0,
            focus_sessions_skipped=0,
            diagnostic_responses=0,
            practice_attempts=0,
            mastery_updates=0,
            forecast_snapshots=0,
        )

    for session, _ in focus:
        if session.completed_at is None:
            continue
        row = activity[_local_day(session.completed_at, zone)]
        if session.status == "completed":
            row.focus_sessions_completed += 1
            row.focus_minutes += session.actual_minutes or 0
        elif session.status == "skipped":
            row.focus_sessions_skipped += 1
    for response, _ in diagnostics:
        activity[_local_day(response.created_at, zone)].diagnostic_responses += 1
    for attempt in practices:
        activity[_local_day(attempt.created_at, zone)].practice_attempts += 1
    for snapshot in mastery_updates:
        activity[_local_day(snapshot.recorded_at, zone)].mastery_updates += 1
    for snapshot in forecasts:
        activity[_local_day(snapshot.created_at, zone)].forecast_snapshots += 1

    total_completed = sum(row.focus_sessions_completed for row in course_rows)
    total_skipped = sum(row.focus_sessions_skipped for row in course_rows)
    total_focus = total_completed + total_skipped
    answer_scores = [
        response.score for response, _ in diagnostics
    ] + [attempt.score for attempt in practices]

    return AnalyticsDashboardRead(
        generated_at=now,
        window_days=days,
        timezone=timezone,
        window_start=start,
        window_end=end,
        course_filter=course_id,
        summary=AnalyticsSummary(
            course_count=len(course_rows),
            at_target_count=sum(row.target_status == "at_target" for row in course_rows),
            below_target_count=sum(row.target_status == "below_target" for row in course_rows),
            unmeasured_count=sum(row.target_status == "unmeasured" for row in course_rows),
            focus_minutes=sum(row.focus_minutes for row in course_rows),
            focus_sessions_completed=total_completed,
            focus_sessions_skipped=total_skipped,
            focus_completion_rate=(round(total_completed / total_focus, 4) if total_focus else None),
            answer_count=len(answer_scores),
            average_answer_score=round(mean(answer_scores), 4) if answer_scores else None,
            mastery_updates=len(mastery_updates),
            forecast_snapshots=len(forecasts),
        ),
        courses=course_rows,
        activity=list(activity.values()),
        assumptions=[
            "Daily activity is grouped in the requested IANA timezone; stored timestamps remain UTC.",
            "Focus analytics count terminal focus sessions in the selected window. Skips do not add "
            "study minutes.",
            "Answer quality combines diagnostic and tutor-practice scores on their shared 0-1 scale.",
            "Diagnostic mastery delta uses recorded diagnostic mastery snapshots only; current mastery "
            "can also include newer tutor-practice evidence.",
            "Forecast movement is normalized by each snapshot's maximum grade before comparison.",
            "Mistake hotspots are all-time evidence because mistake history is currently summarized "
            "without a time-windowed persistence layer.",
        ],
    )
