from __future__ import annotations

from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "StudyOS API",
    }


@router.get("/health/live")
def liveness(request: Request) -> dict[str, str]:
    return {
        "status": "alive",
        "service": request.app.title,
        "version": request.app.version,
        "environment": request.app.state.settings.environment,
    }


def _storage_ready(request: Request) -> bool:
    data_dir = request.app.state.settings.data_dir
    try:
        with NamedTemporaryFile(dir=data_dir, prefix=".studyos-ready-", delete=True):
            pass
    except OSError:
        return False
    return True


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

    if not _storage_ready(request):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload storage is not ready",
        )

    return {
        "status": "ready",
        "service": request.app.title,
        "version": request.app.version,
        "environment": request.app.state.settings.environment,
        "database": "ready",
        "storage": "ready",
    }
