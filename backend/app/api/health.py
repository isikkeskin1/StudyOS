from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "service": "StudyOS API",
        "version": request.app.version,
        "environment": request.app.state.settings.environment,
    }


@router.get("/health/live")
def liveness(request: Request) -> dict[str, str]:
    return {
        "status": "alive",
        "service": request.app.title,
        "version": request.app.version,
    }


@router.get("/health/ready")
def readiness(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    try:
        db.execute(text("select 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready",
        ) from exc

    return {
        "status": "ready",
        "service": request.app.title,
        "version": request.app.version,
        "database": "ready",
    }
