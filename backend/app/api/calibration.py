from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.calibration import CourseCalibrationRead, TopicCalibrationRead
from app.services.calibration import get_course_calibration

router = APIRouter(prefix="/courses", tags=["learning calibration"])


@router.get("/{course_id}/calibration", response_model=CourseCalibrationRead)
def get_calibration(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CourseCalibrationRead:
    if db.get(Course, course_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    calibration = get_course_calibration(db, course_id)
    return CourseCalibrationRead(
        course_id=course_id,
        generated_at=calibration.generated_at,
        topic_count=calibration.topic_count,
        history_point_count=calibration.history_point_count,
        calibrated_learning_topic_count=calibration.calibrated_learning_topic_count,
        calibrated_retention_topic_count=calibration.calibrated_retention_topic_count,
        topics=[
            TopicCalibrationRead(
                topic_id=item.topic_id,
                topic_name=item.topic_name,
                history_point_count=item.history_point_count,
                evidence_span_days=item.evidence_span_days,
                learning_rate_multiplier=item.learning_rate_multiplier,
                learning_scale_hours=item.learning_scale_hours,
                learning_confidence=item.learning_confidence,
                observed_gain_per_evidence=item.observed_gain_per_evidence,
                heuristic_half_life_days=item.heuristic_half_life_days,
                retention_half_life_days=item.retention_half_life_days,
                retention_confidence=item.retention_confidence,
                retention_observation_count=item.retention_observation_count,
                calibration_source=item.calibration_source,
            )
            for item in calibration.topics
        ],
        notes=calibration.notes,
    )
