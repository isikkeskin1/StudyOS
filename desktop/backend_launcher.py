from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings
from app.main import app as studyos_app

_LEGACY_DESKTOP_BASELINE = "0004_ingestion_quality"


def _migration_script_dir() -> Path:
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "alembic",
        Path(__file__).resolve().parents[1] / "backend" / "alembic",
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "env.py").is_file():
            return candidate
    raise RuntimeError("StudyOS desktop migration scripts are missing")


def migrate_desktop_database() -> None:
    settings = get_settings()
    config = Config()
    config.set_main_option("script_location", str(_migration_script_dir()))

    engine = create_engine(
        settings.database_url,
        connect_args=(
            {"check_same_thread": False}
            if settings.database_url.startswith("sqlite")
            else {}
        ),
    )
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    if tables and "alembic_version" not in tables:
        command.stamp(config, _LEGACY_DESKTOP_BASELINE)

    command.upgrade(config, "head")


def main() -> None:
    migrate_desktop_database()
    host = os.getenv("STUDYOS_DESKTOP_HOST", "127.0.0.1")
    port = int(os.environ["STUDYOS_DESKTOP_PORT"])
    uvicorn.run(
        studyos_app,
        host=host,
        port=port,
        log_level=os.getenv("STUDYOS_LOG_LEVEL", "warning").lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
