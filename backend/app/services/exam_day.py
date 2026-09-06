from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course_intelligence import CourseTopic
from app.models.exam_day import ExamDayAnswer, ExamDayQuestion, ExamDaySession
from app.models.exam_intelligence import ExamAnalysis, ExamQuestion, ExamQuestionTopic
from app.models.grading import ExamQuestionReference
from app.schemas.exam_day import (
    ExamDayAnswerUpdate,
    ExamDayQuestionRead,
    ExamDayResultRead,
    ExamDaySessionRead,
    ExamDayTopicBreakdownRead,
)
from app.services.diagnostics import recompute_course_mastery
from app.services.grading import grade_against_reference


class ExamDayUnavailable(RuntimeError):
    pass


class ExamDayStateError(RuntimeError):
    pass


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _expires_at(session: ExamDaySession) -> datetime:
    return _as_utc(session.started_at) + timedelta(minutes=session.duration_minutes)


def _expire_if_needed(db: Session, session: ExamDaySession) -> None:
    if session.status == "active" and datetime.now(UTC) >= _expires_at(session):
        session.status = "expired"
        session.submitted_at = datetime.now(UTC)
        db.commit()
        db.refresh(session)


def create_exam_day(
    db: Session,
    course_id: str,
    *,
    duration_minutes: int,
    question_count: int,
) -> ExamDaySession:
    analysis = db.get(ExamAnalysis, course_id)
    if analysis is None:
        raise ExamDayUnavailable("Analyze past exams before starting exam-day mode")

    questions = list(
        db.scalars(
            select(ExamQuestion)
            .where(ExamQuestion.course_id == course_id)
            .order_by(ExamQuestion.document_id, ExamQuestion.question_index)
        ).all()
    )
    if not questions:
        raise ExamDayUnavailable("No analyzed past-exam questions are available")

    selected = questions[: min(question_count, len(questions))]
    session = ExamDaySession(
        course_id=course_id,
        duration_minutes=duration_minutes,
        question_count=len(selected),
        total_known_marks=round(sum(item.marks or 0 for item in selected), 4),
    )
    db.add(session)
    db.flush()

    for sequence, question in enumerate(selected, start=1):
        primary_topic_id = db.scalar(
            select(ExamQuestionTopic.topic_id)
            .where(ExamQuestionTopic.question_id == question.id)
            .order_by(ExamQuestionTopic.relevance_score.desc())
        )
        automatic = (
            db.scalar(
                select(ExamQuestionReference.id).where(
                    ExamQuestionReference.question_id == question.id
                )
            )
            is not None
        )
        exam_day_question = ExamDayQuestion(
            session_id=session.id,
            exam_question_id=question.id,
            sequence=sequence,
            question_label=question.question_label,
            source_label=question.source_label,
            text=question.text,
            marks=question.marks,
            primary_topic_id=primary_topic_id,
            automatic_grading_available=automatic,
        )
        db.add(exam_day_question)
        db.flush()
        db.add(
            ExamDayAnswer(
                session_id=session.id,
                exam_day_question_id=exam_day_question.id,
            )
        )

    db.commit()
    db.refresh(session)
    return session


def _read_question(
    question: ExamDayQuestion,
    answer: ExamDayAnswer,
    topic_names: dict[str, str],
) -> ExamDayQuestionRead:
    return ExamDayQuestionRead(
        id=question.id,
        sequence=question.sequence,
        question_label=question.question_label,
        source_label=question.source_label,
        text=question.text,
        marks=question.marks,
        topic_name=(
            topic_names.get(question.primary_topic_id)
            if question.primary_topic_id
            else None
        ),
        automatic_grading_available=question.automatic_grading_available,
        answer_text=answer.answer_text,
        flagged=answer.flagged,
        self_score=answer.self_score,
        confidence=answer.confidence,
        score=answer.score,
        grading_source=answer.grading_source,
        feedback=answer.feedback,
    )


def read_exam_day(db: Session, session: ExamDaySession) -> ExamDaySessionRead:
    _expire_if_needed(db, session)
    rows = db.execute(
        select(ExamDayQuestion, ExamDayAnswer)
        .join(ExamDayAnswer, ExamDayAnswer.exam_day_question_id == ExamDayQuestion.id)
        .where(ExamDayQuestion.session_id == session.id)
        .order_by(ExamDayQuestion.sequence)
    ).all()
    topic_ids = {q.primary_topic_id for q, _ in rows if q.primary_topic_id}
    topic_names = {
        item.id: item.name
        for item in db.scalars(select(CourseTopic).where(CourseTopic.id.in_(topic_ids))).all()
    } if topic_ids else {}

    questions = [_read_question(q, a, topic_names) for q, a in rows]
    remaining = max(0, int((_expires_at(session) - datetime.now(UTC)).total_seconds()))
    return ExamDaySessionRead(
        id=session.id,
        course_id=session.course_id,
        status=session.status,
        duration_minutes=session.duration_minutes,
        question_count=session.question_count,
        total_known_marks=session.total_known_marks,
        answered_count=sum(bool(item.answer_text.strip()) for item in questions),
        flagged_count=sum(item.flagged for item in questions),
        started_at=session.started_at,
        submitted_at=session.submitted_at,
        expires_at=_expires_at(session),
        remaining_seconds=remaining,
        questions=questions,
    )


