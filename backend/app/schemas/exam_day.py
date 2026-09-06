from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ExamDayCreateRequest(BaseModel):
    duration_minutes: int = Field(default=90, ge=5, le=360)
    question_count: int = Field(default=10, ge=1, le=50)


class ExamDayAnswerUpdate(BaseModel):
    answer_text: str = Field(default="", max_length=30000)
    flagged: bool = False
    self_score: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(default=0.7, ge=0, le=1)


class ExamDayQuestionRead(BaseModel):
    id: str
    sequence: int
    question_label: str
    source_label: str
    text: str
    marks: float | None
    topic_name: str | None
    automatic_grading_available: bool
    answer_text: str
    flagged: bool
    self_score: float | None
    confidence: float
    score: float | None
    grading_source: str | None
    feedback: str | None


class ExamDaySessionRead(BaseModel):
    id: str
    course_id: str
    status: Literal["active", "submitted", "expired"]
    duration_minutes: int
    question_count: int
    total_known_marks: float
    answered_count: int
    flagged_count: int
    started_at: datetime
    submitted_at: datetime | None
    expires_at: datetime
    remaining_seconds: int
    questions: list[ExamDayQuestionRead]


class ExamDayTopicBreakdownRead(BaseModel):
    topic_id: str | None
    topic_name: str
    question_count: int
    average_score: float


class ExamDayResultRead(BaseModel):
    session_id: str
    status: str
    answered_count: int
    question_count: int
    average_score: float | None
    earned_known_marks: float
    total_known_marks: float
    automatic_grade_count: int
    self_grade_count: int
    topic_breakdown: list[ExamDayTopicBreakdownRead]
    questions: list[ExamDayQuestionRead]
