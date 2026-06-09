from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_content import DocumentChunk
from app.models.tutor_benchmark_history import (
    TutorRetrievalBenchmarkRun,
    TutorRetrievalBenchmarkSuite,
)
from app.schemas.tutor_benchmark import (
    BenchmarkMode,
    TutorBenchmarkModeRead,
    TutorRetrievalBenchmarkCase,
    TutorRetrievalBenchmarkRead,
    TutorRetrievalBenchmarkRequest,
)
from app.schemas.tutor_benchmark_history import (
    TutorBenchmarkComparisonRead,
    TutorBenchmarkModeDeltaRead,
    TutorBenchmarkRunCreate,
    TutorBenchmarkRunHistoryRead,
    TutorBenchmarkRunRead,
    TutorBenchmarkSuiteCreate,
    TutorBenchmarkSuiteRead,
)
from app.services.tutor_benchmark import TutorBenchmarkError, run_retrieval_benchmark
from app.services.tutor_embeddings import TutorEmbeddingConfig, TutorEmbeddingProvider

_SUITE_MODEL = "retrieval-suite-v1"
_METRICS = (
    "top1_accuracy",
    "hit_rate_at_k",
    "recall_at_k",
    "mean_reciprocal_rank",
)


class TutorBenchmarkHistoryError(RuntimeError):
    pass


def _course_chunk_ids(db: Session, course_id: str) -> set[str]:
    rows = db.scalars(
        select(DocumentChunk.id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.course_id == course_id)
    )
    return set(rows)


def _validate_case_chunks(
    db: Session,
    course_id: str,
    cases: list[TutorRetrievalBenchmarkCase],
) -> None:
    available = _course_chunk_ids(db, course_id)
    unknown = sorted(
        {
            chunk_id
            for case in cases
            for chunk_id in case.relevant_chunk_ids
            if chunk_id not in available
        }
    )
    if unknown:
        raise TutorBenchmarkHistoryError(
            "Benchmark suite references chunks that are not processed members of this course: "
            + ", ".join(unknown[:5])
        )


def create_benchmark_suite(
    db: Session,
    course_id: str,
    payload: TutorBenchmarkSuiteCreate,
) -> TutorBenchmarkSuiteRead:
    _validate_case_chunks(db, course_id, payload.cases)
    suite = TutorRetrievalBenchmarkSuite(
        course_id=course_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        benchmark_model=_SUITE_MODEL,
        cases=[case.model_dump(mode="json") for case in payload.cases],
        default_modes=list(payload.default_modes),
        default_k=payload.default_k,
        default_max_results=payload.default_max_results,
    )
    db.add(suite)
    db.commit()
    db.refresh(suite)
    return suite_read(suite, include_cases=True)


def get_benchmark_suite(
    db: Session,
    course_id: str,
    suite_id: str,
) -> TutorRetrievalBenchmarkSuite | None:
    return db.scalar(
        select(TutorRetrievalBenchmarkSuite).where(
            TutorRetrievalBenchmarkSuite.id == suite_id,
            TutorRetrievalBenchmarkSuite.course_id == course_id,
        )
    )


def list_benchmark_suites(db: Session, course_id: str) -> list[TutorBenchmarkSuiteRead]:
    suites = db.scalars(
        select(TutorRetrievalBenchmarkSuite)
        .where(TutorRetrievalBenchmarkSuite.course_id == course_id)
        .order_by(TutorRetrievalBenchmarkSuite.created_at.desc())
    ).all()
    return [suite_read(suite, include_cases=False) for suite in suites]


def suite_read(
    suite: TutorRetrievalBenchmarkSuite,
    *,
    include_cases: bool,
) -> TutorBenchmarkSuiteRead:
    cases = [TutorRetrievalBenchmarkCase.model_validate(case) for case in suite.cases]
    return TutorBenchmarkSuiteRead(
        id=suite.id,
        course_id=suite.course_id,
        name=suite.name,
        description=suite.description,
        benchmark_model=suite.benchmark_model,
        case_count=len(cases),
        default_modes=list(suite.default_modes),
        default_k=suite.default_k,
        default_max_results=suite.default_max_results,
        created_at=suite.created_at,
        cases=cases if include_cases else None,
    )


