from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401
from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.calendar_focus import router as calendar_focus_router
from app.api.calendar_subscription import public_router as public_calendar_router
from app.api.calendar_subscription import router as calendar_subscription_router
from app.api.catalog import router as catalog_router
from app.api.calibration import router as calibration_router
from app.api.cheat_sheet import router as cheat_sheet_router
from app.api.courses import router as courses_router
from app.api.diagnostics import router as diagnostics_router
from app.api.emergency_planning import router as emergency_planning_router
from app.api.emergency_schedule import router as emergency_schedule_router
from app.api.exam_day import router as exam_day_router
from app.api.forecast_tracking import router as forecast_tracking_router
from app.api.grade_modeling import router as grade_modeling_router
from app.api.health import router as health_router
from app.api.mastery_history import router as mastery_history_router
from app.api.mistakes import router as mistakes_router
from app.api.multi_course_planning import router as multi_course_planning_router
from app.api.planning import router as planning_router
from app.api.push_notifications import router as push_notifications_router
from app.api.review_session import router as review_session_router
from app.api.reviews import router as reviews_router
from app.api.search import router as search_router
from app.api.semester_dashboard import router as semester_dashboard_router
from app.api.semester_queue import router as semester_queue_router
from app.api.tutor import router as tutor_router
from app.api.tutor_benchmark import router as tutor_benchmark_router
from app.api.tutor_benchmark_history import router as tutor_benchmark_history_router
from app.api.tutor_embedding_index import router as tutor_embedding_index_router
from app.api.tutor_remediation import router as tutor_remediation_router
from app.core.auth import AuthenticationMiddleware
from app.core.config import Settings, get_settings
from app.core.database import Base, create_database_engine, create_session_factory
from app.core.hardening import AuthRateLimitMiddleware, SecurityHeadersMiddleware
from app.core.observability import (
    RequestObservabilityMiddleware,
    configure_error_tracking,
    configure_logging,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    configure_error_tracking(
        dsn=(
            resolved_settings.sentry_dsn.get_secret_value()
            if resolved_settings.sentry_dsn is not None
            else None
        ),
        environment=resolved_settings.environment,
        release=resolved_settings.release,
        traces_sample_rate=resolved_settings.sentry_traces_sample_rate,
    )
    engine = create_database_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if resolved_settings.database_url.startswith("sqlite"):
            database_path = resolved_settings.database_url.removeprefix("sqlite:///")
            if database_path != ":memory:":
                from pathlib import Path

                Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        resolved_settings.data_dir.mkdir(parents=True, exist_ok=True)
        if resolved_settings.environment != "production":
            Base.metadata.create_all(engine)
        yield
        engine.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.51.2",
        description="Backend API for StudyOS.",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.add_middleware(AuthenticationMiddleware)
    application.add_middleware(
        AuthRateLimitMiddleware,
        attempts=resolved_settings.auth_rate_limit_attempts,
        window_seconds=resolved_settings.auth_rate_limit_window_seconds,
    )
    application.add_middleware(RequestObservabilityMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)

    application.include_router(health_router, prefix=resolved_settings.api_prefix)
    application.include_router(auth_router, prefix=resolved_settings.api_prefix)
    application.include_router(courses_router, prefix=resolved_settings.api_prefix)
    application.include_router(catalog_router, prefix=resolved_settings.api_prefix)
    application.include_router(planning_router, prefix=resolved_settings.api_prefix)
    application.include_router(emergency_planning_router, prefix=resolved_settings.api_prefix)
    application.include_router(emergency_schedule_router, prefix=resolved_settings.api_prefix)
    application.include_router(multi_course_planning_router, prefix=resolved_settings.api_prefix)
    application.include_router(semester_dashboard_router, prefix=resolved_settings.api_prefix)
    application.include_router(semester_queue_router, prefix=resolved_settings.api_prefix)
    application.include_router(calendar_focus_router, prefix=resolved_settings.api_prefix)
    application.include_router(calendar_subscription_router, prefix=resolved_settings.api_prefix)
    application.include_router(push_notifications_router, prefix=resolved_settings.api_prefix)
    application.include_router(analytics_router, prefix=resolved_settings.api_prefix)
    application.include_router(search_router, prefix=resolved_settings.api_prefix)
    application.include_router(diagnostics_router, prefix=resolved_settings.api_prefix)
    application.include_router(exam_day_router, prefix=resolved_settings.api_prefix)
    application.include_router(mistakes_router, prefix=resolved_settings.api_prefix)
    application.include_router(review_session_router, prefix=resolved_settings.api_prefix)
    application.include_router(cheat_sheet_router, prefix=resolved_settings.api_prefix)
    application.include_router(reviews_router, prefix=resolved_settings.api_prefix)
    application.include_router(mastery_history_router, prefix=resolved_settings.api_prefix)
    application.include_router(calibration_router, prefix=resolved_settings.api_prefix)
    application.include_router(grade_modeling_router, prefix=resolved_settings.api_prefix)
    application.include_router(forecast_tracking_router, prefix=resolved_settings.api_prefix)
    application.include_router(tutor_router, prefix=resolved_settings.api_prefix)
    application.include_router(tutor_benchmark_router, prefix=resolved_settings.api_prefix)
    application.include_router(tutor_benchmark_history_router, prefix=resolved_settings.api_prefix)
    application.include_router(tutor_embedding_index_router, prefix=resolved_settings.api_prefix)
    application.include_router(tutor_remediation_router, prefix=resolved_settings.api_prefix)

    application.include_router(public_calendar_router)

    @application.get("/")
    def root() -> dict[str, str]:
        return {
            "name": resolved_settings.app_name,
            "status": "running",
        }

    return application


app = create_app()
