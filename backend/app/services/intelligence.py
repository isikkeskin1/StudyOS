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

# Unicode-aware tokens keep Italian/European course material intact.
# Tokens start with a letter and may contain digits afterwards (for example H2O).
_TOKEN_RE = re.compile(r"[^\W\d_][\w'-]*", re.UNICODE)
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
# Words that usually describe an instruction rather than a lesson/topic.
_INSTRUCTION_TOKENS = {
    "answer",
    "answers",
    "ask",
    "asked",
    "asks",
    "assume",
    "calculate",
    "choose",
    "compute",
    "consider",
    "derive",
    "determine",
    "draw",
    "evaluate",
    "explain",
    "find",
    "following",
    "given",
    "prove",
    "select",
    "show",
    "sketch",
    "solve",
    "state",
    "write",
}
# Short lines with these words are usually page furniture / assessment metadata.
_BOILERPLATE_TOKENS = {
    "academic",
    "candidate",
    "date",
    "department",
    "duration",
    "faculty",
    "instructor",
    "matricola",
    "name",
    "page",
    "pages",
    "professor",
    "school",
    "semester",
    "student",
    "surname",
    "university",
    "year",
}
_BOILERPLATE_PHRASES = (
    "academic year",
    "course code",
    "department of",
    "student id",
    "student number",
    "time allowed",
    "written exam",
    "politecnico di torino",
)
# These can be meaningful in prose but are poor standalone lesson names without structural evidence.
_WEAK_SINGLE_TOKENS = {
    "case",
    "cases",
    "data",
    "equation",
    "equations",
    "figure",
    "figures",
    "function",
    "functions",
    "method",
    "methods",
    "number",
    "numbers",
    "part",
    "parts",
    "result",
    "results",
    "section",
    "sections",
    "system",
    "systems",
    "table",
    "tables",
    "time",
    "value",
    "values",
}
_SENTENCE_VERBS = {
    "be",
    "describe",
    "describes",
    "give",
    "gives",
    "has",
    "have",
    "is",
    "means",
    "relate",
    "relates",
    "represent",
    "represents",
    "show",
    "shows",
    "use",
    "uses",
    "was",
    "were",
}
_EXAM_TYPES = {"past_exam", "past_exam_solution"}
_LECTURE_TYPES = {"lecture", "notes", "textbook", "exercise_sheet", "syllabus"}
_SECTION_PREFIX_RE = re.compile(
    r"^(?:(?:chapter|section|lecture|lesson|week|unit|module|topic)\s+)?"
    r"(?:\d+(?:\.\d+){0,3}|[ivxlcdm]+)[\s.):-]+",
    re.IGNORECASE,
)
_NAMED_PREFIX_RE = re.compile(
    r"^(?:chapter|section|lecture|lesson|week|unit|module|topic)\s*[:\-–—]\s*",
    re.IGNORECASE,
)
_PAGE_ONLY_RE = re.compile(
    r"^(?:page\s*)?\d+\s*(?:(?:of|/)\s*\d+)?$",
    re.IGNORECASE,
)


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
    heading_document_ids: set[str] = field(default_factory=set)
    exam_document_ids: set[str] = field(default_factory=set)
    lecture_document_ids: set[str] = field(default_factory=set)
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


def _heading_surface(line: str) -> tuple[str, bool]:
    original = line.strip()
    explicit_marker = original.startswith(("#", "*", "-", "•", "–", "—"))
    stripped = original.lstrip("#*•-–— \t").strip()

    numbered = bool(_SECTION_PREFIX_RE.match(stripped))
    stripped = _SECTION_PREFIX_RE.sub("", stripped, count=1).strip()
    named_prefix = bool(_NAMED_PREFIX_RE.match(stripped))
    stripped = _NAMED_PREFIX_RE.sub("", stripped, count=1).strip()

    return stripped.rstrip(":").strip(), explicit_marker or numbered or named_prefix


def _is_boilerplate(raw: str, words: list[str]) -> bool:
    lowered = " ".join(raw.lower().split())
    if not lowered or _PAGE_ONLY_RE.fullmatch(lowered):
        return True
    if any(phrase in lowered for phrase in _BOILERPLATE_PHRASES):
        return True

    meaningful = [word for word in words if word not in _STOPWORDS]
    if not meaningful:
        return True
    boilerplate_count = sum(
        word in _BOILERPLATE_TOKENS or word in _GENERIC_TOKENS
        for word in meaningful
    )
    return boilerplate_count == len(meaningful)


