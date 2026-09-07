from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import token_digest
from app.models.integrations import SpotifyConnection, SpotifyOAuthState

logger = logging.getLogger(__name__)

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"
SPOTIFY_SCOPES = (
    "user-read-private",
    "user-read-playback-state",
    "user-read-currently-playing",
    "user-modify-playback-state",
    "user-read-recently-played",
)


class SpotifyIntegrationError(RuntimeError):
    pass


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _fernet(settings: Settings) -> Fernet:
    if settings.integration_secret is None:
        raise SpotifyIntegrationError("StudyOS integration encryption is not configured")
    secret = settings.integration_secret.get_secret_value().encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_token(settings: Settings, value: str) -> str:
    return _fernet(settings).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_token(settings: Settings, value: str) -> str:
    try:
        return _fernet(settings).decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SpotifyIntegrationError(
            "Spotify connection credentials could not be decrypted"
        ) from exc


def require_spotify(settings: Settings) -> None:
    if not settings.spotify_configured:
        raise SpotifyIntegrationError("Spotify integration is not configured")


def create_oauth_state(db: Session, settings: Settings, user_id: str) -> tuple[str, str]:
    require_spotify(settings)
    now = datetime.now(UTC)
    db.execute(delete(SpotifyOAuthState).where(SpotifyOAuthState.expires_at <= now))
    state = secrets.token_urlsafe(32)
    db.add(
        SpotifyOAuthState(
            state_hash=token_digest(state),
            user_id=user_id,
            expires_at=now + timedelta(minutes=10),
        )
    )
    db.commit()
    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": " ".join(SPOTIFY_SCOPES),
        "state": state,
        "show_dialog": "false",
    }
    return state, f"{SPOTIFY_AUTHORIZE_URL}?{urlencode(params)}"


def _token_request(settings: Settings, data: dict[str, str]) -> dict:
    require_spotify(settings)
    if settings.spotify_client_id is None or settings.spotify_client_secret is None:
        raise SpotifyIntegrationError("Spotify client credentials are incomplete")
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.post(
                SPOTIFY_TOKEN_URL,
                data=data,
                auth=(
                    settings.spotify_client_id,
                    settings.spotify_client_secret.get_secret_value(),
                ),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Spotify token exchange failed: %s", type(exc).__name__)
        raise SpotifyIntegrationError("Spotify authorization could not be completed") from exc


def _spotify_json(access_token: str, path: str) -> dict:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{SPOTIFY_API_URL}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SpotifyIntegrationError("Spotify profile could not be loaded") from exc


def complete_oauth(
    db: Session,
    settings: Settings,
    *,
    state: str,
    code: str,
) -> SpotifyConnection:
    now = datetime.now(UTC)
    state_row = db.get(SpotifyOAuthState, token_digest(state))
    if state_row is None or _utc(state_row.expires_at) <= now:
        if state_row is not None:
            db.delete(state_row)
            db.commit()
        raise SpotifyIntegrationError("Spotify authorization state is invalid or expired")

    user_id = state_row.user_id
    db.delete(state_row)
    db.flush()

    token_data = _token_request(
        settings,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.spotify_redirect_uri,
        },
    )
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        db.rollback()
        raise SpotifyIntegrationError("Spotify did not return reusable account credentials")

    profile = _spotify_json(access_token, "/me")
    spotify_user_id = profile.get("id")
    if not isinstance(spotify_user_id, str):
        db.rollback()
        raise SpotifyIntegrationError("Spotify profile response was incomplete")

    connection = db.scalar(
        select(SpotifyConnection).where(SpotifyConnection.user_id == user_id)
    )
    if connection is None:
        connection = SpotifyConnection(
            user_id=user_id,
            spotify_user_id=spotify_user_id,
            scopes=str(token_data.get("scope") or ""),
            access_token_encrypted=encrypt_token(settings, access_token),
            refresh_token_encrypted=encrypt_token(settings, refresh_token),
            expires_at=now + timedelta(seconds=int(token_data.get("expires_in") or 3600)),
        )
        db.add(connection)
    else:
        connection.spotify_user_id = spotify_user_id
        connection.scopes = str(token_data.get("scope") or connection.scopes)
        connection.access_token_encrypted = encrypt_token(settings, access_token)
        connection.refresh_token_encrypted = encrypt_token(settings, refresh_token)
        connection.expires_at = now + timedelta(seconds=int(token_data.get("expires_in") or 3600))
        connection.updated_at = now

    connection.display_name = profile.get("display_name")
    connection.product = profile.get("product")
    db.commit()
    db.refresh(connection)
    return connection


def disconnect_spotify(db: Session, user_id: str) -> bool:
    connection = db.scalar(
        select(SpotifyConnection).where(SpotifyConnection.user_id == user_id)
    )
    if connection is None:
        return False
    db.delete(connection)
    db.commit()
    return True


def get_connection(db: Session, user_id: str) -> SpotifyConnection | None:
    return db.scalar(select(SpotifyConnection).where(SpotifyConnection.user_id == user_id))


def _refresh_access_token(
    db: Session,
    settings: Settings,
    connection: SpotifyConnection,
) -> str:
    refresh_token = decrypt_token(settings, connection.refresh_token_encrypted)
    token_data = _token_request(
        settings,
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    access_token = token_data.get("access_token")
    if not isinstance(access_token, str):
        raise SpotifyIntegrationError("Spotify token refresh returned no access token")

    new_refresh = token_data.get("refresh_token")
    connection.access_token_encrypted = encrypt_token(settings, access_token)
    if isinstance(new_refresh, str) and new_refresh:
        connection.refresh_token_encrypted = encrypt_token(settings, new_refresh)
    connection.scopes = str(token_data.get("scope") or connection.scopes)
    connection.expires_at = datetime.now(UTC) + timedelta(
        seconds=int(token_data.get("expires_in") or 3600)
    )
    connection.updated_at = datetime.now(UTC)
    db.commit()
    return access_token


def access_token_for(
    db: Session,
    settings: Settings,
    connection: SpotifyConnection,
) -> str:
    if _utc(connection.expires_at) <= datetime.now(UTC) + timedelta(seconds=60):
        return _refresh_access_token(db, settings, connection)
    return decrypt_token(settings, connection.access_token_encrypted)


def spotify_request(
    db: Session,
    settings: Settings,
    connection: SpotifyConnection,
    *,
    method: str,
    path: str,
    json: dict | None = None,
) -> httpx.Response:
    access_token = access_token_for(db, settings, connection)
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.request(
                method,
                f"{SPOTIFY_API_URL}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                json=json,
            )
            if response.status_code == 401:
                access_token = _refresh_access_token(db, settings, connection)
                response = client.request(
                    method,
                    f"{SPOTIFY_API_URL}{path}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=json,
                )
            return response
    except httpx.HTTPError as exc:
        raise SpotifyIntegrationError("Spotify is temporarily unavailable") from exc
