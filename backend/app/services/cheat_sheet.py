from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cheat_sheet import CheatSheet
from app.models.course import Course
from app.models.course_intelligence import CourseAnalysis, CourseTopic, TopicEvidence
from app.models.diagnostics import TopicMastery
from app.models.document import Document
from app.models.exam_intelligence import ExamTopicStat
from app.schemas.cheat_sheet import (
    CheatSheetCitationRead,
    CheatSheetGenerateRequest,
    CheatSheetItemRead,
    CheatSheetMistakeWarningRead,
    CheatSheetRead,
    CheatSheetSectionRead,
    CheatSheetSourceRead,
)
from app.services.mistake_intelligence import topic_mistake_signals


class CheatSheetUnavailable(RuntimeError):
    pass


_FORMULA_RE = re.compile(
    r"(?:[A-Za-zΑ-Ωα-ω]\s*=\s*[^.;,\n]{1,120}|"
    r"\b(?:formula|equation|equals|proportional)\b|"
    r"[∑√≈≤≥Δλμσπ∞])",
    re.IGNORECASE,
)
_METHOD_RE = re.compile(
    r"\b(?:first|then|next|finally|step|method|procedure|calculate|compute|"
    r"solve|determine|derive|substitute|apply|use)\b",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


def _compact(text: str, *, limit: int = 520) -> str:
    value = _WHITESPACE_RE.sub(" ", text).strip()
    if len(value) <= limit:
        return value
    shortened = value[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{shortened}…"


def _normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _kind(text: str) -> str:
    if _FORMULA_RE.search(text):
        return "formula"
    if _METHOD_RE.search(text):
        return "method"
    return "key_point"


def _priority(
    topic: CourseTopic,
    *,
    exam_weight: float,
    mastery: float | None,
    mistake_burden: float,
) -> float:
    mastery_gap = 0.5 if mastery is None else max(0.0, min(1.0, 1.0 - mastery))
    score = (
        0.45 * max(0.0, min(1.0, topic.importance_score))
        + 0.30 * max(0.0, min(1.0, exam_weight))
        + 0.15 * mastery_gap
        + 0.10 * max(0.0, min(1.0, mistake_burden))
    )
    return round(score, 4)


def read_cheat_sheet(row: CheatSheet) -> CheatSheetRead:
    return CheatSheetRead(
        id=row.id,
        course_id=row.course_id,
        title=row.title,
        topic_count=row.topic_count,
        item_count=row.item_count,
        source_count=row.source_count,
        generation_config=row.generation_config,
        sections=[CheatSheetSectionRead.model_validate(item) for item in row.sections],
        source_manifest=[CheatSheetSourceRead.model_validate(item) for item in row.source_manifest],
        generated_at=row.generated_at,
    )


def generate_cheat_sheet(
    db: Session,
    course: Course,
    payload: CheatSheetGenerateRequest,
) -> CheatSheet:
    if db.get(CourseAnalysis, course.id) is None:
        raise CheatSheetUnavailable("Course has not been analyzed")

    topics = list(
        db.scalars(
            select(CourseTopic)
            .where(CourseTopic.course_id == course.id)
            .order_by(CourseTopic.importance_score.desc(), CourseTopic.name)
        ).all()
    )
    if not topics:
        raise CheatSheetUnavailable("Course analysis has no topics")

    topic_ids = [topic.id for topic in topics]
    evidence_by_topic: dict[str, list[TopicEvidence]] = defaultdict(list)
    for evidence in db.scalars(
        select(TopicEvidence)
        .where(TopicEvidence.topic_id.in_(topic_ids))
        .order_by(TopicEvidence.evidence_score.desc())
    ).all():
        evidence_by_topic[evidence.topic_id].append(evidence)

    evidence_rows = [item for rows in evidence_by_topic.values() for item in rows]
    if not evidence_rows:
        raise CheatSheetUnavailable("Course analysis has no source evidence")

    document_ids = list({item.document_id for item in evidence_rows})
    documents = {
        document.id: document
        for document in db.scalars(select(Document).where(Document.id.in_(document_ids))).all()
    }

    exam_stats = {
        row.topic_id: row
        for row in db.scalars(
            select(ExamTopicStat).where(ExamTopicStat.course_id == course.id)
        ).all()
    }
    mastery = {
        row.topic_id: row.mastery
        for row in db.scalars(
            select(TopicMastery).where(TopicMastery.course_id == course.id)
        ).all()
    }
    mistake_signals = topic_mistake_signals(db, course.id) if payload.include_mistakes else {}

    ranked: list[tuple[float, CourseTopic, float, float | None, float, list[str]]] = []
    for topic in topics:
        exam_weight = exam_stats.get(topic.id).exam_weight if topic.id in exam_stats else 0.0
        topic_mastery = mastery.get(topic.id)
        mistake_burden, categories = mistake_signals.get(topic.id, (0.0, []))
        ranked.append(
            (
                _priority(
                    topic,
                    exam_weight=exam_weight,
                    mastery=topic_mastery,
                    mistake_burden=mistake_burden,
                ),
                topic,
                exam_weight,
                topic_mastery,
                mistake_burden,
                categories,
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1].importance_score, item[1].name), reverse=True)

    sections: list[dict] = []
    manifest_labels: dict[str, set[str]] = defaultdict(set)
    item_count = 0

    for priority_score, topic, exam_weight, topic_mastery, mistake_burden, categories in ranked:
        candidates: list[tuple[float, TopicEvidence, str, str]] = []
        seen: set[str] = set()
        for evidence in evidence_by_topic.get(topic.id, []):
            text = _compact(evidence.snippet)
            normalized = _normalized(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            kind = _kind(text)
            kind_boost = {"formula": 0.10, "method": 0.06, "key_point": 0.0}[kind]
            candidates.append((evidence.evidence_score + kind_boost, evidence, kind, text))

        candidates.sort(key=lambda item: item[0], reverse=True)
        items: list[CheatSheetItemRead] = []
        for _, evidence, kind, text in candidates[: payload.max_items_per_topic]:
            document = documents.get(evidence.document_id)
            if document is None:
                continue
            citation = CheatSheetCitationRead(
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
                source_label=evidence.source_label,
                filename=document.original_filename,
                quote=text,
            )
            items.append(
                CheatSheetItemRead(
                    kind=kind,
                    text=text,
                    confidence=round(max(0.0, min(1.0, evidence.evidence_score)), 4),
                    citations=[citation],
                )
            )
            manifest_labels[document.id].add(evidence.source_label)

        if not items:
            continue

        warnings = [
            CheatSheetMistakeWarningRead(
                category=category,
                mistake_burden=round(mistake_burden, 4),
            )
            for category in categories
        ]
        section = CheatSheetSectionRead(
            topic_id=topic.id,
            topic_name=topic.name,
            priority_score=priority_score,
            importance_score=round(topic.importance_score, 4),
            exam_weight=round(exam_weight, 4),
            mastery=round(topic_mastery, 4) if topic_mastery is not None else None,
            mistake_burden=round(mistake_burden, 4),
            items=items,
            mistake_warnings=warnings,
        )
        sections.append(section.model_dump())
        item_count += len(items) + len(warnings)
        if len(sections) >= payload.max_topics:
            break

    if not sections:
        raise CheatSheetUnavailable("No source-grounded cheat-sheet items could be generated")

    source_manifest = [
        CheatSheetSourceRead(
            document_id=document_id,
            filename=documents[document_id].original_filename,
            source_labels=sorted(labels),
        ).model_dump()
        for document_id, labels in sorted(
            manifest_labels.items(),
            key=lambda item: documents[item[0]].original_filename.lower(),
        )
    ]

    row = CheatSheet(
        course_id=course.id,
        title=payload.title or f"{course.name} Exam Cheat Sheet",
        topic_count=len(sections),
        item_count=item_count,
        source_count=len(source_manifest),
        generation_config=payload.model_dump(),
        sections=sections,
        source_manifest=source_manifest,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
