from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.tutor_benchmark_history import (
    TutorBenchmarkRunCreate,
    TutorBenchmarkRunHistoryRead,
    TutorBenchmarkRunRead,
    TutorBenchmarkSuiteCreate,
    TutorBenchmarkSuiteRead,
)
from app.services.tutor_benchmark_history import (
    TutorBenchmarkHistoryError,
    create_benchmark_suite,
    get_benchmark_run,
    get_benchmark_suite,
    list_benchmark_runs,
    list_benchmark_suites,
    run_benchmark_suite,
    suite_read,
)
from app.services.tutor_embeddings import (
    TutorEmbeddingConfig,
    TutorEmbeddingFailure,
    TutorEmbeddingUnavailable,
)

router = APIRouter(prefix="/courses", tags=["tutor"])


def _course(db: Session, course_id: str) -> None:
    if db.get(Course, course_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")


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


def _suite_or_404(db: Session, course_id: str, suite_id: str):
    suite = get_benchmark_suite(db, course_id, suite_id)
    if suite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retrieval benchmark suite not found",
        )
    return suite


@router.post(
    "/{course_id}/tutor/retrieval-benchmark-suites",
    response_model=TutorBenchmarkSuiteRead,
    status_code=status.HTTP_201_CREATED,
)
def tutor_create_benchmark_suite(
    course_id: str,
    payload: TutorBenchmarkSuiteCreate,
    db: Annotated[Session, Depends(get_db)],
) -> TutorBenchmarkSuiteRead:
    _course(db, course_id)
    try:
        return create_benchmark_suite(db, course_id, payload)
    except TutorBenchmarkHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/{course_id}/tutor/retrieval-benchmark-suites",
    response_model=list[TutorBenchmarkSuiteRead],
)
def tutor_list_benchmark_suites(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[TutorBenchmarkSuiteRead]:
    _course(db, course_id)
    return list_benchmark_suites(db, course_id)


@router.get(
    "/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}",
    response_model=TutorBenchmarkSuiteRead,
)
def tutor_get_benchmark_suite(
    course_id: str,
    suite_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> TutorBenchmarkSuiteRead:
    _course(db, course_id)
    return suite_read(_suite_or_404(db, course_id, suite_id), include_cases=True)


@router.post(
    "/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}/runs",
    response_model=TutorBenchmarkRunRead,
    status_code=status.HTTP_201_CREATED,
)
def tutor_run_benchmark_suite(
    course_id: str,
    suite_id: str,
    payload: TutorBenchmarkRunCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TutorBenchmarkRunRead:
    _course(db, course_id)
    suite = _suite_or_404(db, course_id, suite_id)
    try:
        return run_benchmark_suite(
            db,
            suite,
            payload,
            embedding_config=_embedding_config(request),
        )
    except TutorBenchmarkHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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


@router.get(
    "/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}/runs",
    response_model=TutorBenchmarkRunHistoryRead,
)
def tutor_list_benchmark_runs(
    course_id: str,
    suite_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> TutorBenchmarkRunHistoryRead:
    _course(db, course_id)
    return list_benchmark_runs(db, _suite_or_404(db, course_id, suite_id))


@router.get(
    "/{course_id}/tutor/retrieval-benchmark-suites/{suite_id}/runs/{run_id}",
    response_model=TutorBenchmarkRunRead,
)
def tutor_get_benchmark_run(
    course_id: str,
    suite_id: str,
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> TutorBenchmarkRunRead:
    _course(db, course_id)
    suite = _suite_or_404(db, course_id, suite_id)
    run = get_benchmark_run(db, suite, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retrieval benchmark run not found",
        )
    return run
