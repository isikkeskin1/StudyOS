from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class ReviewTopicRead(BaseModel):
    topic_id: str
    topic_name: str
    raw_mastery: float
    effective_mastery: float
    raw_confidence: float
    effective_confidence: float
    last_evidence_at: datetime
    days_since_evidence: float
    half_life_days: float
    forgetting_loss: float
    forgetting_risk: str
    exam_weight: float
    review_priority: float
    due_for_review: bool
    recommended_minutes: int
    retention_calibration_confidence: str = "low"
    retention_model: str = "heuristic"
    reason: str


class ReviewQueueRead(BaseModel):
    course_id: str
    generated_at: datetime
    exam_date: date | None
    days_until_exam: int | None
    tracked_topic_count: int
    due_topic_count: int
    total_recommended_minutes: int
    items: list[ReviewTopicRead]
