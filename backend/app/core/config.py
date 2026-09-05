from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class Settings(BaseModel):
    app_name: str = "StudyOS"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./.studyos/studyos.db"
    data_dir: Path = Path("./.studyos/uploads")
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    tutor_provider: Literal["local", "openai"] = "local"
    tutor_embedding_provider: Literal["none", "openai"] = "none"
    openai_api_key: SecretStr | None = None
    openai_tutor_model: str = "gpt-5.6-luna"
    openai_tutor_max_output_tokens: int = Field(default=900, ge=128, le=4096)
    openai_embedding_model: str = "text-embedding-3-small"
    tutor_embedding_max_candidates: int = Field(default=128, ge=8, le=1024)
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
    api_key = os.getenv("OPENAI_API_KEY")
    return Settings(
        environment=os.getenv("STUDYOS_ENV", "development"),
        database_url=os.getenv("STUDYOS_DATABASE_URL", "sqlite:///./.studyos/studyos.db"),
        data_dir=Path(os.getenv("STUDYOS_DATA_DIR", "./.studyos/uploads")),
        max_upload_mb=int(os.getenv("STUDYOS_MAX_UPLOAD_MB", "50")),
        tutor_provider=os.getenv("STUDYOS_TUTOR_PROVIDER", "local").lower(),
        tutor_embedding_provider=os.getenv(
            "STUDYOS_TUTOR_EMBEDDING_PROVIDER", "none"
        ).lower(),
        openai_api_key=SecretStr(api_key) if api_key else None,
        openai_tutor_model=os.getenv("STUDYOS_OPENAI_TUTOR_MODEL", "gpt-5.6-luna"),
        openai_tutor_max_output_tokens=int(
            os.getenv("STUDYOS_OPENAI_TUTOR_MAX_OUTPUT_TOKENS", "900")
        ),
        openai_embedding_model=os.getenv(
            "STUDYOS_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        ),
        tutor_embedding_max_candidates=int(
            os.getenv("STUDYOS_TUTOR_EMBEDDING_MAX_CANDIDATES", "128")
        ),
    )
