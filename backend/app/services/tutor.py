from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course_intelligence import CourseTopic, TopicEvidence
from app.models.document import Document
from app.models.document_content import DocumentAnalysis, DocumentChunk, DocumentUnit
from app.schemas.tutor import (
    TutorAnswerRead,
    TutorAskRequest,
    TutorCitationRead,
    TutorSearchRead,
    TutorSearchRequest,
)
from app.services.tutor_embedding_index import ensure_chunk_embeddings
from app.services.tutor_embeddings import (
    TutorEmbeddingConfig,
    TutorEmbeddingFailure,
    TutorEmbeddingProvider,
    TutorEmbeddingUnavailable,
    build_embedding_provider,
    cosine_similarity,
)
from app.services.tutor_provider import (
    TutorProviderConfig,
    build_tutor_provider,
    validate_grounded_draft,
)

_LEXICAL_MODEL = "lexical-bm25-v1"
_TOPIC_MODEL = "hybrid-topic-bm25-v1"
_SEMANTIC_MODEL = "semantic-vector-rerank-v1"
_HYBRID_VECTOR_MODEL = "hybrid-vector-bm25-v1"
_ANSWER_MODE = "grounded-synthesis-v2"
_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+(?:['’-][a-zA-Z0-9]+)?")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "why",
    "with",
}


@dataclass(frozen=True)
class _Candidate:
    chunk: DocumentChunk
    unit: DocumentUnit
    document: Document
    document_type: str
    tokens: list[str]


@dataclass(frozen=True)
class _CandidateSignal:
    lexical: float
    topic_affinity: float
    matched: list[str]
    matched_topics: list[str]


@dataclass(frozen=True)
class _RetrievalResult:
    citations: list[TutorCitationRead]
    model: str
    components: list[str]
    topic_signal_applied: bool
    semantic_signal_applied: bool
    embedding_provider: str | None


def _tokens(text: str) -> list[str]:
    tokens = [
        match.group(0).lower().replace("’", "'")
        for match in _TOKEN_PATTERN.finditer(text)
    ]
    meaningful = [token for token in tokens if token not in _STOPWORDS]
    return meaningful or tokens


def _candidate_rows(
    db: Session,
    course_id: str,
    document_types: list[str],
) -> list[_Candidate]:
    rows = db.execute(
        select(DocumentChunk, DocumentUnit, Document, DocumentAnalysis)
        .join(DocumentUnit, DocumentUnit.id == DocumentChunk.unit_id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .outerjoin(DocumentAnalysis, DocumentAnalysis.document_id == Document.id)
        .where(Document.course_id == course_id, Document.status == "processed")
    ).all()

    allowed = {item.strip().lower() for item in document_types if item.strip()}
    candidates: list[_Candidate] = []
    for chunk, unit, document, analysis in rows:
        document_type = analysis.document_type if analysis is not None else "unknown"
        if allowed and document_type.lower() not in allowed:
            continue
        candidates.append(
            _Candidate(
                chunk=chunk,
                unit=unit,
                document=document,
                document_type=document_type,
                tokens=_tokens(chunk.text),
            )
        )
    return candidates


def _topic_signals(
    db: Session,
    course_id: str,
    query_terms: set[str],
) -> dict[str, tuple[float, list[str]]]:
    topics = list(
        db.scalars(select(CourseTopic).where(CourseTopic.course_id == course_id)).all()
    )
    matched_topics = [
        topic for topic in topics if query_terms & set(_tokens(topic.normalized_name))
    ]
    if not matched_topics:
        return {}

    topic_by_id = {topic.id: topic for topic in matched_topics}
    evidence = db.scalars(
        select(TopicEvidence).where(TopicEvidence.topic_id.in_(list(topic_by_id)))
    ).all()
    by_chunk: dict[str, tuple[float, list[str]]] = {}
    max_evidence = max((item.evidence_score for item in evidence), default=1.0)
    for item in evidence:
        topic = topic_by_id[item.topic_id]
        normalized_evidence = item.evidence_score / max(max_evidence, 1e-9)
        affinity = min(1.0, 0.6 * topic.importance_score + 0.4 * normalized_evidence)
        current_score, names = by_chunk.get(item.chunk_id, (0.0, []))
        if topic.name not in names:
            names = [*names, topic.name]
        by_chunk[item.chunk_id] = (max(current_score, affinity), names)
    return by_chunk


def _excerpt(text: str, max_chars: int = 620) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def _lexical_signals(
    db: Session,
    course_id: str,
    candidates: list[_Candidate],
    query: str,
    query_terms: list[str],
) -> dict[str, _CandidateSignal]:
    topic_signals = _topic_signals(db, course_id, set(query_terms))
    document_frequency = {
        term: sum(1 for candidate in candidates if term in set(candidate.tokens))
        for term in query_terms
    }
    average_length = max(
        sum(len(candidate.tokens) for candidate in candidates) / len(candidates),
        1.0,
    )
    count = len(candidates)
    query_phrase = " ".join(query.lower().split())
    signals: dict[str, _CandidateSignal] = {}

    for candidate in candidates:
        frequencies = Counter(candidate.tokens)
        matched = [term for term in query_terms if frequencies[term] > 0]
        topic_affinity, matched_topics = topic_signals.get(candidate.chunk.id, (0.0, []))
        bm25 = 0.0
        for term in matched:
            frequency = frequencies[term]
            df = document_frequency[term]
            idf = math.log(1.0 + (count - df + 0.5) / (df + 0.5))
            denominator = frequency + 1.2 * (
                1.0 - 0.75 + 0.75 * len(candidate.tokens) / average_length
            )
            bm25 += idf * (frequency * 2.2) / denominator

        coverage = len(matched) / len(query_terms)
        normalized_bm25 = bm25 / (bm25 + 2.0) if bm25 > 0 else 0.0
        phrase_match = bool(query_phrase and query_phrase in candidate.chunk.text.lower())
        phrase_bonus = 0.08 if phrase_match else 0.0
        lexical = min(1.0, 0.62 * coverage + 0.38 * normalized_bm25 + phrase_bonus)
        signals[candidate.chunk.id] = _CandidateSignal(
            lexical=lexical,
            topic_affinity=topic_affinity,
            matched=matched,
            matched_topics=matched_topics,
        )
    return signals


def _query_vector(provider: TutorEmbeddingProvider, query: str) -> list[float]:
    vectors = provider.embed([query])
    if len(vectors) != 1 or not vectors[0]:
        raise TutorEmbeddingFailure("Embedding provider returned an invalid query vector")
    normalized: list[float] = []
    for value in vectors[0]:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise TutorEmbeddingFailure(
                "Embedding provider returned a non-numeric query vector"
            ) from exc
        if not math.isfinite(number):
            raise TutorEmbeddingFailure("Embedding provider returned a non-finite query vector")
        normalized.append(number)
    return normalized


def _semantic_scores(
    db: Session,
    course_id: str,
    candidates: list[_Candidate],
    query: str,
    signals: dict[str, _CandidateSignal],
    provider: TutorEmbeddingProvider,
    max_candidates: int,
    batch_size: int,
) -> dict[str, float]:
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            signals[candidate.chunk.id].lexical + signals[candidate.chunk.id].topic_affinity,
            -candidate.chunk.chunk_index,
        ),
        reverse=True,
    )
    selected = ordered[:max_candidates]
    query_vector = _query_vector(provider, query)
    cache = ensure_chunk_embeddings(
        db,
        course_id,
        [candidate.chunk for candidate in selected],
        provider,
        batch_size=batch_size,
    )
    scores: dict[str, float] = {}
    for candidate in selected:
        vector = cache.vectors[candidate.chunk.id]
        scores[candidate.chunk.id] = max(0.0, cosine_similarity(query_vector, vector))
    return scores


