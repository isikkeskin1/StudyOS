from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.schemas.tutor_benchmark import (
    BenchmarkMode,
    TutorBenchmarkCaseResultRead,
    TutorBenchmarkFailureRead,
    TutorBenchmarkModeRead,
    TutorBenchmarkRetrievedChunkRead,
    TutorRetrievalBenchmarkRead,
    TutorRetrievalBenchmarkRequest,
)
from app.services.tutor import (
    _candidate_rows,
    _lexical_signals,
    _semantic_scores,
    _tokens,
)
from app.services.tutor_embeddings import (
    TutorEmbeddingConfig,
    TutorEmbeddingProvider,
    build_embedding_provider,
)

_BENCHMARK_MODEL = "retrieval-hard-negative-v1"
_MODE_MODELS: dict[BenchmarkMode, str] = {
    "bm25": "benchmark-bm25-v1",
    "topic": "benchmark-topic-bm25-v1",
    "semantic": "semantic-vector-rerank-v1",
    "hybrid": "hybrid-vector-bm25-v1",
}


class TutorBenchmarkError(RuntimeError):
    pass


@dataclass(frozen=True)
class _ScoredCandidate:
    chunk_id: str
    source_reference: str
    score: float
    lexical: float
    semantic: float
    topic: float


def _mode_score(mode: BenchmarkMode, lexical: float, semantic: float, topic: float) -> float:
    if mode == "bm25":
        return lexical
    if mode == "topic":
        return min(1.0, 0.78 * lexical + 0.22 * topic)
    if mode == "semantic":
        return min(1.0, 0.90 * semantic + 0.10 * topic)
    return min(1.0, 0.50 * lexical + 0.35 * semantic + 0.15 * topic)


def _eligible(mode: BenchmarkMode, lexical: float, semantic: float, topic: float) -> bool:
    if mode == "bm25":
        return lexical > 0
    if mode == "topic":
        return lexical > 0 or topic > 0
    if mode == "semantic":
        return semantic > 0 or topic > 0
    return lexical > 0 or semantic > 0 or topic > 0


def _case_result(
    case_id: str,
    label: str,
    query: str,
    relevant_chunk_ids: list[str],
    ranked: list[_ScoredCandidate],
    k: int,
    max_results: int,
) -> TutorBenchmarkCaseResultRead:
    relevant = set(relevant_chunk_ids)
    first_relevant_rank = next(
        (rank for rank, item in enumerate(ranked, 1) if item.chunk_id in relevant),
        None,
    )
    top_k = ranked[:k]
    retrieved_relevant = sum(item.chunk_id in relevant for item in top_k)
    recall = retrieved_relevant / len(relevant)
    reciprocal = 1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0
    return TutorBenchmarkCaseResultRead(
        case_id=case_id,
        label=label,
        query=query,
        relevant_chunk_ids=relevant_chunk_ids,
        top1_correct=bool(ranked and ranked[0].chunk_id in relevant),
        hit_at_k=retrieved_relevant > 0,
        recall_at_k=round(recall, 4),
        reciprocal_rank=round(reciprocal, 4),
        first_relevant_rank=first_relevant_rank,
        retrieved=[
            TutorBenchmarkRetrievedChunkRead(
                rank=rank,
                chunk_id=item.chunk_id,
                source_reference=item.source_reference,
                score=round(item.score, 4),
                lexical_score=round(item.lexical, 4),
                semantic_score=round(item.semantic, 4),
                topic_affinity=round(item.topic, 4),
                relevant=item.chunk_id in relevant,
            )
            for rank, item in enumerate(ranked[:max_results], 1)
        ],
    )


def _mode_summary(
    mode: BenchmarkMode,
    cases: list[TutorBenchmarkCaseResultRead],
    k: int,
) -> TutorBenchmarkModeRead:
    count = len(cases)
    first_ranks = [
        case.first_relevant_rank
        for case in cases
        if case.first_relevant_rank is not None
    ]
    failures: list[TutorBenchmarkFailureRead] = []
    for case in cases:
        if case.top1_correct:
            continue
        top = case.retrieved[0] if case.retrieved else None
        failures.append(
            TutorBenchmarkFailureRead(
                case_id=case.case_id,
                label=case.label,
                query=case.query,
                reason="top1_miss" if case.hit_at_k else "missed_at_k",
                first_relevant_rank=case.first_relevant_rank,
                top_chunk_id=top.chunk_id if top is not None else None,
                top_source_reference=top.source_reference if top is not None else None,
            )
        )
    return TutorBenchmarkModeRead(
        mode=mode,
        status="evaluated",
        retrieval_model=_MODE_MODELS[mode],
        evaluated_cases=count,
        top1_accuracy=round(sum(case.top1_correct for case in cases) / count, 4),
        hit_rate_at_k=round(sum(case.hit_at_k for case in cases) / count, 4),
        recall_at_k=round(sum(case.recall_at_k for case in cases) / count, 4),
        mean_reciprocal_rank=round(sum(case.reciprocal_rank for case in cases) / count, 4),
        mean_first_relevant_rank=(
            round(sum(first_ranks) / len(first_ranks), 4) if first_ranks else None
        ),
        failures=failures,
        cases=cases,
        note=f"Metrics are computed on the same {count} labeled cases at k={k}.",
    )


