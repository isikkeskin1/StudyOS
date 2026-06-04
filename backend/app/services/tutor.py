from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_content import DocumentAnalysis, DocumentChunk, DocumentUnit
from app.schemas.tutor import (
    TutorAnswerRead,
    TutorAskRequest,
    TutorCitationRead,
    TutorSearchRead,
    TutorSearchRequest,
)

_RETRIEVAL_MODEL = "lexical-bm25-v1"
_ANSWER_MODE = "extractive-grounded-v1"
_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+(?:['’-][a-zA-Z0-9]+)?")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
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


def _tokens(text: str) -> list[str]:
    tokens = [match.group(0).lower().replace("’", "'") for match in _TOKEN_PATTERN.finditer(text)]
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


def _excerpt(text: str, max_chars: int = 620) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def _rank(
    candidates: list[_Candidate],
    query: str,
    limit: int,
) -> list[TutorCitationRead]:
    if not candidates:
        return []

    query_terms = list(dict.fromkeys(_tokens(query)))
    if not query_terms:
        return []

    document_frequency = {
        term: sum(1 for candidate in candidates if term in set(candidate.tokens))
        for term in query_terms
    }
    average_length = sum(len(candidate.tokens) for candidate in candidates) / len(candidates)
    average_length = max(average_length, 1.0)
    count = len(candidates)
    query_phrase = " ".join(query.lower().split())

    scored: list[tuple[float, float, list[str], _Candidate]] = []
    for candidate in candidates:
        frequencies = Counter(candidate.tokens)
        matched = [term for term in query_terms if frequencies[term] > 0]
        if not matched:
            continue

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
        normalized_bm25 = bm25 / (bm25 + 2.0)
        phrase_match = query_phrase and query_phrase in candidate.chunk.text.lower()
        phrase_bonus = 0.08 if phrase_match else 0.0
        relevance = min(1.0, 0.62 * coverage + 0.38 * normalized_bm25 + phrase_bonus)
        scored.append((relevance, coverage, matched, candidate))

    scored.sort(
        key=lambda item: (
            item[0],
            item[1],
            -item[3].chunk.chunk_index,
        ),
        reverse=True,
    )

    citations: list[TutorCitationRead] = []
    for rank, (relevance, coverage, matched, candidate) in enumerate(scored[:limit], start=1):
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
                term_coverage=round(coverage, 4),
                matched_terms=matched,
            )
        )
    return citations


def search_course_material(
    db: Session,
    course_id: str,
    payload: TutorSearchRequest,
) -> TutorSearchRead:
    citations = _rank(
        _candidate_rows(db, course_id, payload.document_types),
        payload.query,
        payload.limit,
    )
    return TutorSearchRead(
        course_id=course_id,
        query=payload.query,
        retrieval_model=_RETRIEVAL_MODEL,
        result_count=len(citations),
        citations=citations,
    )


def _best_sentence(excerpt: str, query_terms: set[str]) -> tuple[float, str] | None:
    best: tuple[float, str] | None = None
    for sentence in _SENTENCE_SPLIT.split(excerpt):
        clean = " ".join(sentence.split()).strip()
        if len(clean) < 12:
            continue
        sentence_terms = set(_tokens(clean))
        overlap = len(query_terms & sentence_terms)
        if overlap == 0:
            continue
        score = overlap / max(1, len(query_terms))
        if best is None or score > best[0]:
            best = (score, clean)
    return best


def answer_from_course_material(
    db: Session,
    course_id: str,
    payload: TutorAskRequest,
) -> TutorAnswerRead:
    citations = _rank(
        _candidate_rows(db, course_id, payload.document_types),
        payload.question,
        payload.max_sources,
    )
    supported = [
        citation for citation in citations if citation.relevance_score >= payload.minimum_relevance
    ]

    if not supported:
        return TutorAnswerRead(
            course_id=course_id,
            question=payload.question,
            answer_mode=_ANSWER_MODE,
            retrieval_model=_RETRIEVAL_MODEL,
            grounding_status="insufficient_evidence",
            answer=(
                "I couldn't find enough support for that answer in the processed course material. "
                "Upload or process a relevant source, or ask a question covered by the "
                "current course."
            ),
            citation_coverage=0.0,
            citations=[],
            note=(
                "No answer was synthesized because the retrieved course evidence did not meet the "
                "minimum relevance threshold."
            ),
        )

    query_terms = set(_tokens(payload.question))
    answer_parts: list[str] = []
    used_citations: list[TutorCitationRead] = []
    seen_sentences: set[str] = set()
    for citation in supported:
        best = _best_sentence(citation.excerpt, query_terms)
        if best is None:
            continue
        sentence = best[1]
        normalized = sentence.lower()
        if normalized in seen_sentences:
            continue
        seen_sentences.add(normalized)
        used_citations.append(citation.model_copy(update={"rank": len(used_citations) + 1}))
        answer_parts.append(f"{sentence} [{len(used_citations)}]")
        if len(answer_parts) == 3:
            break

    if not answer_parts:
        return TutorAnswerRead(
            course_id=course_id,
            question=payload.question,
            answer_mode=_ANSWER_MODE,
            retrieval_model=_RETRIEVAL_MODEL,
            grounding_status="insufficient_evidence",
            answer=(
                "I found related material, but not a sufficiently direct statement to answer the "
                "question without guessing."
            ),
            citation_coverage=0.0,
            citations=[],
            note="Related chunks were retrieved, but no direct grounded sentence was selected.",
        )

    return TutorAnswerRead(
        course_id=course_id,
        question=payload.question,
        answer_mode=_ANSWER_MODE,
        retrieval_model=_RETRIEVAL_MODEL,
        grounding_status="supported",
        answer=" ".join(answer_parts),
        citation_coverage=1.0,
        citations=used_citations,
        note=(
            "This is a deterministic extractive answer grounded only in processed course material. "
            "A later LLM adapter can synthesize richer explanations from the same citation packet."
        ),
    )
