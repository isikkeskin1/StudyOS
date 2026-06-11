from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.semester_queue import SemesterStudyQueue
from app.schemas.semester_queue import (
    SemesterQueueCompleteBlockRequest,
    SemesterQueueCreateRequest,
    SemesterQueueRead,
    SemesterQueueRefreshRequest,
    SemesterQueueSkipBlockRequest,
)
from app.services.emergency_planning import EmergencyPlanUnavailableError
from app.services.multi_course_planning import (
    MultiCourseCourseNotFoundError,
    MultiCoursePlanUnavailableError,
)
from app.services.semester_queue import (
    SemesterQueueConflictError,
    SemesterQueueNotFoundError,
    complete_semester_block,
    create_semester_queue,
    read_semester_queue,
    refresh_semester_queue,
    skip_semester_block,
    start_semester_block,
)

router = APIRouter(prefix="/semester-queues", tags=["planning"])


def _translate(exc: RuntimeError) -> HTTPException:
    if isinstance(exc, (SemesterQueueNotFoundError, MultiCourseCourseNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


_QUEUE_ERRORS = (
    EmergencyPlanUnavailableError,
    MultiCoursePlanUnavailableError,
    MultiCourseCourseNotFoundError,
    SemesterQueueConflictError,
    SemesterQueueNotFoundError,
)


@router.post("", response_model=SemesterQueueRead, status_code=status.HTTP_201_CREATED)
def create_queue(
    payload: SemesterQueueCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SemesterQueueRead:
    try:
        queue = create_semester_queue(db, payload)
        return read_semester_queue(db, queue.id, auto_refresh=False)
    except _QUEUE_ERRORS as exc:
        raise _translate(exc) from exc


@router.get("", response_model=list[SemesterQueueRead])
def list_queues(db: Annotated[Session, Depends(get_db)]) -> list[SemesterQueueRead]:
    queue_ids = list(
        db.scalars(
            select(SemesterStudyQueue.id).order_by(SemesterStudyQueue.created_at.desc())
        ).all()
    )
    return [read_semester_queue(db, queue_id) for queue_id in queue_ids]


@router.get("/{queue_id}", response_model=SemesterQueueRead)
def get_queue(
    queue_id: str, db: Annotated[Session, Depends(get_db)]
) -> SemesterQueueRead:
    try:
        return read_semester_queue(db, queue_id)
    except _QUEUE_ERRORS as exc:
        raise _translate(exc) from exc


@router.post("/{queue_id}/blocks/{block_id}/start", response_model=SemesterQueueRead)
def start_block(
    queue_id: str,
    block_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> SemesterQueueRead:
    try:
        queue = start_semester_block(db, queue_id, block_id)
        return read_semester_queue(db, queue.id, auto_refresh=False)
    except _QUEUE_ERRORS as exc:
        raise _translate(exc) from exc


@router.post("/{queue_id}/blocks/{block_id}/complete", response_model=SemesterQueueRead)
def complete_block(
    queue_id: str,
    block_id: str,
    payload: SemesterQueueCompleteBlockRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SemesterQueueRead:
    try:
        queue = complete_semester_block(db, queue_id, block_id, payload)
        return read_semester_queue(db, queue.id, auto_refresh=False)
    except _QUEUE_ERRORS as exc:
        raise _translate(exc) from exc


@router.post("/{queue_id}/blocks/{block_id}/skip", response_model=SemesterQueueRead)
def skip_block(
    queue_id: str,
    block_id: str,
    payload: SemesterQueueSkipBlockRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SemesterQueueRead:
    try:
        queue = skip_semester_block(db, queue_id, block_id, payload)
        return read_semester_queue(db, queue.id, auto_refresh=False)
    except _QUEUE_ERRORS as exc:
        raise _translate(exc) from exc


@router.post("/{queue_id}/refresh", response_model=SemesterQueueRead)
def refresh_queue(
    queue_id: str,
    payload: SemesterQueueRefreshRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SemesterQueueRead:
    try:
        queue = refresh_semester_queue(db, queue_id, payload)
        return read_semester_queue(db, queue.id, auto_refresh=False)
    except _QUEUE_ERRORS as exc:
        raise _translate(exc) from exc
