from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.tutor_benchmark import (
    TutorRetrievalBenchmarkRead,
    TutorRetrievalBenchmarkRequest,
)
from app.services.tutor_benchmark import TutorBenchmarkError, run_retrieval_benchmark
from app.services.tutor_embeddings import (
    TutorEmbeddingConfig,
    TutorEmbeddingFailure,
    TutorEmbeddingUnavailable,
)

router = APIRouter(prefix="/courses", tags=["tutor"])


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


@router.post(
    "/{course_id}/tutor/retrieval-benchmark",
    response_model=TutorRetrievalBenchmarkRead,
)
def tutor_retrieval_benchmark(
    course_id: str,
    payload: TutorRetrievalBenchmarkRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorRetrievalBenchmarkRead:
    if db.get(Course, course_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    try:
        return run_retrieval_benchmark(
            db,
            course_id,
            payload,
            embedding_config=_embedding_config(request),
        )
    except TutorBenchmarkError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TutorEmbeddingUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TutorEmbeddingFailure as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Embedding provider failed during retrieval benchmark",
        ) from exc
