from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.models.exam_intelligence import ExamAnalysis
from app.schemas.grade_modeling import GradeForecastRead, GradeForecastRequest
from app.services.exam_analysis import (
    CourseTopicsRequiredError,
    NoExamDocumentsError,
    analyze_exams,
)
from app.services.grade_modeling import (
    GradeForecastUnavailableError,
    build_grade_forecast,
)
from app.services.planning import StudyPlanUnavailableError

router = APIRouter(prefix="/courses", tags=["grade modeling"])


@router.post("/{course_id}/grade-forecast", response_model=GradeForecastRead)
def generate_grade_forecast(
    course_id: str,
    payload: GradeForecastRequest,
    db: Annotated[Session, Depends(get_db)],
) -> GradeForecastRead:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    if db.get(ExamAnalysis, course_id) is None:
        try:
            analyze_exams(db, course_id)
        except NoExamDocumentsError:
            pass
        except CourseTopicsRequiredError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        return build_grade_forecast(db, course, payload)
    except (GradeForecastUnavailableError, StudyPlanUnavailableError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
