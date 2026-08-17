from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.course_intelligence import (
    CourseAnalysis,
    CourseTopic,
    TopicEvidence,
    TopicRelationship,
)
from app.models.document import Document
from app.models.document_content import DocumentAnalysis, DocumentChunk

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9']*")
_STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "and",
    "any",
    "are",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "but",
    "can",
    "could",
    "does",
    "each",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "into",
    "its",
    "may",
    "more",
    "most",
    "not",
    "of",
    "off",
    "only",
    "or",
    "other",
    "our",
    "out",
    "over",
    "same",
    "should",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "through",
    "to",
    "under",
    "using",
    "very",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "will",
    "with",
    "would",
    "you",
    "your",
}
_GENERIC_TOKENS = {
    "answer",
    "answers",
    "chapter",
    "course",
    "example",
    "examples",
    "exam",
    "exercise",
    "exercises",
    "final",
    "lecture",
    "lectures",
    "midterm",
    "notes",
    "paper",
    "papers",
    "physics",
    "problem",
    "problems",
    "question",
    "questions",
    "solution",
    "solutions",
    "slide",
    "slides",
    "test",
    "tests",
    "written",
}
_EXAM_TYPES = {"past_exam", "past_exam_solution"}
_LECTURE_TYPES = {"lecture", "notes", "textbook", "exercise_sheet", "syllabus"}


class NoProcessedDocumentsError(RuntimeError):
    pass


@dataclass
class CandidateStats:
    display_name: str
    mention_count: int = 0
    exam_mentions: int = 0
    lecture_mentions: int = 0
    weighted_score: float = 0.0
    heading_hits: int = 0
    document_ids: set[str] = field(default_factory=set)
    chunk_scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TopicResult:
    name: str
    normalized_name: str
    importance_score: float
    mention_count: int
    document_count: int
    exam_mention_count: int
    lecture_mention_count: int
    chunk_scores: dict[str, float]


def _normalize_token(token: str) -> str:
    lowered = token.lower()
    if lowered.endswith("'s"):
        lowered = lowered[:-2]
    return lowered


def _tokenize(text: str) -> list[str]:
    return [_normalize_token(token) for token in _TOKEN_RE.findall(text)]


def _normalize_phrase(text: str) -> str:
    tokens = [token for token in _tokenize(text) if token not in _STOPWORDS]
    return " ".join(tokens)


def _display_from_normalized(normalized: str) -> str:
    return " ".join(word.capitalize() if len(word) > 3 else word for word in normalized.split())


def _is_heading_candidate(line: str) -> bool:
    stripped = line.strip().lstrip("#*- ").strip()
    if not stripped or len(stripped) > 90:
        return False
    words = _tokenize(stripped)
    if not 1 <= len(words) <= 8:
        return False
    if stripped.endswith((".", "?", "!")):
        return False
    if words[0] in _GENERIC_TOKENS:
        return False
    meaningful = [word for word in words if word not in _STOPWORDS and word not in _GENERIC_TOKENS]
    return bool(meaningful)


