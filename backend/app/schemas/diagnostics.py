from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DiagnosticSessionCreate(BaseModel):
    question_count: int = Field(default=12, ge=1, le=30)


class DiagnosticSessionRead(BaseModel):
    id: str
    course_id: str
    status: str
    requested_question_count: int
    selected_question_count: int
    answered_question_count: int
    created_at: datetime
    completed_at: datetime | None


class DiagnosticQuestionTopicRead(BaseModel):
    topic_id: str
    topic_name: str
    relevance_score: float


class DiagnosticQuestionRead(BaseModel):
    id: str
    exam_question_id: str
    sequence: int
    question_label: str
    source_label: str
    text: str
    marks: float | None
    difficulty: float
    primary_topic_id: str
    primary_topic_name: str
    topics: list[DiagnosticQuestionTopicRead]


class DiagnosticNextRead(BaseModel):
    session: DiagnosticSessionRead
    question: DiagnosticQuestionRead | None


class DiagnosticResponseCreate(BaseModel):
    diagnostic_question_id: str
    score: float = Field(ge=0, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    grading_source: Literal["self", "manual", "automatic"] = "self"
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)


class TopicMasteryRead(BaseModel):
    topic_id: str
    topic_name: str
    mastery: float
    confidence: float
    evidence_weight: float
    response_count: int
    updated_at: datetime


class DiagnosticResponseRead(BaseModel):
    id: str
    diagnostic_question_id: str
    score: float
    confidence: float
    grading_source: str
    duration_seconds: int | None
    created_at: datetime
    session: DiagnosticSessionRead
    mastery: list[TopicMasteryRead]
