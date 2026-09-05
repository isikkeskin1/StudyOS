from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TutorSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1200)
    limit: int = Field(default=6, ge=1, le=12)
    document_types: list[str] = Field(default_factory=list)


class TutorAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1200)
    max_sources: int = Field(default=6, ge=1, le=12)
    minimum_relevance: float = Field(default=0.20, ge=0, le=1)
    document_types: list[str] = Field(default_factory=list)
    answer_style: Literal["concise", "guided", "exam"] = "guided"
    provider: Literal["auto", "local", "openai"] = "auto"


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
    result_count: int
    citations: list[TutorCitationRead]


class TutorAnswerRead(BaseModel):
    course_id: str
    question: str
    answer_mode: str
    answer_style: str = "guided"
    provider_requested: Literal["auto", "local", "openai"] = "auto"
    synthesis_provider: str = "local-grounded-v1"
    retrieval_model: str
    retrieval_components: list[str] = Field(default_factory=list)
    topic_signal_applied: bool = False
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
