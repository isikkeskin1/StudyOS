from __future__ import annotations

from datetime import UTC, datetime
from http import HTTPStatus

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.security import token_digest
from app.models.auth import AuthSession
from app.models.course import Course
from app.models.semester_queue import SemesterStudyQueue

PUBLIC_API_PATHS = {
    "/api/v1/auth/register",
    "/api/v1/auth/login",
}
PUBLIC_API_PREFIXES = ("/api/v1/health",)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            not path.startswith("/api/v1")
            or path in PUBLIC_API_PATHS
            or path.startswith(PUBLIC_API_PREFIXES)
        ):
            return await call_next(request)

        token = request.cookies.get("studyos_session")
        authorization = request.headers.get("authorization", "")
        if not token and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()

        if not token:
            return JSONResponse(
                {"detail": "Authentication required"},
                status_code=HTTPStatus.UNAUTHORIZED,
            )

        session_factory = request.app.state.session_factory
        with session_factory() as db:
            auth_session = db.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_digest(token))
            )
            if auth_session is None:
                response = JSONResponse(
                    {"detail": "Session expired or invalid"},
                    status_code=HTTPStatus.UNAUTHORIZED,
                )
                response.delete_cookie("studyos_session", path="/")
                return response

            if _utc(auth_session.expires_at) <= datetime.now(UTC):
                db.delete(auth_session)
                db.commit()
                response = JSONResponse(
                    {"detail": "Session expired or invalid"},
                    status_code=HTTPStatus.UNAUTHORIZED,
                )
                response.delete_cookie("studyos_session", path="/")
                return response

            user_id = auth_session.user_id
            request.state.user_id = user_id

            segments = [segment for segment in path.split("/") if segment]
            if len(segments) >= 4 and segments[2] == "courses":
                course_id = segments[3]
                owned = db.scalar(
                    select(Course.id).where(Course.id == course_id, Course.user_id == user_id)
                )
                if owned is None:
                    return JSONResponse(
                        {"detail": "Course not found"},
                        status_code=HTTPStatus.NOT_FOUND,
                    )
            if len(segments) >= 4 and segments[2] == "semester-queues":
                queue_id = segments[3]
                owned = db.scalar(
                    select(SemesterStudyQueue.id).where(
                        SemesterStudyQueue.id == queue_id,
                        SemesterStudyQueue.user_id == user_id,
                    )
                )
                if owned is None:
                    return JSONResponse(
                        {"detail": "Semester study queue not found"},
                        status_code=HTTPStatus.NOT_FOUND,
                    )

        return await call_next(request)
