from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.diagnostics import MistakeCategory

RetrievalMode = Literal["auto", "lexical", "semantic", "hybrid"]
TutorProvider = Literal["auto", "local", "openai"]


class TutorSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1200)
    limit: int = Field(default=6, ge=1, le=12)
    document_types: list[str] = Field(default_factory=list)
    retrieval_mode: RetrievalMode = "auto"


class TutorAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1200)
    max_sources: int = Field(default=6, ge=1, le=12)
    minimum_relevance: float = Field(default=0.20, ge=0, le=1)
    document_types: list[str] = Field(default_factory=list)
    answer_style: Literal["concise", "guided", "exam"] = "guided"
    provider: TutorProvider = "auto"
    retrieval_mode: RetrievalMode = "auto"


class TutorCitationRead(BaseModel):
    rank: int
    document_id: str
    document_name: str
    document_type: str
    chunk_id: str
    source_label: str
    locator_type: str
    locator_index: int | None
    source_reference: str
    excerpt: str
    relevance_score: float
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    topic_affinity: float = 0.0
    term_coverage: float
    matched_terms: list[str]
    matched_topics: list[str] = Field(default_factory=list)


class TutorSearchRead(BaseModel):
    course_id: str
    query: str
    retrieval_model: str
    retrieval_components: list[str] = Field(default_factory=list)
    topic_signal_applied: bool = False
    semantic_signal_applied: bool = False
    embedding_provider: str | None = None
    result_count: int
    citations: list[TutorCitationRead]


class TutorAnswerRead(BaseModel):
    course_id: str
    question: str
    answer_mode: str
    answer_style: str = "guided"
    provider_requested: TutorProvider = "auto"
    synthesis_provider: str = "local-grounded-v1"
    retrieval_model: str
    retrieval_components: list[str] = Field(default_factory=list)
    topic_signal_applied: bool = False
    semantic_signal_applied: bool = False
    embedding_provider: str | None = None
    grounding_status: Literal["supported", "insufficient_evidence"]
    validation_status: Literal["passed", "not_run", "rejected"] = "not_run"
    validation_model: str = "citation-overlap-v2"
    answer: str
    citation_coverage: float
    grounding_score: float = 0.0
    minimum_claim_support: float = 0.18
    validated_claim_count: int = 0
    unsupported_claim_count: int = 0
    citations: list[TutorCitationRead]
    note: str


class TutorPracticeCreateRequest(BaseModel):
    target_topic: str | None = Field(default=None, min_length=2, max_length=160)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    marks: int | None = Field(default=None, ge=1, le=30)
    provider: TutorProvider = "auto"
    retrieval_mode: RetrievalMode = "auto"
    max_sources: int = Field(default=6, ge=1, le=12)


class TutorPracticeSourceRead(BaseModel):
    rank: int
    role: Literal["question", "solution", "grounding"]
    document_id: str
    document_name: str
    source_label: str
    source_reference: str


class TutorPracticeRead(BaseModel):
    id: str
    course_id: str
    topic: str
    topic_selection: Literal["requested", "weakness_weighted"]
    difficulty: Literal["easy", "medium", "hard"]
    marks: int
    provider_requested: TutorProvider
    generation_provider: str
    generation_mode: str
    retrieval_model: str | None = None
    question: str
    hint_count: int
    hints_revealed: int
    solution_revealed: bool
    source_references: list[str]
    created_at: datetime


class TutorHintRead(BaseModel):
    practice_id: str
    level: int
    hint: str
    remaining_hints: int


class TutorSolutionRead(BaseModel):
    practice_id: str
    solution: str
    sources: list[TutorPracticeSourceRead]
    solution_revealed: bool


class TutorPracticeEvaluateRequest(BaseModel):
    student_answer: str = Field(min_length=1, max_length=20000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    generate_next: bool = True
    grading_provider: TutorProvider = "auto"
    session_id: str | None = Field(default=None, min_length=36, max_length=36)


class TutorPracticeMistakeRead(BaseModel):
    category: MistakeCategory
    severity: float
    source: Literal["automatic"]
    note: str | None


class TutorPracticeMasteryRead(BaseModel):
    topic_id: str
    topic_name: str
    mastery: float
    confidence: float
    evidence_weight: float
    response_count: int


class TutorPracticeRubricCriterionRead(BaseModel):
    criterion: str
    max_points: float
    awarded_points: float
    rationale: str
    mistake_category: MistakeCategory | None = None
    mistake_severity: float | None = None


class TutorPracticeGradingRead(BaseModel):
    grading_mode: str
    grading_provider: str
    total_awarded: float
    total_possible: float
    criteria: list[TutorPracticeRubricCriterionRead]


class TutorPracticeSessionCreateRequest(BaseModel):
    target_topic: str | None = Field(default=None, min_length=2, max_length=160)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    marks: int | None = Field(default=None, ge=1, le=30)
    provider: TutorProvider = "auto"
    retrieval_mode: RetrievalMode = "auto"
    max_sources: int = Field(default=6, ge=1, le=12)
    max_items: int = Field(default=10, ge=1, le=50)


class TutorPracticeSessionMistakeRead(BaseModel):
    category: MistakeCategory
    occurrences: int
    severity_total: float
    average_severity: float


class TutorPracticeSessionTopicRead(BaseModel):
    topic: str
    attempt_count: int
    average_score: float
    average_hints: float
    mistake_count: int


class TutorPracticeSessionContextRead(BaseModel):
    session_id: str
    recent_attempt_count: int
    recent_average_score: float | None
    recent_average_hints: float | None
    dominant_mistake: MistakeCategory | None
    dominant_mistake_count: int
    focus_topic: str | None
    focus_reason: str | None = None


class TutorPracticeSessionRead(BaseModel):
    id: str
    course_id: str
    status: Literal["active", "completed"]
    provider_requested: TutorProvider
    retrieval_mode: RetrievalMode
    max_items: int
    item_count: int
    attempt_count: int
    average_score: float | None
    average_hints: float | None
    dominant_mistakes: list[TutorPracticeSessionMistakeRead]
    topic_summaries: list[TutorPracticeSessionTopicRead]
    remediation_focus: str | None
    current_practice: TutorPracticeRead | None
    created_at: datetime
    completed_at: datetime | None


class TutorPracticeEvaluationRead(BaseModel):
    attempt_id: str
    practice_id: str
    score: float
    grader_name: str
    grader_confidence: float
    evidence_coverage: float
    mastery_weight: float
    hints_used: int
    duration_seconds: int | None
    feedback: str
    mistakes: list[TutorPracticeMistakeRead]
    grading: TutorPracticeGradingRead
    mastery_before: TutorPracticeMasteryRead | None
    mastery_after: TutorPracticeMasteryRead | None
    next_strategy: Literal[
        "increase_difficulty",
        "reinforce",
        "maintain",
        "reoptimize",
        "remediate_pattern",
        "reduce_scaffolding",
        "session_reoptimize",
        "session_complete",
    ]
    next_reason: str
    next_practice: TutorPracticeRead | None
    session_context: TutorPracticeSessionContextRead | None = None
