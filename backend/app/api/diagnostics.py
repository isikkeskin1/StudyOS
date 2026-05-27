from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import DiagnosticQuestion, DiagnosticSession
from app.models.exam_intelligence import ExamAnalysis, ExamQuestion, ExamQuestionTopic
from app.models.grading import ExamQuestionReference
from app.schemas.diagnostics import (
    DiagnosticAnswerRead,
    DiagnosticAutoGradeCreate,
    DiagnosticGradingRead,
    DiagnosticMistakeRead,
    DiagnosticNextRead,
    DiagnosticQuestionRead,
    DiagnosticQuestionTopicRead,
    DiagnosticResponseCreate,
    DiagnosticResponseRead,
    DiagnosticSessionCreate,
    DiagnosticSessionRead,
    TopicMasteryRead,
)
from app.services.diagnostics import (
    DiagnosticStateError,
    DiagnosticUnavailableError,
    DuplicateDiagnosticResponseError,
    complete_session,
    create_diagnostic_session,
    list_course_mastery,
    record_response,
    select_next_question,
    session_counts,
)
from app.services.exam_analysis import (
    CourseTopicsRequiredError,
    NoExamDocumentsError,
    analyze_exams,
)
from app.services.grading import (
    ReferenceSolutionUnavailableError,
    get_grade_artifact,
    grade_diagnostic_response,
)
from app.services.mistake_intelligence import (
    MistakeInput,
    get_response_answer,
    get_response_mistakes,
)

router = APIRouter(prefix="/courses", tags=["diagnostics", "mastery"])


def _get_course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def _get_session(db: Session, course_id: str, session_id: str) -> DiagnosticSession:
    _get_course(db, course_id)
    session = db.get(DiagnosticSession, session_id)
    if session is None or session.course_id != course_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic session not found",
        )
    return session


def _read_session(db: Session, session: DiagnosticSession) -> DiagnosticSessionRead:
    selected, answered = session_counts(db, session.id)
    return DiagnosticSessionRead(
        id=session.id,
        course_id=session.course_id,
        status=session.status,
        requested_question_count=session.requested_question_count,
        selected_question_count=selected,
        answered_question_count=answered,
        created_at=session.created_at,
        completed_at=session.completed_at,
    )


def _read_question(db: Session, question: DiagnosticQuestion) -> DiagnosticQuestionRead:
    exam_question = db.get(ExamQuestion, question.exam_question_id)
    if exam_question is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source exam question is no longer available",
        )

    mappings = list(
        db.scalars(
            select(ExamQuestionTopic)
            .where(ExamQuestionTopic.question_id == exam_question.id)
            .order_by(ExamQuestionTopic.relevance_score.desc())
        ).all()
    )
    topic_ids = {mapping.topic_id for mapping in mappings}
    topic_ids.add(question.primary_topic_id)
    topics = {
        topic.id: topic.name
        for topic in db.scalars(select(CourseTopic).where(CourseTopic.id.in_(topic_ids))).all()
    }
    automatic_grading_available = (
        db.scalar(
            select(ExamQuestionReference.id).where(
                ExamQuestionReference.question_id == exam_question.id
            )
        )
        is not None
    )

    return DiagnosticQuestionRead(
        id=question.id,
        exam_question_id=exam_question.id,
        sequence=question.sequence,
        question_label=exam_question.question_label,
        source_label=exam_question.source_label,
        text=exam_question.text,
        marks=exam_question.marks,
        difficulty=question.difficulty,
        primary_topic_id=question.primary_topic_id,
        primary_topic_name=topics.get(question.primary_topic_id, "Unknown topic"),
        automatic_grading_available=automatic_grading_available,
        topics=[
            DiagnosticQuestionTopicRead(
                topic_id=mapping.topic_id,
                topic_name=topics.get(mapping.topic_id, "Unknown topic"),
                relevance_score=mapping.relevance_score,
            )
            for mapping in mappings
        ],
    )


def _read_mastery(db: Session, course_id: str) -> list[TopicMasteryRead]:
    rows = list_course_mastery(db, course_id)
    topic_names = {
        topic.id: topic.name
        for topic in db.scalars(
            select(CourseTopic).where(CourseTopic.course_id == course_id)
        ).all()
    }
    return [
        TopicMasteryRead(
            topic_id=item.topic_id,
            topic_name=topic_names.get(item.topic_id, "Unknown topic"),
            mastery=round(item.mastery, 4),
            confidence=round(item.confidence, 4),
            evidence_weight=round(item.evidence_weight, 4),
            response_count=item.response_count,
            updated_at=item.updated_at,
        )
        for item in rows
        if item.topic_id in topic_names
    ]


