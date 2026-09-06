from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.search import GlobalSearchRead, SearchKind
from app.services.search import global_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=GlobalSearchRead)
def search(
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    course_id: str | None = None,
    kind: list[SearchKind] | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> GlobalSearchRead:
    return global_search(
        db,
        q,
        course_id=course_id,
        kinds=set(kind) if kind else None,
        limit=limit,
    )
