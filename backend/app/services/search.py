from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cheat_sheet import CheatSheet
from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import DiagnosticResponse, DiagnosticSession
from app.models.document import Document
from app.models.document_content import DocumentChunk
from app.models.forecast_tracking import GradeForecastSnapshot
from app.models.mistakes import DiagnosticMistake
from app.models.tutor_practice import (
    TutorPracticeAttempt,
    TutorPracticeItem,
    TutorPracticeMistake,
)
from app.schemas.search import GlobalSearchRead, GlobalSearchResultRead

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+.-]*", re.IGNORECASE)


@dataclass(frozen=True)
class _Candidate:
    kind: str
    id: str
    course_id: str
    course_name: str
    title: str
    subtitle: str | None
    excerpt: str | None
    haystack: str
    href: str
    boost: float = 1.0


def _tokens(value: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(value)]


def _snippet(text: str, tokens: list[str], limit: int = 220) -> str:
    compact = " ".join(text.split())
    if not compact:
        return ""
    lowered = compact.lower()
    positions = [lowered.find(token) for token in tokens]
    positions = [position for position in positions if position >= 0]
    if not positions or len(compact) <= limit:
        return compact[:limit]
    start = max(0, min(positions) - 60)
    end = min(len(compact), start + limit)
    prefix = "…" if start else ""
    suffix = "…" if end < len(compact) else ""
    return prefix + compact[start:end].strip() + suffix


def _score(candidate: _Candidate, tokens: list[str], query: str) -> float:
    title = candidate.title.lower()
    subtitle = (candidate.subtitle or "").lower()
    haystack = candidate.haystack.lower()
    exact = query.lower()
    total = 0.0
    if exact and exact in title:
        total += 8.0
    elif exact and exact in haystack:
        total += 4.0
    for token in tokens:
        if token in title:
            total += 3.0
        if token in subtitle:
            total += 1.5
        occurrences = haystack.count(token)
        total += min(occurrences, 6) * 0.65
    return round(total * candidate.boost, 4)


