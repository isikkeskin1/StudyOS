from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from app.services.tutor_provider import (
    TutorProviderConfig,
    TutorProviderFailure,
    TutorProviderUnavailable,
)

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
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorAnswerRead:
    _course(db, course_id)
    settings = request.app.state.settings
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )
    provider_config = TutorProviderConfig(
        default_provider=settings.tutor_provider,
        openai_api_key=api_key,
        openai_model=settings.openai_tutor_model,
        openai_max_output_tokens=settings.openai_tutor_max_output_tokens,
    )
    try:
        return answer_from_course_material(
            db,
            course_id,
            payload,
            provider_config=provider_config,
        )
    except TutorProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TutorProviderFailure as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Tutor synthesis provider failed",
        ) from exc
