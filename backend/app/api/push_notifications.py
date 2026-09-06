from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.integrations import PushSubscription
from app.schemas.integrations import (
    PushConfigRead,
    PushDispatchRead,
    PushSubscriptionCreate,
    PushSubscriptionRead,
)
from app.services.push_notifications import (
    send_test_push,
    upsert_push_subscription,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _read(row: PushSubscription) -> PushSubscriptionRead:
    return PushSubscriptionRead(
        id=row.id,
        endpoint=row.endpoint,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/config", response_model=PushConfigRead)
def push_config(request: Request) -> PushConfigRead:
    settings = request.app.state.settings
    return PushConfigRead(
        enabled=settings.push_enabled,
        public_key=settings.vapid_public_key if settings.push_enabled else None,
    )


@router.post(
    "/subscriptions",
    response_model=PushSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_push_subscription(
    payload: PushSubscriptionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> PushSubscriptionRead:
    user_id = request.state.user_id
    row = upsert_push_subscription(
        db,
        user_id=user_id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )
    return _read(row)


@router.get("/subscriptions", response_model=list[PushSubscriptionRead])
def list_push_subscriptions(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[PushSubscriptionRead]:
    rows = db.scalars(
        select(PushSubscription)
        .where(PushSubscription.user_id == request.state.user_id)
        .order_by(PushSubscription.created_at.desc())
    ).all()
    return [_read(row) for row in rows]


@router.delete("/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_push_subscription(
    subscription_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    row = db.get(PushSubscription, subscription_id)
    if row is None or row.user_id != request.state.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Push subscription not found",
        )
    db.delete(row)
    db.commit()


@router.post("/test", response_model=PushDispatchRead)
def test_push(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> PushDispatchRead:
    settings = request.app.state.settings
    if not settings.push_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Web Push is not configured on this deployment",
        )
    attempted, sent, disabled = send_test_push(
        db,
        settings,
        user_id=request.state.user_id,
    )
    return PushDispatchRead(attempted=attempted, sent=sent, disabled=disabled)