def _mode_map(result: TutorRetrievalBenchmarkRead) -> dict[BenchmarkMode, TutorBenchmarkModeRead]:
    return {mode.mode: mode for mode in result.modes}


def _delta(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return round(current - baseline, 4)


def _compare_results(
    current: TutorRetrievalBenchmarkRead,
    baseline: TutorRetrievalBenchmarkRead | None,
    baseline_run_id: str | None,
    tolerance: float,
) -> TutorBenchmarkComparisonRead:
    if baseline is None or baseline_run_id is None:
        return TutorBenchmarkComparisonRead(
            baseline_run_id=None,
            tolerance=tolerance,
            verdict="no_baseline",
            comparable_modes=0,
            note="No earlier comparable run exists for this suite and k value.",
        )

    current_modes = _mode_map(current)
    baseline_modes = _mode_map(baseline)
    deltas: list[TutorBenchmarkModeDeltaRead] = []
    regressed_modes: list[BenchmarkMode] = []
    for mode in current_modes:
        if mode not in baseline_modes:
            continue
        now = current_modes[mode]
        before = baseline_modes[mode]
        regressed: list[str] = []
        if now.status == "evaluated" and before.status == "evaluated":
            for metric in _METRICS:
                change = _delta(getattr(now, metric), getattr(before, metric))
                if change is not None and change < -tolerance:
                    regressed.append(metric)
        if regressed:
            regressed_modes.append(mode)
        deltas.append(
            TutorBenchmarkModeDeltaRead(
                mode=mode,
                baseline_status=before.status,
                current_status=now.status,
                top1_accuracy_delta=_delta(now.top1_accuracy, before.top1_accuracy),
                hit_rate_at_k_delta=_delta(now.hit_rate_at_k, before.hit_rate_at_k),
                recall_at_k_delta=_delta(now.recall_at_k, before.recall_at_k),
                mean_reciprocal_rank_delta=_delta(
                    now.mean_reciprocal_rank,
                    before.mean_reciprocal_rank,
                ),
                mean_first_relevant_rank_delta=_delta(
                    now.mean_first_relevant_rank,
                    before.mean_first_relevant_rank,
                ),
                regressed_metrics=regressed,
            )
        )

    comparable = sum(
        item.current_status == "evaluated" and item.baseline_status == "evaluated"
        for item in deltas
    )
    if comparable == 0:
        verdict = "no_baseline"
        note = "The runs share no retrieval mode that was evaluated in both snapshots."
    elif regressed_modes:
        verdict = "regression"
        note = "At least one bounded retrieval metric regressed beyond the configured tolerance."
    else:
        verdict = "pass"
        note = "No bounded retrieval metric regressed beyond the configured tolerance."
    return TutorBenchmarkComparisonRead(
        baseline_run_id=baseline_run_id,
        tolerance=tolerance,
        verdict=verdict,
        comparable_modes=comparable,
        regressed_modes=regressed_modes,
        mode_deltas=deltas,
        note=note,
    )


def _baseline_run(
    db: Session,
    suite: TutorRetrievalBenchmarkSuite,
    *,
    k: int,
    explicit_run_id: str | None,
) -> TutorRetrievalBenchmarkRun | None:
    if explicit_run_id is not None:
        run = db.get(TutorRetrievalBenchmarkRun, explicit_run_id)
        if run is None or run.suite_id != suite.id:
            raise TutorBenchmarkHistoryError("Baseline run does not belong to this benchmark suite")
        if run.k != k:
            raise TutorBenchmarkHistoryError("Baseline run must use the same k value")
        return run
    return db.scalar(
        select(TutorRetrievalBenchmarkRun)
        .where(
            TutorRetrievalBenchmarkRun.suite_id == suite.id,
            TutorRetrievalBenchmarkRun.k == k,
        )
        .order_by(TutorRetrievalBenchmarkRun.created_at.desc())
        .limit(1)
    )


def run_benchmark_suite(
    db: Session,
    suite: TutorRetrievalBenchmarkSuite,
    payload: TutorBenchmarkRunCreate,
    *,
    embedding_config: TutorEmbeddingConfig | None = None,
    embedding_provider: TutorEmbeddingProvider | None = None,
) -> TutorBenchmarkRunRead:
    cases = [TutorRetrievalBenchmarkCase.model_validate(case) for case in suite.cases]
    _validate_case_chunks(db, suite.course_id, cases)
    modes = list(payload.modes or suite.default_modes)
    k = payload.k if payload.k is not None else suite.default_k
    max_results = (
        payload.max_results if payload.max_results is not None else suite.default_max_results
    )
    if k > max_results:
        raise TutorBenchmarkHistoryError("k cannot exceed max_results")

    baseline_row = _baseline_run(
        db,
        suite,
        k=k,
        explicit_run_id=payload.compare_to_run_id,
    )
    request = TutorRetrievalBenchmarkRequest(
        cases=cases,
        modes=modes,
        k=k,
        max_results=max_results,
    )
    try:
        result = run_retrieval_benchmark(
            db,
            suite.course_id,
            request,
            embedding_config=embedding_config,
            embedding_provider=embedding_provider,
        )
    except TutorBenchmarkError as exc:
        raise TutorBenchmarkHistoryError(str(exc)) from exc

    baseline_result = (
        TutorRetrievalBenchmarkRead.model_validate(baseline_row.result)
        if baseline_row is not None
        else None
    )
    comparison = _compare_results(
        result,
        baseline_result,
        baseline_row.id if baseline_row is not None else None,
        payload.regression_tolerance,
    )
    row = TutorRetrievalBenchmarkRun(
        suite_id=suite.id,
        course_id=suite.course_id,
        revision_label=payload.revision_label.strip() if payload.revision_label else None,
        benchmark_model=result.benchmark_model,
        modes=modes,
        k=k,
        max_results=max_results,
        best_mode=result.best_mode,
        result=result.model_dump(mode="json"),
        comparison=comparison.model_dump(mode="json"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return run_read(row, include_result=True)


def run_read(
    row: TutorRetrievalBenchmarkRun,
    *,
    include_result: bool,
) -> TutorBenchmarkRunRead:
    comparison = TutorBenchmarkComparisonRead.model_validate(row.comparison)
    result = TutorRetrievalBenchmarkRead.model_validate(row.result) if include_result else None
    return TutorBenchmarkRunRead(
        id=row.id,
        suite_id=row.suite_id,
        course_id=row.course_id,
        revision_label=row.revision_label,
        benchmark_model=row.benchmark_model,
        modes=list(row.modes),
        k=row.k,
        max_results=row.max_results,
        best_mode=row.best_mode,
        created_at=row.created_at,
        comparison=comparison,
        result=result,
    )


def list_benchmark_runs(
    db: Session,
    suite: TutorRetrievalBenchmarkSuite,
) -> TutorBenchmarkRunHistoryRead:
    runs = db.scalars(
        select(TutorRetrievalBenchmarkRun)
        .where(TutorRetrievalBenchmarkRun.suite_id == suite.id)
        .order_by(TutorRetrievalBenchmarkRun.created_at.desc())
    ).all()
    return TutorBenchmarkRunHistoryRead(
        suite_id=suite.id,
        run_count=len(runs),
        runs=[run_read(run, include_result=False) for run in runs],
    )


def get_benchmark_run(
    db: Session,
    suite: TutorRetrievalBenchmarkSuite,
    run_id: str,
) -> TutorBenchmarkRunRead | None:
    row = db.get(TutorRetrievalBenchmarkRun, run_id)
    if row is None or row.suite_id != suite.id:
        return None
    return run_read(row, include_result=True)
