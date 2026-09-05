from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.emergency_schedule import EmergencyStudySchedule
from app.models.exam_intelligence import ExamAnalysis, ExamTopicStat
from app.schemas.emergency_schedule import (
    EmergencyScheduleCompleteBlockRequest,
    EmergencyScheduleCreateRequest,
    EmergencyScheduleRead,
    EmergencyScheduleRescheduleRequest,
    EmergencyScheduleSkipBlockRequest,
)
from app.services.emergency_planning import EmergencyPlanUnavailableError
from app.services.emergency_schedule import (
    EmergencyScheduleConflictError,
    EmergencyScheduleNotFoundError,
    complete_schedule_block,
    create_emergency_schedule,
    manually_reschedule,
    read_emergency_schedule,
    skip_schedule_block,
    start_schedule_block,
)
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


def _ensure_exam_analysis(db: Session, course_id: str) -> None:
    analysis = db.get(ExamAnalysis, course_id)
    if analysis is not None and not _exam_analysis_is_stale(db, course_id):
        return
    try:
        analyze_exams(db, course_id)
    except NoExamDocumentsError:
        pass
    except CourseTopicsRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _translate_schedule_error(exc: RuntimeError) -> HTTPException:
    if isinstance(exc, EmergencyScheduleNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/{course_id}/emergency-schedules",
    response_model=EmergencyScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    course_id: str,
    payload: EmergencyScheduleCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyScheduleRead:
    course = _get_course(db, course_id)
    _ensure_exam_analysis(db, course_id)
    try:
        schedule = create_emergency_schedule(db, course, payload)
        return read_emergency_schedule(db, course_id, schedule.id)
    except (EmergencyPlanUnavailableError, EmergencyScheduleConflictError) as exc:
        raise _translate_schedule_error(exc) from exc


@router.get(
    "/{course_id}/emergency-schedules",
    response_model=list[EmergencyScheduleRead],
)
def list_schedules(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[EmergencyScheduleRead]:
    _get_course(db, course_id)
    schedule_ids = list(
        db.scalars(
            select(EmergencyStudySchedule.id)
            .where(EmergencyStudySchedule.course_id == course_id)
            .order_by(EmergencyStudySchedule.created_at.desc())
        ).all()
    )
    return [read_emergency_schedule(db, course_id, schedule_id) for schedule_id in schedule_ids]


@router.get(
    "/{course_id}/emergency-schedules/{schedule_id}",
    response_model=EmergencyScheduleRead,
)
def get_schedule(
    course_id: str,
    schedule_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyScheduleRead:
    _get_course(db, course_id)
    try:
        return read_emergency_schedule(db, course_id, schedule_id)
    except EmergencyScheduleNotFoundError as exc:
        raise _translate_schedule_error(exc) from exc


@router.post(
    "/{course_id}/emergency-schedules/{schedule_id}/blocks/{block_id}/start",
    response_model=EmergencyScheduleRead,
)
def start_block(
    course_id: str,
    schedule_id: str,
    block_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyScheduleRead:
    _get_course(db, course_id)
    try:
        schedule = start_schedule_block(db, course_id, schedule_id, block_id)
        return read_emergency_schedule(db, course_id, schedule.id)
    except (EmergencyScheduleNotFoundError, EmergencyScheduleConflictError) as exc:
        raise _translate_schedule_error(exc) from exc


@router.post(
    "/{course_id}/emergency-schedules/{schedule_id}/blocks/{block_id}/complete",
    response_model=EmergencyScheduleRead,
)
def complete_block(
    course_id: str,
    schedule_id: str,
    block_id: str,
    payload: EmergencyScheduleCompleteBlockRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyScheduleRead:
    course = _get_course(db, course_id)
    try:
        schedule = complete_schedule_block(db, course, schedule_id, block_id, payload)
        return read_emergency_schedule(db, course_id, schedule.id)
    except (
        EmergencyPlanUnavailableError,
        EmergencyScheduleNotFoundError,
        EmergencyScheduleConflictError,
    ) as exc:
        raise _translate_schedule_error(exc) from exc


@router.post(
    "/{course_id}/emergency-schedules/{schedule_id}/blocks/{block_id}/skip",
    response_model=EmergencyScheduleRead,
)
def skip_block(
    course_id: str,
    schedule_id: str,
    block_id: str,
    payload: EmergencyScheduleSkipBlockRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyScheduleRead:
    course = _get_course(db, course_id)
    try:
        schedule = skip_schedule_block(db, course, schedule_id, block_id, payload)
        return read_emergency_schedule(db, course_id, schedule.id)
    except (
        EmergencyPlanUnavailableError,
        EmergencyScheduleNotFoundError,
        EmergencyScheduleConflictError,
    ) as exc:
        raise _translate_schedule_error(exc) from exc


@router.post(
    "/{course_id}/emergency-schedules/{schedule_id}/reschedule",
    response_model=EmergencyScheduleRead,
)
def reschedule(
    course_id: str,
    schedule_id: str,
    payload: EmergencyScheduleRescheduleRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EmergencyScheduleRead:
    course = _get_course(db, course_id)
    _ensure_exam_analysis(db, course_id)
    try:
        schedule = manually_reschedule(db, course, schedule_id, payload)
        return read_emergency_schedule(db, course_id, schedule.id)
    except (
        EmergencyPlanUnavailableError,
        EmergencyScheduleNotFoundError,
        EmergencyScheduleConflictError,
    ) as exc:
        raise _translate_schedule_error(exc) from exc
