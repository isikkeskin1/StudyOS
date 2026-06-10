from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.exam_intelligence import ExamAnalysis, ExamTopicStat
from app.schemas.emergency_planning import EmergencyPlanRead, EmergencyPlanRequest
from app.services.emergency_planning import EmergencyPlanUnavailableError, build_emergency_plan
from app.services.exam_analysis import (
    CourseTopicsRequiredError,
    NoExamDocumentsError,
    analyze_exams,
)

router = APIRouter(prefix="/courses", tags=["planning"])


def _get_course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def _exam_analysis_is_stale(db: Session, course_id: str) -> bool:
    stats = list(
        db.scalars(select(ExamTopicStat).where(ExamTopicStat.course_id == course_id)).all()
    )
    if not stats:
        return False
    current_topic_ids = set(
        db.scalars(select(CourseTopic.id).where(CourseTopic.course_id == course_id)).all()
    )
    return any(stat.topic_id not in current_topic_ids for stat in stats)


@router.post("/{course_id}/emergency-plan", response_model=EmergencyPlanRead)
def generate_emergency_plan(
    course_id: str,
    payload: EmergencyPlanRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyPlanRead:
    course = _get_course(db, course_id)

    exam_analysis = db.get(ExamAnalysis, course_id)
    if exam_analysis is None or _exam_analysis_is_stale(db, course_id):
        try:
            analyze_exams(db, course_id)
        except NoExamDocumentsError:
            pass
        except CourseTopicsRequiredError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        return build_emergency_plan(db, course, payload)
    except EmergencyPlanUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