def _is_heading_candidate(
    line: str,
    *,
    previous_blank: bool = False,
    next_blank: bool = False,
) -> bool:
    stripped, structural_hint = _heading_surface(line)
    if not stripped or len(stripped) > 90:
        return False
    if stripped.endswith((".", "?", "!", ";")):
        return False

    words = _tokenize(stripped)
    if not 1 <= len(words) <= 8:
        return False
    if _is_boilerplate(stripped, words):
        return False
    if any(word in _INSTRUCTION_TOKENS or word in _SENTENCE_VERBS for word in words):
        return False

    meaningful = [
        word
        for word in words
        if word not in _STOPWORDS
        and word not in _GENERIC_TOKENS
        and word not in _BOILERPLATE_TOKENS
    ]
    if not meaningful:
        return False
    if len(words) == 1 and words[0] in _WEAK_SINGLE_TOKENS:
        return False

    surface_words = re.findall(r"[^\W\d_][\w'-]*", stripped, re.UNICODE)
    title_like = bool(surface_words) and (
        sum(word[:1].isupper() for word in surface_words) / len(surface_words) >= 0.65
    )
    letters = "".join(character for character in stripped if character.isalpha())
    all_caps = len(letters) >= 4 and letters.upper() == letters
    isolated = previous_blank and next_blank
    single_concept = len(words) == 1 and len(words[0]) >= 4

    # Do not infer a heading merely because a PDF happened to wrap a short sentence onto
    # its own line. Require some actual structural signal.
    return structural_hint or title_like or all_caps or isolated or single_concept