def _rank(
    db: Session,
    course_id: str,
    candidates: list[_Candidate],
    query: str,
    limit: int,
    retrieval_mode: str,
    embedding_config: TutorEmbeddingConfig,
    embedding_provider: TutorEmbeddingProvider | None = None,
) -> _RetrievalResult:
    if not candidates:
        return _RetrievalResult([], _LEXICAL_MODEL, ["bm25"], False, False, None)

    query_terms = list(dict.fromkeys(_tokens(query)))
    if not query_terms:
        return _RetrievalResult([], _LEXICAL_MODEL, ["bm25"], False, False, None)

    signals = _lexical_signals(db, course_id, candidates, query, query_terms)
    provider = embedding_provider
    semantic_requested = retrieval_mode in {"semantic", "hybrid"}
    if retrieval_mode == "auto" and provider is None and embedding_config.provider != "none":
        provider = build_embedding_provider(embedding_config)
    elif semantic_requested and provider is None:
        provider = build_embedding_provider(embedding_config)
        if provider is None:
            raise TutorEmbeddingUnavailable(
                "Semantic retrieval requested but no embedding provider is configured"
            )

    semantic_scores: dict[str, float] = {}
    resolved_mode = retrieval_mode
    if retrieval_mode == "auto":
        resolved_mode = "hybrid" if provider is not None else "lexical"
    if resolved_mode in {"semantic", "hybrid"} and provider is not None:
        semantic_scores = _semantic_scores(
            db,
            course_id,
            candidates,
            query,
            signals,
            provider,
            embedding_config.max_candidates,
            embedding_config.batch_size,
        )

    scored: list[tuple[float, float, float, float, _CandidateSignal, _Candidate]] = []
    for candidate in candidates:
        signal = signals[candidate.chunk.id]
        semantic = semantic_scores.get(candidate.chunk.id, 0.0)
        if resolved_mode == "semantic":
            relevance = min(1.0, 0.90 * semantic + 0.10 * signal.topic_affinity)
            include = semantic > 0 or signal.topic_affinity > 0
        elif resolved_mode == "hybrid" and provider is not None:
            relevance = min(
                1.0,
                0.50 * signal.lexical + 0.35 * semantic + 0.15 * signal.topic_affinity,
            )
            include = signal.lexical > 0 or semantic > 0 or signal.topic_affinity > 0
        else:
            relevance = min(1.0, 0.78 * signal.lexical + 0.22 * signal.topic_affinity)
            include = signal.lexical > 0 or signal.topic_affinity > 0
        if include:
            scored.append(
                (
                    relevance,
                    signal.lexical,
                    semantic,
                    signal.topic_affinity,
                    signal,
                    candidate,
                )
            )

    scored.sort(
        key=lambda item: (item[0], item[1], item[2], item[3], -item[5].chunk.chunk_index),
        reverse=True,
    )

    citations: list[TutorCitationRead] = []
    for rank, item in enumerate(scored[:limit], start=1):
        relevance, lexical, semantic, topic_affinity, signal, candidate = item
        citations.append(
            TutorCitationRead(
                rank=rank,
                document_id=candidate.document.id,
                document_name=candidate.document.original_filename,
                document_type=candidate.document_type,
                chunk_id=candidate.chunk.id,
                source_label=candidate.chunk.source_label,
                locator_type=candidate.unit.locator_type,
                locator_index=candidate.unit.locator_index,
                source_reference=(
                    f"{candidate.document.original_filename} — {candidate.chunk.source_label}"
                ),
                excerpt=_excerpt(candidate.chunk.text),
                relevance_score=round(relevance, 4),
                lexical_score=round(lexical, 4),
                semantic_score=round(semantic, 4),
                topic_affinity=round(topic_affinity, 4),
                term_coverage=round(len(signal.matched) / len(query_terms), 4),
                matched_terms=signal.matched,
                matched_topics=signal.matched_topics,
            )
        )

    topic_applied = any(citation.topic_affinity > 0 for citation in citations)
    semantic_applied = bool(provider is not None and semantic_scores)
    if resolved_mode == "semantic" and semantic_applied:
        model = _SEMANTIC_MODEL
        components = ["embedding_cosine", "persistent_embedding_cache", "course_topic_evidence"]
    elif resolved_mode == "hybrid" and semantic_applied:
        model = _HYBRID_VECTOR_MODEL
        components = [
            "bm25",
            "embedding_cosine",
            "persistent_embedding_cache",
            "course_topic_evidence",
        ]
    elif topic_applied:
        model = _TOPIC_MODEL
        components = ["bm25", "course_topic_evidence"]
    else:
        model = _LEXICAL_MODEL
        components = ["bm25"]
    if not topic_applied:
        components = [item for item in components if item != "course_topic_evidence"]

    return _RetrievalResult(
        citations=citations,
        model=model,
        components=components,
        topic_signal_applied=topic_applied,
        semantic_signal_applied=semantic_applied,
        embedding_provider=provider.name if semantic_applied else None,
    )


