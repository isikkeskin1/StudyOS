from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.calendar_focus import (
    CalendarPlanCreateRequest,
    CalendarPlanRead,
    FocusActionRead,
    FocusCompleteRequest,
    FocusSessionRead,
    FocusSkipRequest,
    FocusStartRequest,
)
from app.services.calendar_focus import (
    CalendarFocusInputError,
    calendar_plan_ics,
    complete_focus_session,
    create_calendar_plan,
    get_calendar_plan,
    list_calendar_plans,
    list_focus_sessions,
    read_calendar_plan,
    read_focus_session,
    skip_focus_session,
    start_focus_session,
)
from app.services.semester_queue import (
    SemesterQueueConflictError,
    SemesterQueueNotFoundError,
    read_semester_queue,
)

router = APIRouter(prefix="/semester-queues/{queue_id}", tags=["calendar and focus"])


def _translate(exc: RuntimeError) -> HTTPException:
    if isinstance(exc, SemesterQueueNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, CalendarFocusInputError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


_ERRORS = (CalendarFocusInputError, SemesterQueueConflictError, SemesterQueueNotFoundError)


@router.post("/calendar-plans", response_model=CalendarPlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    queue_id: str,
    payload: CalendarPlanCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CalendarPlanRead:
    try:
        row = create_calendar_plan(db, queue_id, payload)
        return read_calendar_plan(db, row)
    except _ERRORS as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.get("/calendar-plans", response_model=list[CalendarPlanRead])
def list_plans(
    queue_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[CalendarPlanRead]:
    try:
        return list_calendar_plans(db, queue_id)
    except _ERRORS as exc:
        raise _translate(exc) from exc


@router.get("/calendar-plans/{plan_id}", response_model=CalendarPlanRead)
def get_plan(
    queue_id: str,
    plan_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CalendarPlanRead:
    try:
        return read_calendar_plan(db, get_calendar_plan(db, queue_id, plan_id))
    except _ERRORS as exc:
        raise _translate(exc) from exc


@router.get("/calendar-plans/{plan_id}/ics")
def export_plan_ics(
    queue_id: str,
    plan_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        row = get_calendar_plan(db, queue_id, plan_id)
        return Response(
            content=calendar_plan_ics(row),
            media_type="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="studyos-{queue_id[:8]}.ics"'
            },
        )
    except _ERRORS as exc:
        raise _translate(exc) from exc


@router.post("/focus-sessions", response_model=FocusActionRead, status_code=status.HTTP_201_CREATED)
def start_focus(
    queue_id: str,
    payload: FocusStartRequest,
    db: Annotated[Session, Depends(get_db)],
) -> FocusActionRead:
    try:
        row = start_focus_session(db, queue_id, payload)
        return FocusActionRead(
            session=read_focus_session(row),
            queue=read_semester_queue(db, queue_id, auto_refresh=False),
        )
    except _ERRORS as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.get("/focus-sessions", response_model=list[FocusSessionRead])
def list_focus(
    queue_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[FocusSessionRead]:
    try:
        return list_focus_sessions(db, queue_id)
    except _ERRORS as exc:
        raise _translate(exc) from exc


@router.get("/focus-sessions/{session_id}", response_model=FocusSessionRead)
def get_focus(
    queue_id: str,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> FocusSessionRead:
    try:
        rows = list_focus_sessions(db, queue_id)
        row = next((item for item in rows if item.id == session_id), None)
        if row is None:
            raise SemesterQueueNotFoundError("Focus session not found")
        return row
    except _ERRORS as exc:
        raise _translate(exc) from exc


@router.post("/focus-sessions/{session_id}/complete", response_model=FocusActionRead)
def complete_focus(
    queue_id: str,
    session_id: str,
    payload: FocusCompleteRequest,
    db: Annotated[Session, Depends(get_db)],
) -> FocusActionRead:
    try:
        row, queue = complete_focus_session(db, queue_id, session_id, payload)
        return FocusActionRead(
            session=read_focus_session(row),
            queue=read_semester_queue(db, queue.id, auto_refresh=False),
        )
    except _ERRORS as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.post("/focus-sessions/{session_id}/skip", response_model=FocusActionRead)
def skip_focus(
    queue_id: str,
    session_id: str,
    payload: FocusSkipRequest,
    db: Annotated[Session, Depends(get_db)],
) -> FocusActionRead:
    try:
        row, queue = skip_focus_session(db, queue_id, session_id, payload)
        return FocusActionRead(
            session=read_focus_session(row),
            queue=read_semester_queue(db, queue.id, auto_refresh=False),
        )
    except _ERRORS as exc:
        db.rollback()
        raise _translate(exc) from exc
