from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.course_intelligence import CourseTopic
from app.models.document import Document
from app.models.document_content import DocumentAnalysis, DocumentUnit
from app.models.exam_intelligence import (
    ExamAnalysis,
    ExamQuestion,
    ExamQuestionTopic,
    ExamTopicStat,
)
from app.models.grading import ExamQuestionReference

_EXAM_TYPES = {"past_exam", "past_exam_solution"}
_QUESTION_START_RE = re.compile(
    r"(?im)^\s*(?:(?:question|q)\s*(\d{1,2})|(\d{1,2})[.)])\s*[:\-]?\s*"
)
_MARK_RE = re.compile(
    r"(?i)(?:\[|\()?\s*(\d+(?:\.\d+)?)\s*(?:marks?|points?|pts?)\s*(?:\]|\))?"
)
_SOLUTION_MARKER_RE = re.compile(
    r"(?im)^\s*(?:solution|answer|soluzione|risposta)\s*(?:[:.\-]\s*)?"
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9']*")
_TASK_RE = re.compile(
    r"(?i)\b(?:calculate|compute|determine|derive|evaluate|explain|find|give|"
    r"identify|prove|show|solve|state|write|sketch|draw|compare|discuss|"
    r"estimate|classify|choose|complete|obtain|use)\b"
)
_ADMIN_RE = re.compile(
    r"(?i)\b(?:"
    r"students? (?:are|is) (?:allowed|not allowed)|"
    r"no (?:laptops?|ipads?|phones?|electronic|communication)|"
    r"electronic devices?|mobile phones?|"
    r"course textbook|loose sheets?|blank sheets?|"
    r"during the (?:written )?exam|classroom|"
    r"zero tolerance|disciplinary consequences?|"
    r"fail the exam|exam (?:is|will be) (?:stopped|terminated)|"
    r"returned at the end|internet during the exam|"
    r"communication (?:is|between students)"
    r")\b"
)
_ADMIN_HEADING_RE = re.compile(
    r"(?im)^\s*(?:general\s+)?(?:exam(?:ination)?\s+)?"
    r"(?:instructions?|rules?|regulations?|important information|allowed materials?)\s*[:\-]?"
)


class NoExamDocumentsError(RuntimeError):
    pass


class CourseTopicsRequiredError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractedQuestion:
    label: str
    source_label: str
    text: str
    marks: float | None
    reference_answer: str | None


def _split_prompt_reference(
    question_text: str,
    *,
    allow_reference: bool,
) -> tuple[str, str | None]:
    cleaned = question_text.strip()
    if not allow_reference:
        return cleaned, None

    marker = _SOLUTION_MARKER_RE.search(cleaned)
    if marker is None:
        return cleaned, None

    prompt = cleaned[: marker.start()].strip()
    reference = cleaned[marker.end() :].strip()
    if not prompt or len(reference) < 5:
        return cleaned, None
    return prompt, reference


def _is_answerable_question(question_text: str) -> bool:
    """Reject administrative/cover-page blocks that only look numbered like questions."""
    cleaned = question_text.strip()
    if not cleaned:
        return False

    admin_hits = len(_ADMIN_RE.findall(cleaned))
    has_admin_heading = _ADMIN_HEADING_RE.search(cleaned) is not None
    has_task = _TASK_RE.search(cleaned) is not None or "?" in cleaned

    if admin_hits >= 2 or (has_admin_heading and admin_hits >= 1):
        return False

    word_count = len(_WORD_RE.findall(cleaned))
    if word_count >= 120 and not has_task:
        return False

    return True


def _extract_questions(
    text: str,
    source_label: str,
    *,
    allow_reference: bool,
) -> list[ExtractedQuestion]:
    matches = list(_QUESTION_START_RE.finditer(text))
    questions: list[ExtractedQuestion] = []
    for index, match in enumerate(matches):
        number = match.group(1) or match.group(2)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_question = text[match.start() : end].strip()
        if not raw_question:
            continue
        question_text, reference_answer = _split_prompt_reference(
            raw_question,
            allow_reference=allow_reference,
        )
        if not _is_answerable_question(question_text):
            continue
        mark_match = _MARK_RE.search(question_text)
        marks = float(mark_match.group(1)) if mark_match else None
        questions.append(
            ExtractedQuestion(
                label=f"Q{number}",
                source_label=source_label,
                text=question_text,
                marks=marks,
                reference_answer=reference_answer,
            )
        )
    return questions


def _topic_relevance(question_text: str, normalized_topic: str) -> float:
    lowered = question_text.lower()
    if normalized_topic in lowered:
        return 1.0

    topic_tokens = set(_WORD_RE.findall(normalized_topic.lower()))
    question_tokens = set(_WORD_RE.findall(lowered))
    if not topic_tokens:
        return 0.0
    overlap = len(topic_tokens & question_tokens) / len(topic_tokens)
    return round(overlap, 4) if overlap >= 0.6 else 0.0


def _clear_exam_analysis(db: Session, course_id: str) -> None:
    question_ids = list(
        db.scalars(select(ExamQuestion.id).where(ExamQuestion.course_id == course_id)).all()
    )
    if question_ids:
        db.execute(
            delete(ExamQuestionReference).where(
                ExamQuestionReference.question_id.in_(question_ids)
            )
        )
        db.execute(
            delete(ExamQuestionTopic).where(ExamQuestionTopic.question_id.in_(question_ids))
        )
    db.execute(delete(ExamTopicStat).where(ExamTopicStat.course_id == course_id))
    db.execute(delete(ExamQuestion).where(ExamQuestion.course_id == course_id))
    db.execute(delete(ExamAnalysis).where(ExamAnalysis.course_id == course_id))


def analyze_exams(db: Session, course_id: str) -> ExamAnalysis:
    topics = list(
        db.scalars(
            select(CourseTopic)
            .where(CourseTopic.course_id == course_id)
            .order_by(CourseTopic.importance_score.desc())
        ).all()
    )
    if not topics:
        raise CourseTopicsRequiredError("Analyze the course before analyzing past exams")

    exam_analyses = list(
        db.execute(
            select(DocumentAnalysis, Document)
            .join(Document, Document.id == DocumentAnalysis.document_id)
            .where(
                Document.course_id == course_id,
                Document.status == "processed",
                DocumentAnalysis.document_type.in_(_EXAM_TYPES),
            )
        ).all()
    )
    if not exam_analyses:
        raise NoExamDocumentsError("Process at least one past exam before exam analysis")

    document_type_by_id = {
        document.id: analysis.document_type for analysis, document in exam_analyses
    }
    exam_document_ids = list(document_type_by_id)
    units = list(
        db.scalars(
            select(DocumentUnit)
            .where(DocumentUnit.document_id.in_(exam_document_ids))
            .order_by(DocumentUnit.document_id, DocumentUnit.unit_index)
        ).all()
    )

    _clear_exam_analysis(db, course_id)

    question_models: list[ExamQuestion] = []
    topic_question_ids: defaultdict[str, set[str]] = defaultdict(set)
    topic_marks: defaultdict[str, float] = defaultdict(float)
    question_index_by_document: defaultdict[str, int] = defaultdict(int)

    for unit in units:
        allow_reference = document_type_by_id.get(unit.document_id) == "past_exam_solution"
        extracted_questions = _extract_questions(
            unit.text,
            unit.source_label,
            allow_reference=allow_reference,
        )
        for extracted in extracted_questions:
            question_index_by_document[unit.document_id] += 1
            question = ExamQuestion(
                id=str(uuid4()),
                course_id=course_id,
                document_id=unit.document_id,
                question_index=question_index_by_document[unit.document_id],
                question_label=extracted.label,
                source_label=extracted.source_label,
                text=extracted.text,
                marks=extracted.marks,
            )
            db.add(question)
            question_models.append(question)

            if extracted.reference_answer is not None:
                db.add(
                    ExamQuestionReference(
                        id=str(uuid4()),
                        question_id=question.id,
                        source_document_id=unit.document_id,
                        source_label=unit.source_label,
                        reference_text=extracted.reference_answer,
                        extraction_method="inline_solution_marker",
                        confidence=0.95,
                    )
                )

            matches: list[tuple[CourseTopic, float]] = []
            for topic in topics:
                relevance = _topic_relevance(extracted.text, topic.normalized_name)
                if relevance > 0:
                    matches.append((topic, relevance))
            matches.sort(key=lambda item: item[1], reverse=True)
            matches = matches[:3]
            total_relevance = sum(score for _, score in matches)
            for topic, relevance in matches:
                allocated_marks = (
                    extracted.marks * relevance / total_relevance
                    if extracted.marks is not None and total_relevance > 0
                    else None
                )
                topic_question_ids[topic.id].add(question.id)
                if allocated_marks is not None:
                    topic_marks[topic.id] += allocated_marks
                db.add(
                    ExamQuestionTopic(
                        id=str(uuid4()),
                        question_id=question.id,
                        topic_id=topic.id,
                        relevance_score=round(relevance, 4),
                        allocated_marks=(
                            round(allocated_marks, 4) if allocated_marks is not None else None
                        ),
                    )
                )

    mapped_question_count = max(
        1,
        len({question_id for ids in topic_question_ids.values() for question_id in ids}),
    )
    total_allocated_marks = sum(topic_marks.values())
    stat_rows: list[tuple[CourseTopic, int, float, float, float, float]] = []
    for topic in topics:
        question_count = len(topic_question_ids[topic.id])
        question_share = question_count / mapped_question_count
        mark_share = topic_marks[topic.id] / total_allocated_marks if total_allocated_marks else 0.0
        raw_weight = (
            0.7 * mark_share + 0.3 * question_share if total_allocated_marks else question_share
        )
        stat_rows.append(
            (topic, question_count, topic_marks[topic.id], question_share, mark_share, raw_weight)
        )

    total_raw_weight = sum(row[5] for row in stat_rows) or 1.0
    for topic, question_count, known_marks, question_share, mark_share, raw_weight in stat_rows:
        db.add(
            ExamTopicStat(
                id=str(uuid4()),
                course_id=course_id,
                topic_id=topic.id,
                question_count=question_count,
                known_marks=round(known_marks, 4),
                question_share=round(question_share, 4),
                mark_share=round(mark_share, 4),
                exam_weight=round(raw_weight / total_raw_weight, 4),
            )
        )

    analysis = ExamAnalysis(
        course_id=course_id,
        exam_document_count=len(exam_document_ids),
        question_count=len(question_models),
        marked_question_count=sum(question.marks is not None for question in question_models),
        total_known_marks=round(sum(question.marks or 0.0 for question in question_models), 4),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis
