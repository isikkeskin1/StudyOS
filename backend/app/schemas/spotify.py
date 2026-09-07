from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SpotifyStatusRead(BaseModel):
    configured: bool
    connected: bool
    display_name: str | None = None
    spotify_user_id: str | None = None
    product: str | None = None
    premium: bool = False


class SpotifyAuthorizeRead(BaseModel):
    authorize_url: str


class SpotifyTrackRead(BaseModel):
    name: str
    artists: list[str]
    album: str | None = None
    image_url: str | None = None
    duration_ms: int | None = None
    uri: str | None = None
    external_url: str | None = None


class SpotifyPlayerRead(BaseModel):
    connected: bool = True
    active: bool = False
    is_playing: bool = False
    progress_ms: int | None = None
    shuffle_state: bool | None = None
    repeat_state: str | None = None
    device_name: str | None = None
    device_type: str | None = None
    volume_percent: int | None = None
    track: SpotifyTrackRead | None = None


class SpotifyControlRequest(BaseModel):
    action: Literal["play", "pause", "next", "previous"]