def _heading_candidates(text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        previous_blank = index == 0 or not lines[index - 1].strip()
        next_blank = index == len(lines) - 1 or not lines[index + 1].strip()
        if not _is_heading_candidate(
            line,
            previous_blank=previous_blank,
            next_blank=next_blank,
        ):
            continue
        raw, _ = _heading_surface(line)
        normalized = _normalize_phrase(raw)
        if normalized and not all(token in _GENERIC_TOKENS for token in normalized.split()):
            candidates.append((normalized, raw))
    return candidates


def _ngram_candidates(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()

    # Never let n-grams span a page line or sentence boundary. The old extractor did this,
    # which could manufacture phrases from the end of one sentence and the start of another.
    segments = re.split(r"(?:\n+|(?<=[.!?;:])\s+)", text)
    for segment in segments:
        tokens = _tokenize(segment)
        for size in (1, 2, 3):
            for index in range(len(tokens) - size + 1):
                phrase_tokens = tokens[index : index + size]
                if phrase_tokens[0] in _STOPWORDS or phrase_tokens[-1] in _STOPWORDS:
                    continue
                if any(
                    token in _INSTRUCTION_TOKENS
                    or token in _BOILERPLATE_TOKENS
                    or token in _SENTENCE_VERBS
                    for token in phrase_tokens
                ):
                    continue
                if all(token in _STOPWORDS or token in _GENERIC_TOKENS for token in phrase_tokens):
                    continue
                if any(len(token) < 3 for token in phrase_tokens):
                    continue
                if len(set(phrase_tokens)) != len(phrase_tokens):
                    continue
                if size == 1 and (
                    phrase_tokens[0] in _GENERIC_TOKENS
                    or phrase_tokens[0] in _WEAK_SINGLE_TOKENS
                ):
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
    if any(
        token in _INSTRUCTION_TOKENS
        or token in _BOILERPLATE_TOKENS
        or token in _SENTENCE_VERBS
        for token in tokens
    ):
        return False
    if all(token in _GENERIC_TOKENS or token in _STOPWORDS for token in tokens):
        return False
    if len(tokens) == 1 and tokens[0] in _WEAK_SINGLE_TOKENS:
        return False

    # Structural headings in teaching material are strong evidence on their own. Exam-only
    # headings are accepted only when teaching material independently mentions the same topic.
    if stats.heading_hits > 0:
        if stats.lecture_document_ids:
            return True
        if len(stats.heading_document_ids) >= 2:
            return True
        return bool(stats.exam_mentions and stats.lecture_mentions)

    # Body text should support/rank a lesson, not invent one from a random sentence. A body-only
    # topic therefore needs cross-document support and at least one teaching document.
    document_count = len(stats.document_ids)
    lecture_document_count = len(stats.lecture_document_ids)
    exam_document_count = len(stats.exam_document_ids)
    if document_count < 2 or lecture_document_count == 0:
        return False

    if len(tokens) == 1:
        return (
            stats.mention_count >= 5
            and (lecture_document_count >= 2 or exam_document_count >= 1)
        )

    return (
        stats.mention_count >= 3
        and (lecture_document_count >= 2 or exam_document_count >= 1)
    )


def _extract_topics(
    documents: list[Document],
    analyses: dict[str, DocumentAnalysis],
    chunks: list[DocumentChunk],
    *,
    limit: int = 20,
) -> list[TopicResult]:
    stats_by_phrase: dict[str, CandidateStats] = {}
    chunks_by_document: dict[str, list[DocumentChunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_document[chunk.document_id].append(chunk)

    for document in documents:
        analysis = analyses[document.id]
        doc_type = analysis.document_type
        # Exams should increase importance, but they should not dominate topic discovery.
        exam_multiplier = 1.7 if doc_type in _EXAM_TYPES else 1.0
        lecture_multiplier = 1.3 if doc_type in _LECTURE_TYPES else 1.0

        for chunk in chunks_by_document[document.id]:
            heading_candidates = _heading_candidates(chunk.text)
            for normalized, raw in heading_candidates:
                candidate = stats_by_phrase.setdefault(
                    normalized,
                    CandidateStats(display_name=raw),
                )
                if candidate.heading_hits == 0:
                    candidate.display_name = raw
                if doc_type in _LECTURE_TYPES:
                    score = 7.0
                elif doc_type in _EXAM_TYPES:
                    score = 4.0
                else:
                    score = 4.5
                candidate.heading_hits += 1
                candidate.mention_count += 1
                candidate.weighted_score += score
                candidate.document_ids.add(document.id)
                candidate.heading_document_ids.add(document.id)
                candidate.chunk_scores[chunk.id] = max(
                    candidate.chunk_scores.get(chunk.id, 0.0),
                    score,
                )
                if doc_type in _EXAM_TYPES:
                    candidate.exam_mentions += 1
                    candidate.exam_document_ids.add(document.id)
                if doc_type in _LECTURE_TYPES:
                    candidate.lecture_mentions += 1
                    candidate.lecture_document_ids.add(document.id)

            ngrams = _ngram_candidates(chunk.text)
            for normalized, count in ngrams.items():
                size = len(normalized.split())
                candidate = stats_by_phrase.setdefault(
                    normalized,
                    CandidateStats(display_name=_display_from_normalized(normalized)),
                )
                phrase_weight = 1.0 + (size - 1) * 0.35
                # A repeated footer or copied solution paragraph should not swamp the course graph.
                effective_count = min(count, 8)
                score = effective_count * phrase_weight * exam_multiplier * lecture_multiplier
                candidate.mention_count += count
                candidate.weighted_score += score
                candidate.document_ids.add(document.id)
                candidate.chunk_scores[chunk.id] = (
                    candidate.chunk_scores.get(chunk.id, 0.0) + score
                )
                if doc_type in _EXAM_TYPES:
                    candidate.exam_mentions += count
                    candidate.exam_document_ids.add(document.id)
                if doc_type in _LECTURE_TYPES:
                    candidate.lecture_mentions += count
                    candidate.lecture_document_ids.add(document.id)

    viable = [
        (normalized, stats)
        for normalized, stats in stats_by_phrase.items()
        if _candidate_quality(normalized, stats)
    ]
    viable.sort(
        key=lambda item: (
            item[1].heading_hits > 0,
            len(item[1].heading_document_ids),
            len(item[1].document_ids),
            item[1].weighted_score,
            len(item[0].split()),
        ),
        reverse=True,
    )

    selected: list[tuple[str, CandidateStats]] = []
    for normalized, stats in viable:
        redundant = False
        normalized_tokens = set(normalized.split())
        for chosen_normalized, chosen_stats in selected:
            chosen_tokens = set(chosen_normalized.split())
            contained = normalized in chosen_normalized or chosen_normalized in normalized
            overlap = (
                len(normalized_tokens & chosen_tokens)
                / max(1, min(len(normalized_tokens), len(chosen_tokens)))
            )
            if contained or overlap >= 0.85:
                if (
                    stats.heading_hits <= chosen_stats.heading_hits
                    and stats.weighted_score <= chosen_stats.weighted_score * 1.1
                ):
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
