from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def test_health_endpoints_report_liveness_and_readiness(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'health.db'}",
        data_dir=tmp_path / "uploads",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        live = client.get("/api/v1/health/live")
        assert live.status_code == 200
        assert live.json()["status"] == "alive"
        assert live.json()["version"] == "0.52.0"
        assert live.headers["x-request-id"]

        ready = client.get("/api/v1/health/ready")
        assert ready.status_code == 200
        assert ready.json()["database"] == "ready"
        assert ready.json()["storage"] == "ready"
        assert ready.headers["x-request-id"]


def test_request_id_is_preserved_when_supplied(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'request-id.db'}",
        data_dir=tmp_path / "uploads",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"X-Request-ID": "trace-test-123"},
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "trace-test-123"


def test_production_rejects_sqlite_database() -> None:
    with pytest.raises(ValidationError, match="Production requires a non-SQLite"):
        Settings(environment="production", database_url="sqlite:///prod.db")


def test_openai_provider_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(tutor_provider="openai")


def test_readiness_fails_when_upload_storage_is_unwritable_path(tmp_path: Path) -> None:
    data_dir = tmp_path / "uploads"
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'storage-health.db'}",
        data_dir=data_dir,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        data_dir.rmdir()
        data_dir.write_text("not a directory", encoding="utf-8")
        ready = client.get("/api/v1/health/ready")

    assert ready.status_code == 503
    assert ready.json()["detail"] == "Upload storage is not ready"
