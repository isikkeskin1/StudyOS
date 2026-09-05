from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.tutor import (
    TutorAnswerRead,
    TutorAskRequest,
    TutorHintRead,
    TutorPracticeCreateRequest,
    TutorPracticeEvaluateRequest,
    TutorPracticeEvaluationRead,
    TutorPracticeRead,
    TutorPracticeSessionCreateRequest,
    TutorPracticeSessionRead,
    TutorSearchRead,
    TutorSearchRequest,
    TutorSolutionRead,
)
from app.services.tutor import answer_from_course_material, search_course_material
from app.services.tutor_embeddings import (
    TutorEmbeddingConfig,
    TutorEmbeddingFailure,
    TutorEmbeddingUnavailable,
)
from app.services.tutor_practice import (
    TutorPracticeUnavailable,
    create_practice_item,
    get_practice_item,
    reveal_next_hint,
    reveal_solution,
)
from app.services.tutor_practice_evaluation import (
    TutorPracticeEvaluationError,
    evaluate_practice_item,
)
from app.services.tutor_practice_sessions import (
    TutorPracticeSessionError,
    complete_practice_session,
    create_practice_session,
    get_practice_session,
    practice_session_read,
)
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


def _provider_config(request: Request) -> TutorProviderConfig:
    settings = request.app.state.settings
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )
    return TutorProviderConfig(
        default_provider=settings.tutor_provider,
        openai_api_key=api_key,
        openai_model=settings.openai_tutor_model,
        openai_max_output_tokens=settings.openai_tutor_max_output_tokens,
    )


def _embedding_config(request: Request) -> TutorEmbeddingConfig:
    settings = request.app.state.settings
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )
    return TutorEmbeddingConfig(
        provider=settings.tutor_embedding_provider,
        openai_api_key=api_key,
        openai_model=settings.openai_embedding_model,
        max_candidates=settings.tutor_embedding_max_candidates,
    )


def _raise_tutor_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (TutorProviderUnavailable, TutorEmbeddingUnavailable)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if isinstance(exc, (TutorProviderFailure, TutorEmbeddingFailure)):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Tutor model provider failed",
        ) from exc
    if isinstance(
        exc,
        (TutorPracticeUnavailable, TutorPracticeEvaluationError, TutorPracticeSessionError),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    raise exc


@router.post("/{course_id}/tutor/search", response_model=TutorSearchRead)
def tutor_search(
    course_id: str,
    payload: TutorSearchRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorSearchRead:
    _course(db, course_id)
    try:
        return search_course_material(
            db,
            course_id,
            payload,
            embedding_config=_embedding_config(request),
        )
    except (TutorEmbeddingUnavailable, TutorEmbeddingFailure) as exc:
        _raise_tutor_error(exc)


@router.post("/{course_id}/tutor/ask", response_model=TutorAnswerRead)
def tutor_ask(
    course_id: str,
    payload: TutorAskRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorAnswerRead:
    _course(db, course_id)
    try:
        return answer_from_course_material(
            db,
            course_id,
            payload,
            provider_config=_provider_config(request),
            embedding_config=_embedding_config(request),
        )
    except (
        TutorProviderUnavailable,
        TutorProviderFailure,
        TutorEmbeddingUnavailable,
        TutorEmbeddingFailure,
    ) as exc:
        _raise_tutor_error(exc)


@router.post(
    "/{course_id}/tutor/practice",
    response_model=TutorPracticeRead,
    status_code=status.HTTP_201_CREATED,
)
def tutor_create_practice(
    course_id: str,
    payload: TutorPracticeCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorPracticeRead:
    _course(db, course_id)
    try:
        return create_practice_item(
            db,
            course_id,
            payload,
            provider_config=_provider_config(request),
            embedding_config=_embedding_config(request),
        )
    except (
        TutorProviderUnavailable,
        TutorProviderFailure,
        TutorEmbeddingUnavailable,
        TutorEmbeddingFailure,
        TutorPracticeUnavailable,
    ) as exc:
        _raise_tutor_error(exc)


@router.post(
    "/{course_id}/tutor/practice-sessions",
    response_model=TutorPracticeSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def tutor_create_practice_session(
    course_id: str,
    payload: TutorPracticeSessionCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorPracticeSessionRead:
    _course(db, course_id)
    try:
        return create_practice_session(
            db,
            course_id,
            payload,
            provider_config=_provider_config(request),
            embedding_config=_embedding_config(request),
        )
    except (
        TutorProviderUnavailable,
        TutorProviderFailure,
        TutorEmbeddingUnavailable,
        TutorEmbeddingFailure,
        TutorPracticeUnavailable,
        TutorPracticeSessionError,
    ) as exc:
        _raise_tutor_error(exc)


@router.get(
    "/{course_id}/tutor/practice-sessions/{session_id}",
    response_model=TutorPracticeSessionRead,
)
def tutor_get_practice_session(
    course_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> TutorPracticeSessionRead:
    _course(db, course_id)
    session = get_practice_session(db, course_id, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practice session not found",
        )
    return practice_session_read(db, session)


@router.post(
    "/{course_id}/tutor/practice-sessions/{session_id}/complete",
    response_model=TutorPracticeSessionRead,
)
def tutor_complete_practice_session(
    course_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> TutorPracticeSessionRead:
    _course(db, course_id)
    session = get_practice_session(db, course_id, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practice session not found",
        )
    return complete_practice_session(db, session)


@router.post(
    "/{course_id}/tutor/practice/{practice_id}/hint",
    response_model=TutorHintRead,
)
def tutor_next_hint(
    course_id: str,
    practice_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> TutorHintRead:
    _course(db, course_id)
    item = get_practice_item(db, course_id, practice_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practice item not found",
        )
    try:
        return reveal_next_hint(db, item)
    except TutorPracticeUnavailable as exc:
        _raise_tutor_error(exc)


@router.post(
    "/{course_id}/tutor/practice/{practice_id}/evaluate",
    response_model=TutorPracticeEvaluationRead,
)
def tutor_evaluate_practice(
    course_id: str,
    practice_id: str,
    payload: TutorPracticeEvaluateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorPracticeEvaluationRead:
    _course(db, course_id)
    item = get_practice_item(db, course_id, practice_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practice item not found",
        )
    try:
        return evaluate_practice_item(
            db,
            item,
            payload,
            provider_config=_provider_config(request),
            embedding_config=_embedding_config(request),
        )
    except (
        TutorPracticeEvaluationError,
        TutorPracticeSessionError,
        TutorProviderUnavailable,
        TutorProviderFailure,
    ) as exc:
        _raise_tutor_error(exc)


@router.get(
    "/{course_id}/tutor/practice/{practice_id}/solution",
    response_model=TutorSolutionRead,
)
def tutor_solution(
    course_id: str,
    practice_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> TutorSolutionRead:
    _course(db, course_id)
    item = get_practice_item(db, course_id, practice_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practice item not found",
        )
    return reveal_solution(db, item)
