from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.analytics import AnalyticsDashboardRead
from app.services.analytics import (
    AnalyticsCourseNotFoundError,
    AnalyticsInputError,
    build_analytics_dashboard,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsDashboardRead)
def get_analytics(
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    course_id: str | None = None,
    timezone: str = "UTC",
) -> AnalyticsDashboardRead:
    try:
        return build_analytics_dashboard(
            db,
            days=days,
            course_id=course_id,
            timezone=timezone,
        )
    except AnalyticsCourseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnalyticsInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
