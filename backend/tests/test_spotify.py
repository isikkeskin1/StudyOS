from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.spotify import decrypt_token, encrypt_token


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'spotify.db'}",
        data_dir=tmp_path / "uploads",
        spotify_client_id="spotify-client",
        spotify_client_secret="spotify-secret",
        integration_secret="studyos-integration-test-secret",
        spotify_redirect_uri="https://studyos.courses/api/v1/integrations/spotify/callback",
    )


def test_spotify_tokens_are_encrypted_at_rest(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    encrypted = encrypt_token(settings, "spotify-access-token")
    assert encrypted != "spotify-access-token"
    assert decrypt_token(settings, encrypted) == "spotify-access-token"


def test_spotify_connect_requires_account_and_returns_stateful_oauth_url(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/v1/integrations/spotify/status").status_code == 401
        assert client.post(
            "/api/v1/auth/register",
            json={"email": "music@example.com", "password": "music-password"},
        ).status_code == 201

        status = client.get("/api/v1/integrations/spotify/status")
        assert status.status_code == 200
        assert status.json()["configured"] is True
        assert status.json()["connected"] is False

        connect = client.post("/api/v1/integrations/spotify/connect")
        assert connect.status_code == 200
        parsed = urlparse(connect.json()["authorize_url"])
        params = parse_qs(parsed.query)
        assert parsed.netloc == "accounts.spotify.com"
        assert params["client_id"] == ["spotify-client"]
        assert params["state"][0]
        assert "user-read-playback-state" in params["scope"][0]
        assert "user-modify-playback-state" in params["scope"][0]


def test_spotify_callback_is_public_for_desktop_pairing(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/api/v1/integrations/spotify/callback")
        assert response.status_code == 303
        assert response.headers["location"] == "/?spotify=invalid"
