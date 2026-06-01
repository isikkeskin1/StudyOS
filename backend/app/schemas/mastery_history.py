from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MasteryHistoryPointRead(BaseModel):
    response_id: str
    recorded_at: datetime
    mastery: float
    confidence: float
    evidence_weight: float
    response_count: int
    source_score: float
    topic_relevance: float
    evidence_increment: float


class TopicMasteryTrendRead(BaseModel):
    topic_id: str
    topic_name: str
    point_count: int
    raw_mastery: float
    effective_mastery: float
    confidence: float
    effective_confidence: float
    forgetting_risk: str
    change_from_first: float
    weekly_change: float | None
    trend_direction: Literal["improving", "stable", "declining", "insufficient_data"]
    trend_confidence: Literal["low", "medium", "high"]
    recent_accuracy: float
    recent_response_count: int
    observed_gain_per_evidence: float | None
    first_evidence_at: datetime
    latest_evidence_at: datetime
    evidence_span_days: float
    points: list[MasteryHistoryPointRead]


class CourseMasteryHistoryRead(BaseModel):
    course_id: str
    generated_at: datetime
    tracked_topic_count: int
    total_history_points: int
    improving_topic_count: int
    stable_topic_count: int
    declining_topic_count: int
    topics: list[TopicMasteryTrendRead]
