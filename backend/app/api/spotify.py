from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.integrations import SpotifyConnection
from app.schemas.spotify import (
    SpotifyAuthorizeRead,
    SpotifyControlRequest,
    SpotifyPlayerRead,
    SpotifyStatusRead,
    SpotifyTrackRead,
)
from app.services.spotify import (
    SpotifyIntegrationError,
    complete_oauth,
    create_oauth_state,
    disconnect_spotify,
    get_connection,
    spotify_request,
)

router = APIRouter(prefix="/integrations/spotify", tags=["integrations", "spotify"])


def _user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return str(user_id)


def _service_error(exc: SpotifyIntegrationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    )


def _callback_response(
    request: Request,
    outcome: str,
    *,
    title: str,
    message: str,
) -> RedirectResponse | HTMLResponse:
    # Web OAuth runs in the same browser and can return directly to the workspace.
    # Desktop OAuth opens the system browser, which often has no StudyOS session cookie;
    # give that flow a deliberate completion page instead of dropping it on sign-in.
    if request.cookies.get("studyos_session"):
        return RedirectResponse(
            url=f"/?spotify={outcome}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    document = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} · StudyOS</title>
  </head>
  <body>
    <main>
      <p>StudyOS</p>
      <h1>{title}</h1>
      <p>{message}</p>
      <p>You can close this tab and return to the StudyOS app.</p>
      <a href="/">Open StudyOS in this browser</a>
    </main>
  </body>
</html>"""
    return HTMLResponse(document)


@router.get("/status", response_model=SpotifyStatusRead)
def spotify_status(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SpotifyStatusRead:
    settings = request.app.state.settings
    connection = get_connection(db, _user_id(request))
    return SpotifyStatusRead(
        configured=settings.spotify_configured,
        connected=connection is not None,
        display_name=connection.display_name if connection else None,
        spotify_user_id=connection.spotify_user_id if connection else None,
        product=connection.product if connection else None,
        premium=(connection.product or "").lower() == "premium" if connection else False,
    )


@router.post("/connect", response_model=SpotifyAuthorizeRead)
def spotify_connect(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SpotifyAuthorizeRead:
    settings = request.app.state.settings
    try:
        _, authorize_url = create_oauth_state(db, settings, _user_id(request))
    except SpotifyIntegrationError as exc:
        raise _service_error(exc) from exc
    return SpotifyAuthorizeRead(authorize_url=authorize_url)


@router.get("/callback", include_in_schema=False)
def spotify_callback(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    state: str | None = Query(default=None),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse | HTMLResponse:
    if error:
        return _callback_response(
            request,
            "denied",
            title="Spotify connection cancelled",
            message="Spotify did not grant StudyOS access.",
        )
    if not state or not code:
        return _callback_response(
            request,
            "invalid",
            title="Spotify connection could not be completed",
            message="The authorization response was incomplete or expired.",
        )
    try:
        complete_oauth(db, request.app.state.settings, state=state, code=code)
    except SpotifyIntegrationError:
        return _callback_response(
            request,
            "error",
            title="Spotify connection could not be completed",
            message="StudyOS could not finish the Spotify authorization.",
        )
    return _callback_response(
        request,
        "connected",
        title="Spotify connected",
        message="Your Spotify account is now linked to StudyOS.",
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def spotify_disconnect(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    disconnect_spotify(db, _user_id(request))


def _connection_or_404(request: Request, db: Session) -> SpotifyConnection:
    connection = get_connection(db, _user_id(request))
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Spotify is not connected",
        )
    return connection


def _track_from_payload(item: dict[str, Any] | None) -> SpotifyTrackRead | None:
    if not item:
        return None
    artists = [
        str(artist.get("name"))
        for artist in item.get("artists", [])
        if isinstance(artist, dict) and artist.get("name")
    ]
    album = item.get("album") if isinstance(item.get("album"), dict) else {}
    images = album.get("images", []) if isinstance(album, dict) else []
    image_url = next(
        (
            str(image.get("url"))
            for image in images
            if isinstance(image, dict) and image.get("url")
        ),
        None,
    )
    external_urls = item.get("external_urls")
    external_url = external_urls.get("spotify") if isinstance(external_urls, dict) else None
    duration_ms = item.get("duration_ms")
    return SpotifyTrackRead(
        name=str(item.get("name") or "Unknown track"),
        artists=artists,
        album=str(album.get("name")) if isinstance(album, dict) and album.get("name") else None,
        image_url=image_url,
        duration_ms=duration_ms if isinstance(duration_ms, int) else None,
        uri=item.get("uri") if isinstance(item.get("uri"), str) else None,
        external_url=external_url if isinstance(external_url, str) else None,
    )


@router.get("/player", response_model=SpotifyPlayerRead)
def spotify_player(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SpotifyPlayerRead:
    connection = _connection_or_404(request, db)
    try:
        response = spotify_request(
            db,
            request.app.state.settings,
            connection,
            method="GET",
            path="/me/player",
        )
    except SpotifyIntegrationError as exc:
        raise _service_error(exc) from exc

    if response.status_code == status.HTTP_204_NO_CONTENT:
        return SpotifyPlayerRead(active=False)
    if response.status_code == status.HTTP_403_FORBIDDEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Spotify playback controls require an eligible Spotify account",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spotify player unavailable",
        )

    payload = response.json()
    device = payload.get("device") if isinstance(payload.get("device"), dict) else {}
    progress_ms = payload.get("progress_ms")
    shuffle_state = payload.get("shuffle_state")
    repeat_state = payload.get("repeat_state")
    item = payload.get("item")
    return SpotifyPlayerRead(
        active=bool(payload.get("is_playing") or item),
        is_playing=bool(payload.get("is_playing")),
        progress_ms=progress_ms if isinstance(progress_ms, int) else None,
        shuffle_state=shuffle_state if isinstance(shuffle_state, bool) else None,
        repeat_state=repeat_state if isinstance(repeat_state, str) else None,
        device_name=device.get("name") if isinstance(device.get("name"), str) else None,
        device_type=device.get("type") if isinstance(device.get("type"), str) else None,
        volume_percent=(
            device.get("volume_percent")
            if isinstance(device.get("volume_percent"), int)
            else None
        ),
        track=_track_from_payload(item if isinstance(item, dict) else None),
    )


@router.post("/player", status_code=status.HTTP_204_NO_CONTENT)
def spotify_player_control(
    payload: SpotifyControlRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    connection = _connection_or_404(request, db)
    routes = {
        "play": ("PUT", "/me/player/play"),
        "pause": ("PUT", "/me/player/pause"),
        "next": ("POST", "/me/player/next"),
        "previous": ("POST", "/me/player/previous"),
    }
    method, path = routes[payload.action]
    try:
        response = spotify_request(
            db,
            request.app.state.settings,
            connection,
            method=method,
            path=path,
        )
    except SpotifyIntegrationError as exc:
        raise _service_error(exc) from exc
    if response.status_code == status.HTTP_403_FORBIDDEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Spotify playback controls require Spotify Premium",
        )
    if response.status_code not in {status.HTTP_200_OK, status.HTTP_204_NO_CONTENT}:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spotify control failed",
        )
