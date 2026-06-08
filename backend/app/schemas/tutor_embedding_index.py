from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TutorEmbeddingIndexSyncRequest(BaseModel):
    force: bool = False
    batch_size: int | None = Field(default=None, ge=1, le=256)


class TutorEmbeddingIndexRead(BaseModel):
    course_id: str
    status: Literal["disabled", "empty", "stale", "ready"]
    provider_name: str | None
    model_name: str | None
    total_chunks: int
    indexed_chunks: int
    missing_chunks: int
    stale_chunks: int
    orphaned_embeddings: int
    coverage: float
    dimensions: int | None
    embedded_now: int = 0
    reused_chunks: int = 0
    deleted_orphans: int = 0
