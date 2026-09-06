from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PushConfigRead(BaseModel):
    enabled: bool
    public_key: str | None


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=4096)
    auth: str = Field(min_length=1, max_length=4096)


class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(min_length=8, max_length=8192)
    keys: PushKeys


class PushSubscriptionRead(BaseModel):
    id: str
    endpoint: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class PushDispatchRead(BaseModel):
    attempted: int
    sent: int
    disabled: int


class CalendarSubscriptionCreate(BaseModel):
    start_at: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    break_minutes: int = Field(default=5, ge=0, le=60)


class CalendarSubscriptionRead(BaseModel):
    id: str
    queue_id: str
    timezone: str
    start_at: datetime
    break_minutes: int
    active: bool
    created_at: datetime


class CalendarSubscriptionCreated(CalendarSubscriptionRead):
    feed_path: str
