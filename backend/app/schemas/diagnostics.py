from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MistakeCategory = Literal[
    "concept",
    "formula_selection",
    "algebra",
    "arithmetic",
    "sign",
    "units",
    "interpretation",
    "incomplete_reasoning",
    "careless",
    "other",
]


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
    automatic_grading_available: bool = False
    topics: list[DiagnosticQuestionTopicRead]


class DiagnosticNextRead(BaseModel):
    session: DiagnosticSessionRead
    question: DiagnosticQuestionRead | None


class DiagnosticMistakeCreate(BaseModel):
    category: MistakeCategory
    severity: float = Field(default=1.0, gt=0, le=1)
    source: Literal["self", "manual", "automatic"] = "self"
    note: str | None = Field(default=None, max_length=1000)


class DiagnosticResponseCreate(BaseModel):
    diagnostic_question_id: str
    score: float = Field(ge=0, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    grading_source: Literal["self", "manual", "automatic"] = "self"
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    student_answer: str | None = Field(default=None, max_length=20000)
    reference_answer: str | None = Field(default=None, max_length=20000)
    feedback: str | None = Field(default=None, max_length=5000)
    mistakes: list[DiagnosticMistakeCreate] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_mistakes(self) -> DiagnosticResponseCreate:
        categories = [item.category for item in self.mistakes]
        if len(categories) != len(set(categories)):
            raise ValueError("mistake categories must be unique per response")
        return self


class DiagnosticAutoGradeCreate(BaseModel):
    diagnostic_question_id: str
    student_answer: str = Field(min_length=1, max_length=20000)
    confidence: float = Field(default=0.5, ge=0, le=1)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)


class TopicMasteryRead(BaseModel):
    topic_id: str
    topic_name: str
    mastery: float
    confidence: float
    evidence_weight: float
    response_count: int
    updated_at: datetime


class DiagnosticAnswerRead(BaseModel):
    student_answer: str | None
    reference_answer: str | None
    feedback: str | None


class DiagnosticMistakeRead(BaseModel):
    category: str
    severity: float
    source: str
    note: str | None


class DiagnosticGradingRead(BaseModel):
    grader_name: str
    grader_confidence: float
    evidence_coverage: float
    reference_source_label: str
    reference_extraction_method: str


class DiagnosticResponseRead(BaseModel):
    id: str
    diagnostic_question_id: str
    score: float
    confidence: float
    grading_source: str
    duration_seconds: int | None
    created_at: datetime
    answer: DiagnosticAnswerRead | None
    mistakes: list[DiagnosticMistakeRead]
    grading: DiagnosticGradingRead | None = None
    session: DiagnosticSessionRead
    mastery: list[TopicMasteryRead]
