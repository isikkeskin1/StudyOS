from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.tutor_embedding_index import (
    TutorEmbeddingIndexRead,
    TutorEmbeddingIndexSyncRequest,
)
from app.services.tutor_embedding_index import (
    embedding_index_status,
    sync_course_embedding_index,
)
from app.services.tutor_embeddings import (
    TutorEmbeddingConfig,
    TutorEmbeddingFailure,
    TutorEmbeddingUnavailable,
    build_embedding_provider,
)

router = APIRouter(prefix="/courses", tags=["tutor"])


def _course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


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
        batch_size=settings.tutor_embedding_batch_size,
    )


def _provider_or_error(config: TutorEmbeddingConfig):
    try:
        return build_embedding_provider(config)
    except TutorEmbeddingUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get(
    "/{course_id}/tutor/embedding-index",
    response_model=TutorEmbeddingIndexRead,
)
def tutor_embedding_index_status(
    course_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorEmbeddingIndexRead:
    _course(db, course_id)
    config = _embedding_config(request)
    provider = _provider_or_error(config)
    return embedding_index_status(db, course_id, provider)


@router.post(
    "/{course_id}/tutor/embedding-index/sync",
    response_model=TutorEmbeddingIndexRead,
)
def tutor_embedding_index_sync(
    course_id: str,
    payload: TutorEmbeddingIndexSyncRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorEmbeddingIndexRead:
    _course(db, course_id)
    config = _embedding_config(request)
    provider = _provider_or_error(config)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding index sync requires a configured embedding provider",
        )
    try:
        return sync_course_embedding_index(
            db,
            course_id,
            provider,
            batch_size=payload.batch_size or config.batch_size,
            force=payload.force,
        )
    except TutorEmbeddingFailure as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Embedding provider failed while syncing the course index",
        ) from exc
