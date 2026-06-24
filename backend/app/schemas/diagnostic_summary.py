from __future__ import annotations

from pydantic import BaseModel


class DiagnosticSessionTopicSummaryRead(BaseModel):
    topic_id: str
    topic_name: str
    question_count: int
    average_score: float


class DiagnosticSessionMistakeSummaryRead(BaseModel):
    category: str
    occurrences: int
    average_severity: float


class DiagnosticSessionSummaryRead(BaseModel):
    session_id: str
    course_id: str
    status: str
    answered_question_count: int
    average_score: float | None
    average_confidence: float | None
    total_duration_seconds: int
    automatic_grade_count: int
    self_grade_count: int
    topic_summaries: list[DiagnosticSessionTopicSummaryRead]
    mistakes: list[DiagnosticSessionMistakeSummaryRead]