def _retrieve(
    db: Session,
    course_id: str,
    query: str,
    limit: int,
    document_types: list[str],
    retrieval_mode: str,
    embedding_config: TutorEmbeddingConfig | None = None,
    embedding_provider: TutorEmbeddingProvider | None = None,
) -> _RetrievalResult:
    return _rank(
        db,
        course_id,
        _candidate_rows(db, course_id, document_types),
        query,
        limit,
        retrieval_mode,
        embedding_config or TutorEmbeddingConfig(),
        embedding_provider,
    )


def search_course_material(
    db: Session,
    course_id: str,
    payload: TutorSearchRequest,
    embedding_config: TutorEmbeddingConfig | None = None,
    embedding_provider: TutorEmbeddingProvider | None = None,
) -> TutorSearchRead:
    result = _retrieve(
        db,
        course_id,
        payload.query,
        payload.limit,
        payload.document_types,
        payload.retrieval_mode,
        embedding_config,
        embedding_provider,
    )
    return TutorSearchRead(
        course_id=course_id,
        query=payload.query,
        retrieval_model=result.model,
        retrieval_components=result.components,
        topic_signal_applied=result.topic_signal_applied,
        semantic_signal_applied=result.semantic_signal_applied,
        embedding_provider=result.embedding_provider,
        result_count=len(result.citations),
        citations=result.citations,
    )


