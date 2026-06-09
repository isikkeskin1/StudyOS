from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

BenchmarkMode = Literal["bm25", "topic", "semantic", "hybrid"]


class TutorRetrievalBenchmarkCase(BaseModel):
    case_id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=2, max_length=1200)
    relevant_chunk_ids: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_relevant_chunks(self) -> TutorRetrievalBenchmarkCase:
        if len(set(self.relevant_chunk_ids)) != len(self.relevant_chunk_ids):
            raise ValueError("relevant_chunk_ids must be unique within a case")
        return self


class TutorRetrievalBenchmarkRequest(BaseModel):
    cases: list[TutorRetrievalBenchmarkCase] = Field(min_length=1, max_length=200)
    modes: list[BenchmarkMode] = Field(
        default_factory=lambda: ["bm25", "topic", "semantic", "hybrid"],
        min_length=1,
        max_length=4,
    )
    k: int = Field(default=3, ge=1, le=20)
    max_results: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def validate_unique_ids_and_modes(self) -> TutorRetrievalBenchmarkRequest:
        case_ids = [case.case_id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("case_id values must be unique")
        if len(set(self.modes)) != len(self.modes):
            raise ValueError("modes must be unique")
        if self.k > self.max_results:
            raise ValueError("k cannot exceed max_results")
        return self


class TutorBenchmarkRetrievedChunkRead(BaseModel):
    rank: int
    chunk_id: str
    source_reference: str
    score: float
    lexical_score: float
    semantic_score: float
    topic_affinity: float
    relevant: bool


class TutorBenchmarkCaseResultRead(BaseModel):
    case_id: str
    label: str
    query: str
    relevant_chunk_ids: list[str]
    top1_correct: bool
    hit_at_k: bool
    recall_at_k: float
    reciprocal_rank: float
    first_relevant_rank: int | None
    retrieved: list[TutorBenchmarkRetrievedChunkRead]


class TutorBenchmarkFailureRead(BaseModel):
    case_id: str
    label: str
    query: str
    reason: Literal["top1_miss", "missed_at_k"]
    first_relevant_rank: int | None
    top_chunk_id: str | None
    top_source_reference: str | None


class TutorBenchmarkModeRead(BaseModel):
    mode: BenchmarkMode
    status: Literal["evaluated", "unavailable"]
    retrieval_model: str
    evaluated_cases: int
    top1_accuracy: float | None
    hit_rate_at_k: float | None
    recall_at_k: float | None
    mean_reciprocal_rank: float | None
    mean_first_relevant_rank: float | None
    failures: list[TutorBenchmarkFailureRead] = Field(default_factory=list)
    cases: list[TutorBenchmarkCaseResultRead] = Field(default_factory=list)
    note: str | None = None


class TutorRetrievalBenchmarkRead(BaseModel):
    course_id: str
    benchmark_model: str
    case_count: int
    k: int
    max_results: int
    best_mode: BenchmarkMode | None
    modes: list[TutorBenchmarkModeRead]
    note: str
