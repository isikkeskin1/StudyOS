from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator


class Settings(BaseModel):
    app_name: str = "StudyOS"
    environment: Literal["development", "test", "desktop", "production"] = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./.studyos/studyos.db"
    data_dir: Path = Path("./.studyos/uploads")
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    log_level: str = "INFO"
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0, le=1)
    release: str | None = None
    vapid_public_key: str | None = None
    vapid_private_key: SecretStr | None = None
    vapid_subject: str = "mailto:admin@studyos.local"
    push_poll_seconds: int = Field(default=300, ge=60, le=3600)
    auth_rate_limit_attempts: int = Field(default=10, ge=2, le=100)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    admin_emails: tuple[str, ...] = ()

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

    @property
    def push_enabled(self) -> bool:
        return self.vapid_public_key is not None and self.vapid_private_key is not None

    @model_validator(mode="after")
    def validate_runtime(self) -> Settings:
        if self.environment == "production" and self.database_url.startswith("sqlite"):
            raise ValueError("Production requires a non-SQLite STUDYOS_DATABASE_URL")
        if (self.vapid_public_key is None) != (self.vapid_private_key is None):
            raise ValueError("Both VAPID public and private keys must be configured together")
        if (
            self.tutor_provider == "openai"
            or self.tutor_embedding_provider == "openai"
        ) and self.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required when an OpenAI provider is enabled")
        return self


def get_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY")
    sentry_dsn = os.getenv("STUDYOS_SENTRY_DSN")
    vapid_private_key = os.getenv("STUDYOS_VAPID_PRIVATE_KEY")
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
        vapid_public_key=os.getenv("STUDYOS_VAPID_PUBLIC_KEY") or None,
        vapid_private_key=(
            SecretStr(vapid_private_key) if vapid_private_key else None
        ),
        vapid_subject=os.getenv(
            "STUDYOS_VAPID_SUBJECT", "mailto:admin@studyos.local"
        ),
        push_poll_seconds=int(os.getenv("STUDYOS_PUSH_POLL_SECONDS", "300")),
        auth_rate_limit_attempts=int(os.getenv("STUDYOS_AUTH_RATE_LIMIT_ATTEMPTS", "10")),
        auth_rate_limit_window_seconds=int(
            os.getenv("STUDYOS_AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")
        ),
        admin_emails=tuple(
            email.strip().lower()
            for email in os.getenv("STUDYOS_ADMIN_EMAILS", "").split(",")
            if email.strip()
        ),
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
