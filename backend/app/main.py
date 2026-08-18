from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401
from app.api.courses import router as courses_router
from app.api.health import router as health_router
from app.api.planning import router as planning_router
from app.core.config import Settings, get_settings
from app.core.database import Base, create_database_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
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
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.5.0",
        description="Backend API for StudyOS.",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.engine = engine
    application.state.session_factory = session_factory

    application.include_router(health_router, prefix=resolved_settings.api_prefix)
    application.include_router(courses_router, prefix=resolved_settings.api_prefix)
    application.include_router(planning_router, prefix=resolved_settings.api_prefix)

    @application.get("/")
    def root() -> dict[str, str]:
        return {
            "name": resolved_settings.app_name,
            "status": "running",
        }

    return application


app = create_app()
