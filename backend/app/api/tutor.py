from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.tutor import (
    TutorAnswerRead,
    TutorAskRequest,
    TutorSearchRead,
    TutorSearchRequest,
)
from app.services.tutor import answer_from_course_material, search_course_material

router = APIRouter(prefix="/courses", tags=["tutor"])


def _course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.post("/{course_id}/tutor/search", response_model=TutorSearchRead)
def tutor_search(
    course_id: str,
    payload: TutorSearchRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TutorSearchRead:
    _course(db, course_id)
    return search_course_material(db, course_id, payload)


@router.post("/{course_id}/tutor/ask", response_model=TutorAnswerRead)
def tutor_ask(
    course_id: str,
    payload: TutorAskRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TutorAnswerRead:
    _course(db, course_id)
    return answer_from_course_material(db, course_id, payload)
