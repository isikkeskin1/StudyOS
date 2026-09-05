from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class TopicCalibrationRead(BaseModel):
    topic_id: str
    topic_name: str
    history_point_count: int
    evidence_span_days: float
    learning_rate_multiplier: float
    learning_scale_hours: float
    learning_confidence: Literal["low", "medium", "high"]
    observed_gain_per_evidence: float | None
    heuristic_half_life_days: float | None
    retention_half_life_days: float | None
    retention_confidence: Literal["low", "medium", "high"]
    retention_observation_count: int
    calibration_source: Literal["heuristic", "blended", "personalized"]


class CourseCalibrationRead(BaseModel):
    course_id: str
    generated_at: datetime
    topic_count: int
    history_point_count: int
    calibrated_learning_topic_count: int
    calibrated_retention_topic_count: int
    topics: list[TopicCalibrationRead]
    notes: list[str]