def update_exam_day_answer(
    db: Session,
    session: ExamDaySession,
    question_id: str,
    payload: ExamDayAnswerUpdate,
) -> ExamDaySessionRead:
    _expire_if_needed(db, session)
    if session.status != "active":
        raise ExamDayStateError("Exam-day session is no longer active")

    question = db.get(ExamDayQuestion, question_id)
    if question is None or question.session_id != session.id:
        raise ExamDayStateError("Exam question does not belong to this session")
    answer = db.scalar(
        select(ExamDayAnswer).where(ExamDayAnswer.exam_day_question_id == question.id)
    )
    if answer is None:
        raise ExamDayStateError("Exam answer record is missing")

    answer.answer_text = payload.answer_text
    answer.flagged = payload.flagged
    answer.self_score = payload.self_score
    answer.confidence = payload.confidence
    answer.updated_at = datetime.now(UTC)
    db.commit()
    return read_exam_day(db, session)


def submit_exam_day(db: Session, session: ExamDaySession) -> ExamDayResultRead:
    _expire_if_needed(db, session)
    if session.status == "submitted":
        return read_exam_day_result(db, session)

    rows = db.execute(
        select(ExamDayQuestion, ExamDayAnswer)
        .join(ExamDayAnswer, ExamDayAnswer.exam_day_question_id == ExamDayQuestion.id)
        .where(ExamDayQuestion.session_id == session.id)
        .order_by(ExamDayQuestion.sequence)
    ).all()

    for question, answer in rows:
        if not answer.answer_text.strip():
            answer.score = 0.0
            answer.grading_source = "blank"
            answer.feedback = "No answer submitted."
            continue

        reference = db.scalar(
            select(ExamQuestionReference).where(
                ExamQuestionReference.question_id == question.exam_question_id
            )
        )
        source_question = db.get(ExamQuestion, question.exam_question_id)
        if reference is not None and source_question is not None:
            graded = grade_against_reference(
                source_question.text,
                reference.reference_text,
                answer.answer_text,
                reference_confidence=reference.confidence,
            )
            answer.score = graded.score
            answer.grading_source = "automatic"
            answer.feedback = graded.feedback
        else:
            answer.score = answer.self_score if answer.self_score is not None else 0.0
            answer.grading_source = "self"
            answer.feedback = "Self-scored because no extracted reference solution was available."

    session.status = "submitted"
    session.submitted_at = datetime.now(UTC)
    db.commit()
    recompute_course_mastery(db, session.course_id)
    return read_exam_day_result(db, session)


def read_exam_day_result(db: Session, session: ExamDaySession) -> ExamDayResultRead:
    snapshot = read_exam_day(db, session)
    rows = db.execute(
        select(ExamDayQuestion, ExamDayAnswer)
        .join(ExamDayAnswer, ExamDayAnswer.exam_day_question_id == ExamDayQuestion.id)
        .where(ExamDayQuestion.session_id == session.id)
        .order_by(ExamDayQuestion.sequence)
    ).all()
    topic_ids = {q.primary_topic_id for q, _ in rows if q.primary_topic_id}
    topic_names = {
        item.id: item.name
        for item in db.scalars(select(CourseTopic).where(CourseTopic.id.in_(topic_ids))).all()
    } if topic_ids else {}

    scored = [a.score for _, a in rows if a.score is not None]
    topic_scores: dict[str | None, list[float]] = defaultdict(list)
    earned_known_marks = 0.0
    for question, answer in rows:
        score = answer.score if answer.score is not None else 0.0
        topic_scores[question.primary_topic_id].append(score)
        if question.marks is not None:
            earned_known_marks += question.marks * score

    breakdown = [
        ExamDayTopicBreakdownRead(
            topic_id=topic_id,
            topic_name=topic_names.get(topic_id, "Unmapped") if topic_id else "Unmapped",
            question_count=len(scores),
            average_score=round(sum(scores) / len(scores), 4),
        )
        for topic_id, scores in sorted(
            topic_scores.items(),
            key=lambda item: sum(item[1]) / len(item[1]),
        )
    ]
    return ExamDayResultRead(
        session_id=session.id,
        status=session.status,
        answered_count=snapshot.answered_count,
        question_count=session.question_count,
        average_score=round(sum(scored) / len(scored), 4) if scored else None,
        earned_known_marks=round(earned_known_marks, 4),
        total_known_marks=session.total_known_marks,
        automatic_grade_count=sum(a.grading_source == "automatic" for _, a in rows),
        self_grade_count=sum(a.grading_source == "self" for _, a in rows),
        topic_breakdown=breakdown,
        questions=snapshot.questions,
    )
