from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.semester_dashboard import SemesterDashboardRead
from app.services.semester_dashboard import build_semester_dashboard
from app.services.semester_queue import SemesterQueueNotFoundError

router = APIRouter(tags=["semester"])


@router.get("/semester/dashboard", response_model=SemesterDashboardRead)
def semester_dashboard(
    db: Annotated[Session, Depends(get_db)], queue_id: str | None = None
) -> SemesterDashboardRead:
    try:
        return build_semester_dashboard(db, queue_id)
    except SemesterQueueNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
