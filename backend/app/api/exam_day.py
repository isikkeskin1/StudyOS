from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.models.exam_day import ExamDaySession
from app.schemas.exam_day import (
    ExamDayAnswerUpdate,
    ExamDayCreateRequest,
    ExamDayResultRead,
    ExamDaySessionRead,
)
from app.services.exam_analysis import (
    CourseTopicsRequiredError,
    NoExamDocumentsError,
    analyze_exams,
)
from app.services.exam_day import (
    ExamDayStateError,
    ExamDayUnavailable,
    create_exam_day,
    read_exam_day,
    read_exam_day_result,
    submit_exam_day,
    update_exam_day_answer,
)

router = APIRouter(prefix="/courses/{course_id}/exam-day", tags=["exam day"])


def _course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def _session(db: Session, course_id: str, session_id: str) -> ExamDaySession:
    _course(db, course_id)
    session = db.get(ExamDaySession, session_id)
    if session is None or session.course_id != course_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam-day session not found",
        )
    return session


def _conflict(exc: RuntimeError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("", response_model=ExamDaySessionRead, status_code=status.HTTP_201_CREATED)
def start_exam_day(
    course_id: str,
    payload: ExamDayCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ExamDaySessionRead:
    _course(db, course_id)
    try:
        analyze_exams(db, course_id)
    except (CourseTopicsRequiredError, NoExamDocumentsError) as exc:
        raise _conflict(exc) from exc

    try:
        session = create_exam_day(
            db,
            course_id,
            duration_minutes=payload.duration_minutes,
            question_count=payload.question_count,
        )
        return read_exam_day(db, session)
    except ExamDayUnavailable as exc:
        raise _conflict(exc) from exc


@router.get("", response_model=list[ExamDaySessionRead])
def list_exam_days(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[ExamDaySessionRead]:
    _course(db, course_id)
    sessions = db.scalars(
        select(ExamDaySession)
        .where(ExamDaySession.course_id == course_id)
        .order_by(ExamDaySession.started_at.desc())
    ).all()
    return [read_exam_day(db, session) for session in sessions]


@router.get("/{session_id}", response_model=ExamDaySessionRead)
def get_exam_day(
    course_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ExamDaySessionRead:
    return read_exam_day(db, _session(db, course_id, session_id))


@router.put("/{session_id}/questions/{question_id}", response_model=ExamDaySessionRead)
def save_exam_day_answer(
    course_id: str,
    session_id: str,
    question_id: str,
    payload: ExamDayAnswerUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> ExamDaySessionRead:
    session = _session(db, course_id, session_id)
    try:
        return update_exam_day_answer(db, session, question_id, payload)
    except ExamDayStateError as exc:
        raise _conflict(exc) from exc


@router.post("/{session_id}/submit", response_model=ExamDayResultRead)
def submit_exam_day_session(
    course_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ExamDayResultRead:
    session = _session(db, course_id, session_id)
    try:
        return submit_exam_day(db, session)
    except ExamDayStateError as exc:
        raise _conflict(exc) from exc


@router.get("/{session_id}/result", response_model=ExamDayResultRead)
def get_exam_day_result(
    course_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ExamDayResultRead:
    session = _session(db, course_id, session_id)
    if session.status == "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exam-day session has not been submitted",
        )
    return read_exam_day_result(db, session)
