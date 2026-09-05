from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.tutor_remediation import (
    TutorPracticeTeachingHintRead,
    TutorPracticeTeachingRead,
)
from app.services.tutor_practice import TutorPracticeUnavailable
from app.services.tutor_practice_sessions import TutorPracticeSessionError
from app.services.tutor_remediation import (
    TutorPracticeTeachingError,
    current_teaching_plan,
    reveal_teaching_hint,
)

router = APIRouter(prefix="/courses", tags=["tutor"])


def _course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def _raise_teaching_error(exc: Exception) -> None:
    if isinstance(
        exc,
        (TutorPracticeTeachingError, TutorPracticeSessionError, TutorPracticeUnavailable),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    raise exc


@router.get(
    "/{course_id}/tutor/practice-sessions/{session_id}/teaching",
    response_model=TutorPracticeTeachingRead,
)
def tutor_current_teaching_plan(
    course_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> TutorPracticeTeachingRead:
    _course(db, course_id)
    try:
        return current_teaching_plan(db, course_id, session_id)
    except (TutorPracticeTeachingError, TutorPracticeSessionError) as exc:
        _raise_teaching_error(exc)


@router.post(
    "/{course_id}/tutor/practice-sessions/{session_id}/practice/{practice_id}/hint",
    response_model=TutorPracticeTeachingHintRead,
)
def tutor_session_teaching_hint(
    course_id: str,
    session_id: str,
    practice_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> TutorPracticeTeachingHintRead:
    _course(db, course_id)
    try:
        return reveal_teaching_hint(db, course_id, session_id, practice_id)
    except (
        TutorPracticeTeachingError,
        TutorPracticeSessionError,
        TutorPracticeUnavailable,
    ) as exc:
        _raise_teaching_error(exc)
