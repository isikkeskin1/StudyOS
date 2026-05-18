from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "StudyOS"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./.studyos/studyos.db"
    data_dir: Path = Path("./.studyos/uploads")
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    allowed_extensions: tuple[str, ...] = (
        ".pdf",
        ".docx",
        ".pptx",
        ".txt",
        ".md",
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


def get_settings() -> Settings:
    return Settings(
        environment=os.getenv("STUDYOS_ENV", "development"),
        database_url=os.getenv("STUDYOS_DATABASE_URL", "sqlite:///./.studyos/studyos.db"),
        data_dir=Path(os.getenv("STUDYOS_DATA_DIR", "./.studyos/uploads")),
        max_upload_mb=int(os.getenv("STUDYOS_MAX_UPLOAD_MB", "50")),
    )
