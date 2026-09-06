from __future__ import annotations

import logging
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import create_database_engine, create_session_factory
from app.core.observability import configure_error_tracking, configure_logging
from app.models.auth import User
from app.services.push_notifications import dispatch_push_signals

logger = logging.getLogger("studyos.push_worker")


def run_once() -> None:
    settings = get_settings()
    if not settings.push_enabled:
        logger.info("Web Push disabled: VAPID keys are not configured")
        return

    engine = create_database_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        with factory() as db:
            user_ids = list(db.scalars(select(User.id)).all())
        for user_id in user_ids:
            with factory() as db:
                db.info["user_id"] = user_id
                attempted, sent, disabled = dispatch_push_signals(
                    db,
                    settings,
                    user_id=user_id,
                )
                if attempted:
                    logger.info(
                        "push dispatch user=%s attempted=%s sent=%s disabled=%s",
                        user_id,
                        attempted,
                        sent,
                        disabled,
                    )
    finally:
        engine.dispose()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_error_tracking(
        dsn=(
            settings.sentry_dsn.get_secret_value()
            if settings.sentry_dsn is not None
            else None
        ),
        environment=settings.environment,
        release=settings.release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    interval = settings.push_poll_seconds
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("Push worker iteration failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
