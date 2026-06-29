from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator


class Settings(BaseModel):
    app_name: str = "StudyOS"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./.studyos/studyos.db"
    data_dir: Path = Path("./.studyos/uploads")
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    log_level: str = "INFO"
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0, le=1)
    release: str | None = None

    tutor_provider: Literal["local", "openai"] = "local"
    tutor_embedding_provider: Literal["none", "openai"] = "none"
    openai_api_key: SecretStr | None = None
    openai_tutor_model: str = "gpt-5.6-luna"
    openai_tutor_max_output_tokens: int = Field(default=900, ge=128, le=4096)
    openai_embedding_model: str = "text-embedding-3-small"
    tutor_embedding_max_candidates: int = Field(default=128, ge=8, le=1024)
    tutor_embedding_batch_size: int = Field(default=64, ge=1, le=256)
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

    @model_validator(mode="after")
    def validate_runtime(self) -> Settings:
        if self.environment == "production" and self.database_url.startswith("sqlite"):
            raise ValueError("Production requires a non-SQLite STUDYOS_DATABASE_URL")
        if (
            self.tutor_provider == "openai"
            or self.tutor_embedding_provider == "openai"
        ) and self.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required when an OpenAI provider is enabled")
        return self


def get_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY")
    sentry_dsn = os.getenv("STUDYOS_SENTRY_DSN")
    return Settings(
        environment=os.getenv("STUDYOS_ENV", "development").lower(),
        database_url=os.getenv("STUDYOS_DATABASE_URL", "sqlite:///./.studyos/studyos.db"),
        data_dir=Path(os.getenv("STUDYOS_DATA_DIR", "./.studyos/uploads")),
        max_upload_mb=int(os.getenv("STUDYOS_MAX_UPLOAD_MB", "50")),
        log_level=os.getenv("STUDYOS_LOG_LEVEL", "INFO"),
        sentry_dsn=SecretStr(sentry_dsn) if sentry_dsn else None,
        sentry_traces_sample_rate=float(
            os.getenv("STUDYOS_SENTRY_TRACES_SAMPLE_RATE", "0")
        ),
        release=os.getenv("STUDYOS_RELEASE"),
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
        tutor_embedding_batch_size=int(
            os.getenv("STUDYOS_TUTOR_EMBEDDING_BATCH_SIZE", "64")
        ),
    )
