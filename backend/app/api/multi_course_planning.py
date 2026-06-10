from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.multi_course_planning import MultiCoursePlanRead, MultiCoursePlanRequest
from app.services.emergency_planning import EmergencyPlanUnavailableError
from app.services.multi_course_planning import (
    MultiCourseCourseNotFoundError,
    MultiCoursePlanUnavailableError,
    build_multi_course_plan,
)

router = APIRouter(tags=["planning"])


@router.post("/multi-course-plan", response_model=MultiCoursePlanRead)
def multi_course_plan(
    payload: MultiCoursePlanRequest,
    db: Annotated[Session, Depends(get_db)],
) -> MultiCoursePlanRead:
    try:
        return build_multi_course_plan(db, payload)
    except MultiCourseCourseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (MultiCoursePlanUnavailableError, EmergencyPlanUnavailableError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