def _unavailable_mode(mode: BenchmarkMode, note: str) -> TutorBenchmarkModeRead:
    return TutorBenchmarkModeRead(
        mode=mode,
        status="unavailable",
        retrieval_model=_MODE_MODELS[mode],
        evaluated_cases=0,
        top1_accuracy=None,
        hit_rate_at_k=None,
        recall_at_k=None,
        mean_reciprocal_rank=None,
        mean_first_relevant_rank=None,
        note=note,
    )


def run_retrieval_benchmark(
    db: Session,
    course_id: str,
    payload: TutorRetrievalBenchmarkRequest,
    embedding_config: TutorEmbeddingConfig | None = None,
    embedding_provider: TutorEmbeddingProvider | None = None,
) -> TutorRetrievalBenchmarkRead:
    candidates = _candidate_rows(db, course_id, [])
    if not candidates:
        raise TutorBenchmarkError("Course has no processed chunks to benchmark")

    candidate_ids = {candidate.chunk.id for candidate in candidates}
    unknown = sorted(
        {
            chunk_id
            for case in payload.cases
            for chunk_id in case.relevant_chunk_ids
            if chunk_id not in candidate_ids
        }
    )
    if unknown:
        raise TutorBenchmarkError(
            "Benchmark references chunks that are not processed members of this course: "
            + ", ".join(unknown[:5])
        )

    config = embedding_config or TutorEmbeddingConfig()
    provider = embedding_provider
    semantic_requested = any(mode in {"semantic", "hybrid"} for mode in payload.modes)
    if semantic_requested and provider is None and config.provider != "none":
        provider = build_embedding_provider(config)

    results_by_mode: dict[BenchmarkMode, list[TutorBenchmarkCaseResultRead]] = {
        mode: [] for mode in payload.modes
    }
    unavailable_semantic = semantic_requested and provider is None

    for case in payload.cases:
        query_terms = list(dict.fromkeys(_tokens(case.query)))
        signals = _lexical_signals(db, course_id, candidates, case.query, query_terms)
        semantic_scores: dict[str, float] = {}
        if provider is not None and semantic_requested:
            semantic_scores = _semantic_scores(
                db,
                course_id,
                candidates,
                case.query,
                signals,
                provider,
                config.max_candidates,
                config.batch_size,
            )

        for mode in payload.modes:
            if mode in {"semantic", "hybrid"} and unavailable_semantic:
                continue
            ranked: list[_ScoredCandidate] = []
            for candidate in candidates:
                signal = signals[candidate.chunk.id]
                semantic = semantic_scores.get(candidate.chunk.id, 0.0)
                if not _eligible(mode, signal.lexical, semantic, signal.topic_affinity):
                    continue
                source_reference = (
                    f"{candidate.document.original_filename} — "
                    f"{candidate.chunk.source_label}"
                )
                ranked.append(
                    _ScoredCandidate(
                        chunk_id=candidate.chunk.id,
                        source_reference=source_reference,
                        score=_mode_score(
                            mode,
                            signal.lexical,
                            semantic,
                            signal.topic_affinity,
                        ),
                        lexical=signal.lexical,
                        semantic=semantic,
                        topic=signal.topic_affinity,
                    )
                )
            ranked.sort(
                key=lambda item: (
                    item.score,
                    item.lexical,
                    item.semantic,
                    item.topic,
                    item.chunk_id,
                ),
                reverse=True,
            )
            results_by_mode[mode].append(
                _case_result(
                    case.case_id,
                    case.label,
                    case.query,
                    case.relevant_chunk_ids,
                    ranked,
                    payload.k,
                    payload.max_results,
                )
            )

    mode_reads: list[TutorBenchmarkModeRead] = []
    for mode in payload.modes:
        if mode in {"semantic", "hybrid"} and unavailable_semantic:
            mode_reads.append(
                _unavailable_mode(
                    mode,
                    "No embedding provider is configured; lexical baselines were still evaluated.",
                )
            )
        else:
            mode_reads.append(_mode_summary(mode, results_by_mode[mode], payload.k))

    evaluated = [item for item in mode_reads if item.status == "evaluated"]
    best = max(
        evaluated,
        key=lambda item: (
            item.mean_reciprocal_rank or 0.0,
            item.top1_accuracy or 0.0,
            item.recall_at_k or 0.0,
            item.hit_rate_at_k or 0.0,
        ),
        default=None,
    )
    return TutorRetrievalBenchmarkRead(
        course_id=course_id,
        benchmark_model=_BENCHMARK_MODEL,
        case_count=len(payload.cases),
        k=payload.k,
        max_results=payload.max_results,
        best_mode=best.mode if best is not None else None,
        modes=mode_reads,
        note=(
            "All evaluated modes use the same labeled queries and relevant chunk IDs. "
            "This benchmark measures ranking quality, not end-to-end tutor answer correctness."
        ),
    )