def _read_answer(
    db: Session,
    response_id: str,
) -> tuple[
    DiagnosticAnswerRead | None,
    list[DiagnosticMistakeRead],
    DiagnosticGradingRead | None,
]:
    artifact = get_response_answer(db, response_id)
    answer = (
        DiagnosticAnswerRead(
            student_answer=artifact.student_answer,
            reference_answer=artifact.reference_answer,
            feedback=artifact.feedback,
        )
        if artifact is not None
        else None
    )
    mistakes = [
        DiagnosticMistakeRead(
            category=item.category,
            severity=item.severity,
            source=item.source,
            note=item.note,
        )
        for item in get_response_mistakes(db, response_id)
    ]
    grade_artifact = get_grade_artifact(db, response_id)
    grading = (
        DiagnosticGradingRead(
            grader_name=grade_artifact.grader_name,
            grader_confidence=grade_artifact.grader_confidence,
            evidence_coverage=grade_artifact.evidence_coverage,
            reference_source_label=grade_artifact.reference_source_label,
            reference_extraction_method=grade_artifact.reference_extraction_method,
        )
        if grade_artifact is not None
        else None
    )
    return answer, mistakes, grading


def _response_read(db: Session, course_id: str, session: DiagnosticSession, response):
    answer, mistakes, grading = _read_answer(db, response.id)
    return DiagnosticResponseRead(
        id=response.id,
        diagnostic_question_id=response.diagnostic_question_id,
        score=response.score,
        confidence=response.confidence,
        grading_source=response.grading_source,
        duration_seconds=response.duration_seconds,
        created_at=response.created_at,
        answer=answer,
        mistakes=mistakes,
        grading=grading,
        session=_read_session(db, session),
        mastery=_read_mastery(db, course_id),
    )


@router.post(
    "/{course_id}/diagnostics",
    response_model=DiagnosticSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def start_diagnostic(
    course_id: str,
    payload: DiagnosticSessionCreate,
    db: Annotated[Session, Depends(get_db)],
) -> DiagnosticSessionRead:
    _get_course(db, course_id)

    if db.get(ExamAnalysis, course_id) is None:
        try:
            analyze_exams(db, course_id)
        except (CourseTopicsRequiredError, NoExamDocumentsError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    try:
        session = create_diagnostic_session(db, course_id, payload.question_count)
    except DiagnosticUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return _read_session(db, session)


@router.get(
    "/{course_id}/diagnostics/{session_id}",
    response_model=DiagnosticSessionRead,
)
def get_diagnostic(
    course_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> DiagnosticSessionRead:
    session = _get_session(db, course_id, session_id)
    return _read_session(db, session)


@router.get(
    "/{course_id}/diagnostics/{session_id}/next",
    response_model=DiagnosticNextRead,
)
def get_next_diagnostic_question(
    course_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> DiagnosticNextRead:
    session = _get_session(db, course_id, session_id)
    question = select_next_question(db, session)
    return DiagnosticNextRead(
        session=_read_session(db, session),
        question=_read_question(db, question) if question is not None else None,
    )


@router.post(
    "/{course_id}/diagnostics/{session_id}/responses",
    response_model=DiagnosticResponseRead,
)
def submit_diagnostic_response(
    course_id: str,
    session_id: str,
    payload: DiagnosticResponseCreate,
    db: Annotated[Session, Depends(get_db)],
) -> DiagnosticResponseRead:
    session = _get_session(db, course_id, session_id)
    try:
        response, _ = record_response(
            db,
            session,
            payload.diagnostic_question_id,
            payload.score,
            payload.confidence,
            payload.grading_source,
            payload.duration_seconds,
            student_answer=payload.student_answer,
            reference_answer=payload.reference_answer,
            feedback=payload.feedback,
            mistakes=[
                MistakeInput(
                    category=item.category,
                    severity=item.severity,
                    source=item.source,
                    note=item.note,
                )
                for item in payload.mistakes
            ],
        )
    except DuplicateDiagnosticResponseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DiagnosticStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return _response_read(db, course_id, session, response)


@router.post(
    "/{course_id}/diagnostics/{session_id}/grade",
    response_model=DiagnosticResponseRead,
)
def automatically_grade_diagnostic_response(
    course_id: str,
    session_id: str,
    payload: DiagnosticAutoGradeCreate,
    db: Annotated[Session, Depends(get_db)],
) -> DiagnosticResponseRead:
    session = _get_session(db, course_id, session_id)
    try:
        response = grade_diagnostic_response(
            db,
            session,
            payload.diagnostic_question_id,
            payload.student_answer,
            confidence=payload.confidence,
            duration_seconds=payload.duration_seconds,
        )
    except ReferenceSolutionUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DuplicateDiagnosticResponseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DiagnosticStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _response_read(db, course_id, session, response)


@router.post(
    "/{course_id}/diagnostics/{session_id}/complete",
    response_model=DiagnosticSessionRead,
)
def finish_diagnostic(
    course_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> DiagnosticSessionRead:
    session = _get_session(db, course_id, session_id)
    complete_session(db, session)
    return _read_session(db, session)


@router.get("/{course_id}/mastery", response_model=list[TopicMasteryRead])
def get_course_mastery(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[TopicMasteryRead]:
    _get_course(db, course_id)
    return _read_mastery(db, course_id)
