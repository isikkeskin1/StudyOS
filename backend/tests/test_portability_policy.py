from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.main import create_app
from app.models.auth import User
from app.models.integrations import SpotifyConnection, SpotifyOAuthState


def test_spotify_credentials_never_enter_portable_exports(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'portability.db'}",
        data_dir=tmp_path / "uploads",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.post(
            "/api/v1/auth/register",
            json={"email": "portable@example.com", "password": "portable-password"},
        ).status_code == 201

        with app.state.session_factory() as db:
            user = db.scalar(select(User).where(User.email == "portable@example.com"))
            assert user is not None
            db.add(
                SpotifyConnection(
                    user_id=user.id,
                    spotify_user_id="spotify-user",
                    display_name="Portable User",
                    product="premium",
                    scopes="user-read-private",
                    access_token_encrypted="encrypted-access-material",
                    refresh_token_encrypted="encrypted-refresh-material",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            db.add(
                SpotifyOAuthState(
                    state_hash="f" * 64,
                    user_id=user.id,
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                )
            )
            db.commit()

        exported = client.get("/api/v1/auth/export")
        assert exported.status_code == 200
        tables = exported.json()["tables"]
        assert "spotify_connections" not in tables
        assert "spotify_oauth_states" not in tables

        bundle = client.get("/api/v1/auth/migration-bundle")
        assert bundle.status_code == 200
        assert b"spotify_connections" not in bundle.content
        assert b"spotify_oauth_states" not in bundle.content
        assert b"encrypted-access-material" not in bundle.content
        assert b"encrypted-refresh-material" not in bundle.content
