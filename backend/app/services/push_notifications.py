from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.integrations import PushDelivery, PushSubscription
from app.services.semester_dashboard import build_semester_dashboard


@dataclass(frozen=True)
class PushSignal:
    key: str
    title: str
    body: str
    url: str = "/#overview"


def build_push_signals(db: Session) -> list[PushSignal]:
    dashboard = build_semester_dashboard(db)
    signals: list[PushSignal] = []
    today = datetime.now(UTC).date().isoformat()

    if dashboard.due_review_count > 0:
        signals.append(
            PushSignal(
                key=f"reviews:{today}:{dashboard.due_review_count}",
                title=(
                    f"{dashboard.due_review_count} review"
                    f"{'' if dashboard.due_review_count == 1 else 's'} due"
                ),
                body="Open StudyOS to clear the highest-value spaced reviews first.",
            )
        )

    if dashboard.next_action is not None:
        action = dashboard.next_action
        signals.append(
            PushSignal(
                key=f"next:{action.id}",
                title=f"Next: {action.topic_name}",
                body=(
                    f"{action.course_name} · {action.planned_minutes} min · "
                    f"expected +{action.expected_mark_gain:.2f} marks"
                ),
            )
        )

    selected = next(
        (
            queue
            for queue in dashboard.queues
            if queue.queue_id == dashboard.selected_queue_id
        ),
        None,
    )
    if selected is not None and selected.needs_refresh:
        signals.append(
            PushSignal(
                key=f"queue-refresh:{selected.queue_id}:{selected.revision}",
                title="Study queue needs a refresh",
                body=" · ".join(selected.refresh_reasons)
                or "StudyOS has newer evidence for the plan.",
            )
        )

    return signals


def upsert_push_subscription(
    db: Session,
    *,
    user_id: str,
    endpoint: str,
    p256dh: str,
    auth: str,
) -> PushSubscription:
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    now = datetime.now(UTC)
    if row is None:
        row = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        if row.user_id != user_id:
            db.execute(
                delete(PushDelivery).where(
                    PushDelivery.subscription_id == row.id
                )
            )
        row.user_id = user_id
        row.p256dh = p256dh
        row.auth = auth
        row.enabled = True
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def _send(
    subscription: PushSubscription,
    signal: PushSignal,
    settings: Settings,
) -> None:
    if settings.vapid_private_key is None:
        raise RuntimeError("VAPID private key is not configured")
    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        },
        data=json.dumps(
            {
                "title": signal.title,
                "body": signal.body,
                "tag": signal.key,
                "url": signal.url,
            }
        ),
        vapid_private_key=settings.vapid_private_key.get_secret_value(),
        vapid_claims={"sub": settings.vapid_subject},
    )


def dispatch_push_signals(
    db: Session,
    settings: Settings,
    *,
    user_id: str,
    signals: list[PushSignal] | None = None,
) -> tuple[int, int, int]:
    if not settings.push_enabled:
        return 0, 0, 0

    subscriptions = list(
        db.scalars(
            select(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.enabled.is_(True),
            )
        ).all()
    )
    resolved_signals = signals if signals is not None else build_push_signals(db)
    attempted = 0
    sent = 0
    disabled = 0

    for subscription in subscriptions:
        for signal in resolved_signals:
            existing = db.scalar(
                select(PushDelivery.id).where(
                    PushDelivery.subscription_id == subscription.id,
                    PushDelivery.signal_key == signal.key,
                )
            )
            if existing is not None:
                continue
            attempted += 1
            try:
                _send(subscription, signal, settings)
            except WebPushException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code in {404, 410}:
                    subscription.enabled = False
                    disabled += 1
                    db.commit()
                continue
            db.add(
                PushDelivery(
                    subscription_id=subscription.id,
                    signal_key=signal.key,
                )
            )
            db.commit()
            sent += 1

    return attempted, sent, disabled


def send_test_push(
    db: Session,
    settings: Settings,
    *,
    user_id: str,
) -> tuple[int, int, int]:
    signal = PushSignal(
        key=f"test:{datetime.now(UTC).isoformat()}",
        title="StudyOS push is working",
        body="Closed-app notifications are connected to this device.",
    )
    return dispatch_push_signals(
        db,
        settings,
        user_id=user_id,
        signals=[signal],
    )
