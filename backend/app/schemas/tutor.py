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
    term_coverage: float
    matched_terms: list[str]


class TutorSearchRead(BaseModel):
    course_id: str
    query: str
    retrieval_model: str
    result_count: int
    citations: list[TutorCitationRead]


class TutorAnswerRead(BaseModel):
    course_id: str
    question: str
    answer_mode: str
    retrieval_model: str
    grounding_status: Literal["supported", "insufficient_evidence"]
    answer: str
    citation_coverage: float
    citations: list[TutorCitationRead]
    note: str
