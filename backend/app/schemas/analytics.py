from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class AnalyticsActivityDay(BaseModel):
    date: date
    focus_minutes: int
    focus_sessions_completed: int
    focus_sessions_skipped: int
    diagnostic_responses: int
    practice_attempts: int
    mastery_updates: int
    forecast_snapshots: int


class AnalyticsMistakeCategory(BaseModel):
    category: str
    occurrences: int
    weighted_lost_score: float
    share_of_classified_loss: float


class AnalyticsTopicRisk(BaseModel):
    topic_id: str
    topic_name: str
    mistake_burden: float
    dominant_categories: list[str]


class AnalyticsCourseRead(BaseModel):
    course_id: str
    course_name: str
    target_grade: float | None
    max_grade: float
    current_estimated_grade: float | None
    normalized_current_grade: float | None
    normalized_target_grade: float | None
    normalized_target_gap: float | None
    target_status: Literal["unconfigured", "unmeasured", "below_target", "at_target"]
    confidence: Literal["low", "medium", "high"]
    topic_count: int
    measured_topic_count: int
    current_mean_mastery: float | None
    diagnostic_mastery_delta: float | None
    focus_minutes: int
    focus_sessions_completed: int
    focus_sessions_skipped: int
    focus_completion_rate: float | None
    answer_count: int
    average_answer_score: float | None
    forecast_count: int
    latest_forecast_grade: float | None
    latest_target_probability: float | None
    normalized_forecast_delta: float | None
    mistake_classification_coverage: float
    top_mistakes: list[AnalyticsMistakeCategory]
    highest_risk_topics: list[AnalyticsTopicRisk]


class AnalyticsSummary(BaseModel):
    course_count: int
    at_target_count: int
    below_target_count: int
    unmeasured_count: int
    focus_minutes: int
    focus_sessions_completed: int
    focus_sessions_skipped: int
    focus_completion_rate: float | None
    answer_count: int
    average_answer_score: float | None
    mastery_updates: int
    forecast_snapshots: int


class AnalyticsDashboardRead(BaseModel):
    generated_at: datetime
    window_days: int
    timezone: str
    window_start: datetime
    window_end: datetime
    course_filter: str | None
    summary: AnalyticsSummary
    courses: list[AnalyticsCourseRead]
    activity: list[AnalyticsActivityDay]
    assumptions: list[str]
