from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    original_filename: str
    content_type: str | None
    extension: str
    size_bytes: int
    sha256: str
    status: str
    created_at: datetime
