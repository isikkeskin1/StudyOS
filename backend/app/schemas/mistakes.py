from __future__ import annotations

from pydantic import BaseModel


class MistakeCategoryStatRead(BaseModel):
    category: str
    occurrences: int
    weighted_lost_score: float
    share_of_classified_loss: float


class TopicMistakePatternRead(BaseModel):
    topic_id: str
    topic_name: str
    mistake_burden: float
    dominant_categories: list[str]


class MistakeIntelligenceRead(BaseModel):
    course_id: str
    response_count: int
    responses_with_mistakes: int
    lost_score_total: float
    classified_loss_total: float
    classification_coverage: float
    categories: list[MistakeCategoryStatRead]
    topics: list[TopicMistakePatternRead]
