from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.integrations import CalendarSubscription
from app.schemas.integrations import (
    CalendarSubscriptionCreate,
    CalendarSubscriptionCreated,
    CalendarSubscriptionRead,
)
from app.services.calendar_subscription import (
    calendar_subscription_ics,
    create_calendar_subscription,
    created_calendar_subscription,
    find_calendar_subscription,
    read_calendar_subscription,
    revoke_calendar_subscription,
)
from app.services.calendar_focus import CalendarFocusInputError

router = APIRouter(
    prefix="/semester-queues/{queue_id}/calendar-subscriptions",
    tags=["calendar and focus"],
)
public_router = APIRouter(tags=["calendar and focus"])


@router.post(
    "",
    response_model=CalendarSubscriptionCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription(
    queue_id: str,
    payload: CalendarSubscriptionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> CalendarSubscriptionCreated:
    try:
        row, token = create_calendar_subscription(
            db,
            user_id=request.state.user_id,
            queue_id=queue_id,
            timezone=payload.timezone,
            start_at=payload.start_at,
            break_minutes=payload.break_minutes,
        )
    except CalendarFocusInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return created_calendar_subscription(row, token)


@router.get("", response_model=list[CalendarSubscriptionRead])
def list_subscriptions(
    queue_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[CalendarSubscriptionRead]:
    rows = db.scalars(
        select(CalendarSubscription)
        .where(
            CalendarSubscription.queue_id == queue_id,
            CalendarSubscription.user_id == request.state.user_id,
        )
        .order_by(CalendarSubscription.created_at.desc())
    ).all()
    return [read_calendar_subscription(row) for row in rows]


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_subscription(
    queue_id: str,
    subscription_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    row = db.get(CalendarSubscription, subscription_id)
    if (
        row is None
        or row.queue_id != queue_id
        or row.user_id != request.state.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar subscription not found",
        )
    revoke_calendar_subscription(db, row)


@public_router.get("/calendar/{token}.ics")
def live_calendar_feed(
    token: str,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    row = find_calendar_subscription(db, token)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar subscription not found",
        )
    try:
        content = calendar_subscription_ics(db, row)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": 'inline; filename="studyos-live.ics"',
        },
    )
