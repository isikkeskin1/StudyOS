from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "environment": "test",
        "database_url": f"sqlite:///{tmp_path / 'security.db'}",
        "data_dir": tmp_path / "uploads",
        "auth_rate_limit_attempts": 2,
        "auth_rate_limit_window_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)


def test_api_security_headers_are_applied(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers


def test_production_responses_enable_hsts(tmp_path: Path) -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://studyos:studyos@127.0.0.1:5432/studyos",
        data_dir=tmp_path / "uploads",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert (
        response.headers["strict-transport-security"]
        == "max-age=31536000; includeSubDomains"
    )


def test_auth_rate_limit_returns_retry_after(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "rate@example.com", "password": "secure-password"},
        )
        assert registered.status_code == 201
        client.cookies.clear()

        payload = {"email": "rate@example.com", "password": "wrong-password"}
        assert client.post("/api/v1/auth/login", json=payload).status_code == 401
        assert client.post("/api/v1/auth/login", json=payload).status_code == 401

        blocked = client.post("/api/v1/auth/login", json=payload)
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
        assert blocked.headers["x-content-type-options"] == "nosniff"