def global_search(
    db: Session,
    query: str,
    *,
    course_id: str | None = None,
    kinds: set[str] | None = None,
    limit: int = 30,
) -> GlobalSearchRead:
    normalized = " ".join(query.split()).strip()
    tokens = _tokens(normalized)
    if not tokens:
        return GlobalSearchRead(query=normalized, result_count=0, results=[])

    courses = list(db.scalars(select(Course).order_by(Course.name, Course.id)).all())
    if course_id is not None:
        courses = [course for course in courses if course.id == course_id]
    if not courses:
        return GlobalSearchRead(query=normalized, result_count=0, results=[])

    course_by_id = {course.id: course for course in courses}
    course_ids = set(course_by_id)
    candidates: list[_Candidate] = []

    def allow(kind: str) -> bool:
        return kinds is None or kind in kinds

    if allow("course"):
        for course in courses:
            candidates.append(
                _Candidate(
                    kind="course",
                    id=course.id,
                    course_id=course.id,
                    course_name=course.name,
                    title=course.name,
                    subtitle="Course",
                    excerpt=None,
                    haystack=course.name,
                    href=f"/courses/{course.id}",
                    boost=1.35,
                )
            )

    if allow("topic"):
        rows = db.scalars(
            select(CourseTopic).where(CourseTopic.course_id.in_(course_ids))
        ).all()
        for topic in rows:
            course = course_by_id[topic.course_id]
            candidates.append(
                _Candidate(
                    kind="topic",
                    id=topic.id,
                    course_id=course.id,
                    course_name=course.name,
                    title=topic.name,
                    subtitle=f"Topic · importance {topic.importance_score:.2f}",
                    excerpt=None,
                    haystack=f"{topic.name} {topic.normalized_name}",
                    href=f"/courses/{course.id}?tab=topics&topic={topic.id}",
                    boost=1.25,
                )
            )

    if allow("source"):
        rows = db.execute(
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.course_id.in_(course_ids))
        ).all()
        for chunk, document in rows:
            course = course_by_id[document.course_id]
            candidates.append(
                _Candidate(
                    kind="source",
                    id=chunk.id,
                    course_id=course.id,
                    course_name=course.name,
                    title=document.original_filename,
                    subtitle=chunk.source_label,
                    excerpt=chunk.text,
                    haystack=f"{document.original_filename} {chunk.source_label} {chunk.text}",
                    href=(
                        f"/courses/{course.id}?tab=sources"
                        f"&document={document.id}&chunk={chunk.id}"
                    ),
                )
            )

    if allow("practice"):
        rows = db.scalars(
            select(TutorPracticeItem).where(TutorPracticeItem.course_id.in_(course_ids))
        ).all()
        for item in rows:
            course = course_by_id[item.course_id]
            candidates.append(
                _Candidate(
                    kind="practice",
                    id=item.id,
                    course_id=course.id,
                    course_name=course.name,
                    title=item.topic_name,
                    subtitle=f"Practice · {item.difficulty} · {item.marks} marks",
                    excerpt=item.question,
                    haystack=f"{item.topic_name} {item.question} {item.solution}",
                    href=f"/courses/{course.id}?tab=tutor&practice={item.id}",
                )
            )

    if allow("mistake"):
        diagnostic_rows = db.execute(
            select(DiagnosticMistake, DiagnosticSession.course_id)
            .join(
                DiagnosticResponse,
                DiagnosticResponse.id == DiagnosticMistake.response_id,
            )
            .join(
                DiagnosticSession,
                DiagnosticSession.id == DiagnosticResponse.session_id,
            )
            .where(DiagnosticSession.course_id.in_(course_ids))
        ).all()
        for mistake, cid in diagnostic_rows:
            course = course_by_id[cid]
            candidates.append(
                _Candidate(
                    kind="mistake",
                    id=mistake.id,
                    course_id=course.id,
                    course_name=course.name,
                    title=mistake.category.replace("_", " "),
                    subtitle="Diagnostic mistake",
                    excerpt=mistake.note,
                    haystack=f"{mistake.category} {mistake.note or ''}",
                    href=f"/courses/{course.id}?tab=mistakes",
                    boost=1.1,
                )
            )

        practice_rows = db.execute(
            select(TutorPracticeMistake, TutorPracticeAttempt)
            .join(
                TutorPracticeAttempt,
                TutorPracticeAttempt.id == TutorPracticeMistake.attempt_id,
            )
            .where(TutorPracticeAttempt.course_id.in_(course_ids))
        ).all()
        for mistake, attempt in practice_rows:
            course = course_by_id[attempt.course_id]
            candidates.append(
                _Candidate(
                    kind="mistake",
                    id=mistake.id,
                    course_id=course.id,
                    course_name=course.name,
                    title=mistake.category.replace("_", " "),
                    subtitle="Practice mistake",
                    excerpt=mistake.note,
                    haystack=f"{mistake.category} {mistake.note or ''}",
                    href=f"/courses/{course.id}?tab=mistakes",
                    boost=1.1,
                )
            )

    if allow("cheat_sheet"):
        rows = db.scalars(
            select(CheatSheet).where(CheatSheet.course_id.in_(course_ids))
        ).all()
        for sheet in rows:
            course = course_by_id[sheet.course_id]
            section_text = " ".join(
                f"{section.get('topic_name', '')} "
                + " ".join(str(item.get("text", "")) for item in section.get("items", []))
                for section in sheet.sections
            )
            candidates.append(
                _Candidate(
                    kind="cheat_sheet",
                    id=sheet.id,
                    course_id=course.id,
                    course_name=course.name,
                    title=sheet.title,
                    subtitle=f"Cheat sheet · {sheet.item_count} items",
                    excerpt=section_text,
                    haystack=f"{sheet.title} {section_text}",
                    href=f"/courses/{course.id}?tab=cheats&sheet={sheet.id}",
                )
            )

    if allow("forecast"):
        rows = db.scalars(
            select(GradeForecastSnapshot).where(
                GradeForecastSnapshot.course_id.in_(course_ids)
            )
        ).all()
        for snapshot in rows:
            if not snapshot.label:
                continue
            course = course_by_id[snapshot.course_id]
            candidates.append(
                _Candidate(
                    kind="forecast",
                    id=snapshot.id,
                    course_id=course.id,
                    course_name=course.name,
                    title=snapshot.label,
                    subtitle=(
                        f"Forecast · expected {snapshot.expected_grade:.1f}/"
                        f"{snapshot.max_grade:.0f}"
                    ),
                    excerpt=None,
                    haystack=snapshot.label,
                    href=f"/courses/{course.id}?tab=forecast&snapshot={snapshot.id}",
                )
            )

    ranked: list[GlobalSearchResultRead] = []
    for candidate in candidates:
        score = _score(candidate, tokens, normalized)
        if score <= 0:
            continue
        excerpt = (
            _snippet(candidate.excerpt, tokens)
            if candidate.excerpt
            else candidate.excerpt
        )
        ranked.append(
            GlobalSearchResultRead(
                kind=candidate.kind,
                id=candidate.id,
                course_id=candidate.course_id,
                course_name=candidate.course_name,
                title=candidate.title,
                subtitle=candidate.subtitle,
                excerpt=excerpt,
                score=score,
                href=candidate.href,
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.kind, item.title.lower()))
    results = ranked[:limit]
    return GlobalSearchRead(
        query=normalized,
        result_count=len(results),
        results=results,
    )