def _heading_candidates(text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not _is_heading_candidate(line):
            continue
        raw = line.strip().lstrip("#*- ").strip()
        normalized = _normalize_phrase(raw)
        if normalized and not all(token in _GENERIC_TOKENS for token in normalized.split()):
            candidates.append((normalized, raw))
    return candidates


def _ngram_candidates(text: str) -> Counter[str]:
    tokens = _tokenize(text)
    counts: Counter[str] = Counter()

    for size in (1, 2, 3):
        for index in range(len(tokens) - size + 1):
            phrase_tokens = tokens[index : index + size]
            if phrase_tokens[0] in _STOPWORDS or phrase_tokens[-1] in _STOPWORDS:
                continue
            if all(token in _STOPWORDS or token in _GENERIC_TOKENS for token in phrase_tokens):
                continue
            if any(len(token) < 3 for token in phrase_tokens):
                continue
            if size == 1 and phrase_tokens[0] in _GENERIC_TOKENS:
                continue
            normalized = " ".join(phrase_tokens)
            counts[normalized] += 1

    return counts


def _snippet(text: str, normalized_phrase: str, *, radius: int = 130) -> str:
    lowered = text.lower()
    first_word = normalized_phrase.split()[0]
    index = lowered.find(first_word)
    if index < 0:
        return text[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(text), index + len(normalized_phrase) + radius)
    snippet = text[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(text):
        snippet = f"{snippet}..."
    return snippet


def _candidate_quality(normalized: str, stats: CandidateStats) -> bool:
    tokens = normalized.split()
    if not tokens or len(tokens) > 4:
        return False
    if any(token.isdigit() for token in tokens):
        return False
    if all(token in _GENERIC_TOKENS or token in _STOPWORDS for token in tokens):
        return False
    if len(tokens) == 1 and stats.mention_count < 3 and stats.heading_hits == 0:
        return False
    if len(tokens) > 1 and stats.mention_count < 2 and stats.heading_hits == 0:
        return False
    return True


def _extract_topics(
    documents: list[Document],
    analyses: dict[str, DocumentAnalysis],
    chunks: list[DocumentChunk],
    *,
    limit: int = 30,
) -> list[TopicResult]:
    stats_by_phrase: dict[str, CandidateStats] = {}
    chunks_by_document: dict[str, list[DocumentChunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_document[chunk.document_id].append(chunk)

    for document in documents:
        analysis = analyses[document.id]
        doc_type = analysis.document_type
        exam_multiplier = 2.4 if doc_type in _EXAM_TYPES else 1.0
        lecture_multiplier = 1.2 if doc_type in _LECTURE_TYPES else 1.0

        for chunk in chunks_by_document[document.id]:
            heading_candidates = _heading_candidates(chunk.text)
            for normalized, raw in heading_candidates:
                candidate = stats_by_phrase.setdefault(
                    normalized,
                    CandidateStats(display_name=raw),
                )
                score = 4.0 * exam_multiplier * lecture_multiplier
                candidate.heading_hits += 1
                candidate.mention_count += 1
                candidate.weighted_score += score
                candidate.document_ids.add(document.id)
                candidate.chunk_scores[chunk.id] = max(
                    candidate.chunk_scores.get(chunk.id, 0.0),
                    score,
                )
                if doc_type in _EXAM_TYPES:
                    candidate.exam_mentions += 1
                if doc_type in _LECTURE_TYPES:
                    candidate.lecture_mentions += 1

            ngrams = _ngram_candidates(chunk.text)
            for normalized, count in ngrams.items():
                size = len(normalized.split())
                candidate = stats_by_phrase.setdefault(
                    normalized,
                    CandidateStats(display_name=_display_from_normalized(normalized)),
                )
                phrase_weight = 1.0 + (size - 1) * 0.35
                score = count * phrase_weight * exam_multiplier * lecture_multiplier
                candidate.mention_count += count
                candidate.weighted_score += score
                candidate.document_ids.add(document.id)
                candidate.chunk_scores[chunk.id] = (
                    candidate.chunk_scores.get(chunk.id, 0.0) + score
                )
                if doc_type in _EXAM_TYPES:
                    candidate.exam_mentions += count
                if doc_type in _LECTURE_TYPES:
                    candidate.lecture_mentions += count

    viable = [
        (normalized, stats)
        for normalized, stats in stats_by_phrase.items()
        if _candidate_quality(normalized, stats)
    ]
    viable.sort(
        key=lambda item: (
            item[1].weighted_score,
            item[1].heading_hits,
            len(item[0].split()),
        ),
        reverse=True,
    )

    selected: list[tuple[str, CandidateStats]] = []
    for normalized, stats in viable:
        redundant = False
        for chosen_normalized, chosen_stats in selected:
            if normalized in chosen_normalized or chosen_normalized in normalized:
                if stats.weighted_score <= chosen_stats.weighted_score * 0.9:
                    redundant = True
                    break
        if redundant:
            continue
        selected.append((normalized, stats))
        if len(selected) >= limit:
            break

    if not selected:
        return []

    max_score = max(stats.weighted_score for _, stats in selected)
    results: list[TopicResult] = []
    for normalized, stats in selected:
        importance = min(1.0, stats.weighted_score / max_score if max_score else 0.0)
        results.append(
            TopicResult(
                name=stats.display_name,
                normalized_name=normalized,
                importance_score=round(importance, 4),
                mention_count=stats.mention_count,
                document_count=len(stats.document_ids),
                exam_mention_count=stats.exam_mentions,
                lecture_mention_count=stats.lecture_mentions,
                chunk_scores=dict(stats.chunk_scores),
            )
        )
    return results


def analyze_course(db: Session, course_id: str) -> CourseAnalysis:
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.course_id == course_id, Document.status == "processed")
            .order_by(Document.created_at)
        ).all()
    )
    if not documents:
        raise NoProcessedDocumentsError("Process at least one course document before analysis")

    document_ids = [document.id for document in documents]
    analyses = {
        analysis.document_id: analysis
        for analysis in db.scalars(
            select(DocumentAnalysis).where(DocumentAnalysis.document_id.in_(document_ids))
        ).all()
    }
    documents = [document for document in documents if document.id in analyses]
    if not documents:
        raise NoProcessedDocumentsError("Process at least one course document before analysis")

    document_ids = [document.id for document in documents]
    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id.in_(document_ids))
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        ).all()
    )

    topics = _extract_topics(documents, analyses, chunks)
    chunk_lookup = {chunk.id: chunk for chunk in chunks}

    existing_topic_ids = list(
        db.scalars(select(CourseTopic.id).where(CourseTopic.course_id == course_id)).all()
    )
    if existing_topic_ids:
        db.execute(delete(TopicEvidence).where(TopicEvidence.topic_id.in_(existing_topic_ids)))
    db.execute(delete(TopicRelationship).where(TopicRelationship.course_id == course_id))
    db.execute(delete(CourseTopic).where(CourseTopic.course_id == course_id))
    db.execute(delete(CourseAnalysis).where(CourseAnalysis.course_id == course_id))

    topic_models: list[CourseTopic] = []
    topic_by_normalized: dict[str, CourseTopic] = {}
    topic_chunk_sets: dict[str, set[str]] = {}

    for topic in topics:
        model = CourseTopic(
            id=str(uuid4()),
            course_id=course_id,
            name=topic.name,
            normalized_name=topic.normalized_name,
            importance_score=topic.importance_score,
            mention_count=topic.mention_count,
            document_count=topic.document_count,
            exam_mention_count=topic.exam_mention_count,
            lecture_mention_count=topic.lecture_mention_count,
        )
        db.add(model)
        topic_models.append(model)
        topic_by_normalized[topic.normalized_name] = model
        topic_chunk_sets[topic.normalized_name] = set(topic.chunk_scores)

        evidence_items = sorted(
            topic.chunk_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        for chunk_id, score in evidence_items:
            chunk = chunk_lookup[chunk_id]
            db.add(
                TopicEvidence(
                    id=str(uuid4()),
                    topic_id=model.id,
                    document_id=chunk.document_id,
                    chunk_id=chunk.id,
                    source_label=chunk.source_label,
                    snippet=_snippet(chunk.text, topic.normalized_name),
                    evidence_score=round(score, 4),
                )
            )

    relationships: list[tuple[str, str, int, float]] = []
    for first, second in combinations(topics, 2):
        first_chunks = topic_chunk_sets[first.normalized_name]
        second_chunks = topic_chunk_sets[second.normalized_name]
        cooccurrence = len(first_chunks & second_chunks)
        if cooccurrence == 0:
            continue
        denominator = math.sqrt(max(1, len(first_chunks)) * max(1, len(second_chunks)))
        weight = min(1.0, cooccurrence / denominator)
        relationships.append(
            (
                first.normalized_name,
                second.normalized_name,
                cooccurrence,
                round(weight, 4),
            )
        )

    relationships.sort(key=lambda item: (item[2], item[3]), reverse=True)
    relationships = relationships[:100]

    for first_name, second_name, count, weight in relationships:
        db.add(
            TopicRelationship(
                id=str(uuid4()),
                course_id=course_id,
                source_topic_id=topic_by_normalized[first_name].id,
                target_topic_id=topic_by_normalized[second_name].id,
                cooccurrence_count=count,
                weight=weight,
            )
        )

    analysis_model = CourseAnalysis(
        course_id=course_id,
        analyzed_document_count=len(documents),
        topic_count=len(topic_models),
        relationship_count=len(relationships),
    )
    db.add(analysis_model)
    db.commit()
    db.refresh(analysis_model)
    return analysis_model
