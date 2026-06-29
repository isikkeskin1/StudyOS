from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path / "uploads",
        max_upload_mb=1,
    )
    app = create_app(settings)

    with TestClient(app) as test_client:
        registered = test_client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@studyos.local",
                "password": "test-password-123",
            },
        )
        assert registered.status_code == 201
        yield test_client
