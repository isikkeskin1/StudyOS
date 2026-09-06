from __future__ import annotations

import json
import logging
import time
import uuid

import sentry_sdk
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("studyos.request")


def configure_logging(level: str = "INFO") -> None:
    resolved = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=resolved, format="%(message)s")


def configure_error_tracking(
    *,
    dsn: str | None,
    environment: str,
    release: str | None,
    traces_sample_rate: float,
) -> None:
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
    )


def _emit(payload: dict[str, object]) -> None:
    logger.info(json.dumps(payload, separators=(",", ":"), default=str))


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            _emit(
                {
                    "event": "request_error",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
            logger.exception("Unhandled request exception")
            raise
        finally:
            _emit(
                {
                    "event": "request_complete",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "user_id": getattr(request.state, "user_id", None),
                }
            )
