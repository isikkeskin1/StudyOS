from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from http import HTTPStatus

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

_AUTH_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if request.app.state.settings.environment == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        attempts: int,
        window_seconds: int,
    ) -> None:
        super().__init__(app)
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _key(self, request: Request) -> str:
        client = request.client.host if request.client is not None else "unknown"
        return f"{client}:{request.url.path}"

    def _retry_after(self, key: str, now: float) -> int | None:
        with self._lock:
            bucket = self._attempts[key]
            cutoff = now - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.attempts:
                return max(1, int(self.window_seconds - (now - bucket[0])) + 1)
            bucket.append(now)
            return None

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path in _AUTH_PATHS:
            retry_after = self._retry_after(self._key(request), time.monotonic())
            if retry_after is not None:
                return JSONResponse(
                    {"detail": "Too many authentication attempts. Try again later."},
                    status_code=HTTPStatus.TOO_MANY_REQUESTS,
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)
