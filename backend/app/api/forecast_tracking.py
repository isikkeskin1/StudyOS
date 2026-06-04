from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.models.exam_intelligence import ExamAnalysis
from app.schemas.forecast_tracking import (
    ForecastCalibrationRead,
    ForecastOutcomeCreate,
    ForecastSnapshotCreate,
    ForecastSnapshotRead,
)
from app.schemas.forecast_validation import ForecastValidationRead
from app.services.exam_analysis import (
    CourseTopicsRequiredError,
    NoExamDocumentsError,
    analyze_exams,
)
from app.services.forecast_tracking import (
    ForecastTrackingError,
    build_forecast_calibration,
    create_forecast_snapshot,
    list_forecast_snapshots,
    record_forecast_outcome,
)
from app.services.forecast_validation import build_forecast_validation
from app.services.grade_modeling import GradeForecastUnavailableError
from app.services.planning import StudyPlanUnavailableError

router = APIRouter(prefix="/courses", tags=["forecast tracking"])


def _course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def _ensure_exam_analysis(db: Session, course_id: str) -> None:
    if db.get(ExamAnalysis, course_id) is not None:
        return
    try:
        analyze_exams(db, course_id)
    except NoExamDocumentsError:
        pass
    except CourseTopicsRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{course_id}/forecast-snapshots",
    response_model=ForecastSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def save_forecast_snapshot(
    course_id: str,
    payload: ForecastSnapshotCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ForecastSnapshotRead:
    course = _course(db, course_id)
    _ensure_exam_analysis(db, course_id)
    try:
        return create_forecast_snapshot(db, course, payload)
    except (GradeForecastUnavailableError, StudyPlanUnavailableError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{course_id}/forecast-snapshots", response_model=list[ForecastSnapshotRead])
def read_forecast_snapshots(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[ForecastSnapshotRead]:
    _course(db, course_id)
    return list_forecast_snapshots(db, course_id)


@router.post(
    "/{course_id}/forecast-snapshots/{snapshot_id}/outcome",
    response_model=ForecastSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def save_forecast_outcome(
    course_id: str,
    snapshot_id: str,
    payload: ForecastOutcomeCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ForecastSnapshotRead:
    course = _course(db, course_id)
    try:
        return record_forecast_outcome(db, course, snapshot_id, payload)
    except ForecastTrackingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{course_id}/forecast-calibration", response_model=ForecastCalibrationRead)
def read_forecast_calibration(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ForecastCalibrationRead:
    _course(db, course_id)
    return build_forecast_calibration(db, course_id)


@router.get("/{course_id}/forecast-validation", response_model=ForecastValidationRead)
def read_forecast_validation(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ForecastValidationRead:
    _course(db, course_id)
    return build_forecast_validation(db, course_id)
