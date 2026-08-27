from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import (
    DiagnosticQuestion,
    DiagnosticResponse,
    DiagnosticSession,
    TopicMastery,
)
from app.models.exam_intelligence import ExamQuestion, ExamQuestionTopic, ExamTopicStat


class DiagnosticUnavailableError(RuntimeError):
    pass


class DiagnosticStateError(RuntimeError):
    pass


class DuplicateDiagnosticResponseError(RuntimeError):
    pass


def session_counts(db: Session, session_id: str) -> tuple[int, int]:
    selected = db.scalar(
        select(func.count(DiagnosticQuestion.id)).where(
            DiagnosticQuestion.session_id == session_id
        )
    )
    answered = db.scalar(
        select(func.count(DiagnosticResponse.id)).where(
            DiagnosticResponse.session_id == session_id
        )
    )
    return int(selected or 0), int(answered or 0)


def _finish_session(db: Session, session: DiagnosticSession) -> None:
    if session.status == "completed":
        return
    session.status = "completed"
    session.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)


def create_diagnostic_session(
    db: Session,
    course_id: str,
    question_count: int,
) -> DiagnosticSession:
    available = db.scalar(
        select(func.count(ExamQuestion.id)).where(ExamQuestion.course_id == course_id)
    )
    if not available:
        raise DiagnosticUnavailableError(
            "Analyze at least one past exam before starting a diagnostic"
        )

    session = DiagnosticSession(
        id=str(uuid4()),
        course_id=course_id,
        requested_question_count=min(question_count, int(available)),
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _question_difficulty(question: ExamQuestion) -> float:
    if question.marks is None:
        return 0.5
    return round(min(1.0, max(0.25, 0.35 + question.marks / 20.0)), 4)


def _question_mappings(
    db: Session,
    exam_question_ids: list[str],
) -> dict[str, list[ExamQuestionTopic]]:
    mappings: dict[str, list[ExamQuestionTopic]] = defaultdict(list)
    if not exam_question_ids:
        return mappings

    rows = db.scalars(
        select(ExamQuestionTopic)
        .where(ExamQuestionTopic.question_id.in_(exam_question_ids))
        .order_by(ExamQuestionTopic.relevance_score.desc())
    ).all()
    for mapping in rows:
        mappings[mapping.question_id].append(mapping)
    return mappings


def select_next_question(
    db: Session,
    session: DiagnosticSession,
) -> DiagnosticQuestion | None:
    selected_questions = list(
        db.scalars(
            select(DiagnosticQuestion)
            .where(DiagnosticQuestion.session_id == session.id)
            .order_by(DiagnosticQuestion.sequence)
        ).all()
    )
    answered_question_ids = set(
        db.scalars(
            select(DiagnosticResponse.diagnostic_question_id).where(
                DiagnosticResponse.session_id == session.id
            )
        ).all()
    )

    for question in selected_questions:
        if question.id not in answered_question_ids:
            return question

    if session.status != "active":
        return None

    if len(answered_question_ids) >= session.requested_question_count:
        _finish_session(db, session)
        return None

    selected_exam_question_ids = {question.exam_question_id for question in selected_questions}
    query = select(ExamQuestion).where(ExamQuestion.course_id == session.course_id)
    if selected_exam_question_ids:
        query = query.where(ExamQuestion.id.not_in(selected_exam_question_ids))
    exam_questions = list(db.scalars(query.order_by(ExamQuestion.question_index)).all())
    if not exam_questions:
        _finish_session(db, session)
        return None

    exam_ids = [question.id for question in exam_questions]
    mappings_by_question = _question_mappings(db, exam_ids)
    topics = {
        topic.id: topic
        for topic in db.scalars(
            select(CourseTopic).where(CourseTopic.course_id == session.course_id)
        ).all()
    }
    exam_stats = {
        stat.topic_id: stat
        for stat in db.scalars(
            select(ExamTopicStat).where(ExamTopicStat.course_id == session.course_id)
        ).all()
    }
    mastery = {
        item.topic_id: item
        for item in db.scalars(
            select(TopicMastery).where(TopicMastery.course_id == session.course_id)
        ).all()
    }
    selected_primary = Counter(question.primary_topic_id for question in selected_questions)

    best_question: ExamQuestion | None = None
    best_primary_topic: str | None = None
    best_utility = -1.0

    for exam_question in exam_questions:
        mappings = mappings_by_question.get(exam_question.id, [])
        components: list[tuple[str, float]] = []
        for mapping in mappings:
            topic = topics.get(mapping.topic_id)
            if topic is None:
                continue
            stat = exam_stats.get(topic.id)
            base_weight = stat.exam_weight if stat is not None else topic.importance_score
            mastery_item = mastery.get(topic.id)
            mastery_value = mastery_item.mastery if mastery_item is not None else 0.5
            confidence = mastery_item.confidence if mastery_item is not None else 0.0
            uncertainty = 0.55 + 0.45 * (1.0 - confidence)
            weakness = 0.90 + 0.10 * (1.0 - mastery_value)
            coverage = 1.0 / (1.0 + 0.60 * selected_primary[topic.id])
            component = (
                max(base_weight, 0.01)
                * mapping.relevance_score
                * uncertainty
                * weakness
                * coverage
            )
            components.append((topic.id, component))

        if not components:
            continue
        utility = sum(component for _, component in components)
        if utility > best_utility:
            best_utility = utility
            best_question = exam_question
            best_primary_topic = max(components, key=lambda item: item[1])[0]

    if best_question is None or best_primary_topic is None:
        _finish_session(db, session)
        return None

    diagnostic_question = DiagnosticQuestion(
        id=str(uuid4()),
        session_id=session.id,
        exam_question_id=best_question.id,
        primary_topic_id=best_primary_topic,
        sequence=len(selected_questions) + 1,
        difficulty=_question_difficulty(best_question),
    )
    db.add(diagnostic_question)
    db.commit()
    db.refresh(diagnostic_question)
    return diagnostic_question


def recompute_course_mastery(db: Session, course_id: str) -> list[TopicMastery]:
    session_ids = list(
        db.scalars(
            select(DiagnosticSession.id).where(DiagnosticSession.course_id == course_id)
        ).all()
    )
    if not session_ids:
        return []

    diagnostic_questions = list(
        db.scalars(
            select(DiagnosticQuestion).where(DiagnosticQuestion.session_id.in_(session_ids))
        ).all()
    )
    question_by_id = {question.id: question for question in diagnostic_questions}
    responses = list(
        db.scalars(
            select(DiagnosticResponse).where(DiagnosticResponse.session_id.in_(session_ids))
        ).all()
    )
    exam_question_ids = list({question.exam_question_id for question in diagnostic_questions})
    mappings_by_question = _question_mappings(db, exam_question_ids)

    evidence: dict[str, dict[str, float]] = defaultdict(
        lambda: {"weight": 0.0, "success": 0.0, "count": 0.0}
    )
    for response in responses:
        diagnostic_question = question_by_id.get(response.diagnostic_question_id)
        if diagnostic_question is None:
            continue
        mappings = mappings_by_question.get(diagnostic_question.exam_question_id, [])
        for mapping in mappings:
            weight = (
                max(0.05, mapping.relevance_score)
                * (0.8 + 0.4 * diagnostic_question.difficulty)
                * (0.75 + 0.25 * response.confidence)
            )
            row = evidence[mapping.topic_id]
            row["weight"] += weight
            row["success"] += weight * response.score
            row["count"] += 1.0

    existing = {
        item.topic_id: item
        for item in db.scalars(
            select(TopicMastery).where(TopicMastery.course_id == course_id)
        ).all()
    }
    updated: list[TopicMastery] = []
    now = datetime.now(UTC)

    for topic_id, row in evidence.items():
        weight = row["weight"]
        alpha = 2.0 + row["success"]
        beta = 2.0 + weight - row["success"]
        mastery_value = alpha / (alpha + beta)
        confidence = 1.0 - math.exp(-weight / 3.0)

        item = existing.get(topic_id)
        if item is None:
            item = TopicMastery(
                id=str(uuid4()),
                course_id=course_id,
                topic_id=topic_id,
                mastery=mastery_value,
                confidence=confidence,
                evidence_weight=weight,
                response_count=int(row["count"]),
                updated_at=now,
            )
            db.add(item)
        else:
            item.mastery = mastery_value
            item.confidence = confidence
            item.evidence_weight = weight
            item.response_count = int(row["count"])
            item.updated_at = now
        updated.append(item)

    db.commit()
    for item in updated:
        db.refresh(item)
    return updated


def record_response(
    db: Session,
    session: DiagnosticSession,
    diagnostic_question_id: str,
    score: float,
    confidence: float,
    grading_source: str,
    duration_seconds: int | None,
) -> tuple[DiagnosticResponse, list[TopicMastery]]:
    if session.status != "active":
        raise DiagnosticStateError("Diagnostic session is already completed")

    diagnostic_question = db.get(DiagnosticQuestion, diagnostic_question_id)
    if diagnostic_question is None or diagnostic_question.session_id != session.id:
        raise DiagnosticStateError("Diagnostic question does not belong to this session")

    existing = db.scalar(
        select(DiagnosticResponse).where(
            DiagnosticResponse.diagnostic_question_id == diagnostic_question_id
        )
    )
    if existing is not None:
        raise DuplicateDiagnosticResponseError("This diagnostic question is already scored")

    response = DiagnosticResponse(
        id=str(uuid4()),
        session_id=session.id,
        diagnostic_question_id=diagnostic_question_id,
        score=score,
        confidence=confidence,
        grading_source=grading_source,
        duration_seconds=duration_seconds,
    )
    db.add(response)
    db.commit()
    db.refresh(response)

    mastery = recompute_course_mastery(db, session.course_id)
    _, answered = session_counts(db, session.id)
    if answered >= session.requested_question_count:
        _finish_session(db, session)

    return response, mastery


def complete_session(db: Session, session: DiagnosticSession) -> DiagnosticSession:
    _finish_session(db, session)
    return session


def list_course_mastery(db: Session, course_id: str) -> list[TopicMastery]:
    return list(
        db.scalars(
            select(TopicMastery)
            .where(TopicMastery.course_id == course_id)
            .order_by(TopicMastery.confidence.desc(), TopicMastery.mastery)
        ).all()
    )
