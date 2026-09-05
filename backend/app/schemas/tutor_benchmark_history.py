from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.tutor_benchmark import (
    BenchmarkMode,
    TutorRetrievalBenchmarkCase,
    TutorRetrievalBenchmarkRead,
)

RegressionVerdict = Literal["no_baseline", "pass", "regression"]


class TutorBenchmarkSuiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    cases: list[TutorRetrievalBenchmarkCase] = Field(min_length=1, max_length=200)
    default_modes: list[BenchmarkMode] = Field(
        default_factory=lambda: ["bm25", "topic", "semantic", "hybrid"],
        min_length=1,
        max_length=4,
    )
    default_k: int = Field(default=3, ge=1, le=20)
    default_max_results: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def validate_suite(self) -> TutorBenchmarkSuiteCreate:
        case_ids = [case.case_id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("case_id values must be unique")
        if len(set(self.default_modes)) != len(self.default_modes):
            raise ValueError("default_modes must be unique")
        if self.default_k > self.default_max_results:
            raise ValueError("default_k cannot exceed default_max_results")
        return self


class TutorBenchmarkSuiteRead(BaseModel):
    id: str
    course_id: str
    name: str
    description: str | None
    benchmark_model: str
    case_count: int
    default_modes: list[BenchmarkMode]
    default_k: int
    default_max_results: int
    created_at: datetime
    cases: list[TutorRetrievalBenchmarkCase] | None = None


class TutorBenchmarkRunCreate(BaseModel):
    modes: list[BenchmarkMode] | None = Field(default=None, min_length=1, max_length=4)
    k: int | None = Field(default=None, ge=1, le=20)
    max_results: int | None = Field(default=None, ge=1, le=50)
    revision_label: str | None = Field(default=None, max_length=160)
    compare_to_run_id: str | None = None
    regression_tolerance: float = Field(default=0.02, ge=0.0, le=0.25)

    @model_validator(mode="after")
    def validate_run(self) -> TutorBenchmarkRunCreate:
        if self.modes is not None and len(set(self.modes)) != len(self.modes):
            raise ValueError("modes must be unique")
        if self.k is not None and self.max_results is not None and self.k > self.max_results:
            raise ValueError("k cannot exceed max_results")
        return self


class TutorBenchmarkModeDeltaRead(BaseModel):
    mode: BenchmarkMode
    baseline_status: Literal["evaluated", "unavailable"]
    current_status: Literal["evaluated", "unavailable"]
    top1_accuracy_delta: float | None
    hit_rate_at_k_delta: float | None
    recall_at_k_delta: float | None
    mean_reciprocal_rank_delta: float | None
    mean_first_relevant_rank_delta: float | None
    regressed_metrics: list[str] = Field(default_factory=list)


class TutorBenchmarkComparisonRead(BaseModel):
    baseline_run_id: str | None
    tolerance: float
    verdict: RegressionVerdict
    comparable_modes: int
    regressed_modes: list[BenchmarkMode] = Field(default_factory=list)
    mode_deltas: list[TutorBenchmarkModeDeltaRead] = Field(default_factory=list)
    note: str


class TutorBenchmarkRunRead(BaseModel):
    id: str
    suite_id: str
    course_id: str
    revision_label: str | None
    benchmark_model: str
    modes: list[BenchmarkMode]
    k: int
    max_results: int
    best_mode: BenchmarkMode | None
    created_at: datetime
    comparison: TutorBenchmarkComparisonRead
    result: TutorRetrievalBenchmarkRead | None = None


class TutorBenchmarkRunHistoryRead(BaseModel):
    suite_id: str
    run_count: int
    runs: list[TutorBenchmarkRunRead]