def _insufficient_answer(
    course_id: str,
    payload: TutorAskRequest,
    result: _RetrievalResult,
    note: str,
) -> TutorAnswerRead:
    return TutorAnswerRead(
        course_id=course_id,
        question=payload.question,
        answer_mode=_ANSWER_MODE,
        answer_style=payload.answer_style,
        provider_requested=payload.provider,
        synthesis_provider="not_run",
        retrieval_model=result.model,
        retrieval_components=result.components,
        topic_signal_applied=result.topic_signal_applied,
        semantic_signal_applied=result.semantic_signal_applied,
        embedding_provider=result.embedding_provider,
        grounding_status="insufficient_evidence",
        validation_status="not_run",
        answer=(
            "I couldn't find enough support for that answer in the processed course material. "
            "Upload or process a relevant source, or ask a question covered by the current course."
        ),
        citation_coverage=0.0,
        grounding_score=0.0,
        citations=[],
        note=note,
    )


def answer_from_course_material(
    db: Session,
    course_id: str,
    payload: TutorAskRequest,
    provider_config: TutorProviderConfig | None = None,
    embedding_config: TutorEmbeddingConfig | None = None,
    embedding_provider: TutorEmbeddingProvider | None = None,
) -> TutorAnswerRead:
    result = _retrieve(
        db,
        course_id,
        payload.question,
        payload.max_sources,
        payload.document_types,
        payload.retrieval_mode,
        embedding_config,
        embedding_provider,
    )
    supported = [
        citation
        for citation in result.citations
        if citation.relevance_score >= payload.minimum_relevance
    ]
    if not supported:
        return _insufficient_answer(
            course_id,
            payload,
            result,
            "Retrieved course evidence did not meet the minimum relevance threshold.",
        )

    ranked = [
        citation.model_copy(update={"rank": index})
        for index, citation in enumerate(supported, 1)
    ]
    provider = build_tutor_provider(
        payload.provider,
        provider_config or TutorProviderConfig(),
    )
    draft = provider.synthesize(payload.question, ranked, payload.answer_style)
    if draft.insufficient_evidence:
        response = _insufficient_answer(
            course_id,
            payload,
            result,
            "The synthesis provider determined that the citation packet was insufficient.",
        )
        return response.model_copy(update={"synthesis_provider": draft.provider})

    validation = validate_grounded_draft(draft, ranked)
    if validation.status != "passed":
        response = _insufficient_answer(
            course_id,
            payload,
            result,
            (
                "The generated draft was rejected because one or more claims were uncited, "
                "invalidly cited, or insufficiently supported by the cited excerpt."
            ),
        )
        return response.model_copy(
            update={
                "synthesis_provider": draft.provider,
                "validation_status": "rejected",
                "validation_model": validation.model,
                "citation_coverage": validation.citation_coverage,
                "grounding_score": validation.grounding_score,
                "minimum_claim_support": validation.minimum_support_score,
                "validated_claim_count": validation.validated_claim_count,
                "unsupported_claim_count": validation.unsupported_claim_count,
            }
        )

    return TutorAnswerRead(
        course_id=course_id,
        question=payload.question,
        answer_mode=_ANSWER_MODE,
        answer_style=payload.answer_style,
        provider_requested=payload.provider,
        synthesis_provider=draft.provider,
        retrieval_model=result.model,
        retrieval_components=result.components,
        topic_signal_applied=result.topic_signal_applied,
        semantic_signal_applied=result.semantic_signal_applied,
        embedding_provider=result.embedding_provider,
        grounding_status="supported",
        validation_status="passed",
        validation_model=validation.model,
        answer=draft.answer,
        citation_coverage=validation.citation_coverage,
        grounding_score=validation.grounding_score,
        minimum_claim_support=validation.minimum_support_score,
        validated_claim_count=validation.validated_claim_count,
        unsupported_claim_count=0,
        citations=ranked,
        note=(
            "The answer was generated through a provider-neutral grounded synthesis interface and "
            "accepted only after local claim-to-citation validation."
        ),
    )