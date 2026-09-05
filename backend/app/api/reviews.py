from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.reviews import ReviewQueueRead, ReviewTopicRead
from app.services.calibration import get_course_calibration
from app.services.retention import build_review_queue

router = APIRouter(prefix="/courses", tags=["review scheduling"])


@router.get("/{course_id}/reviews", response_model=ReviewQueueRead)
def get_review_queue(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ReviewQueueRead:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    calibration = get_course_calibration(db, course_id)
    half_lives = {
        item.topic_id: item.retention_half_life_days
        for item in calibration.topics
        if item.retention_half_life_days is not None
    }
    retention_confidences = {
        item.topic_id: item.retention_confidence for item in calibration.topics
    }
    queue = build_review_queue(
        db,
        course,
        retention_half_lives=half_lives,
        retention_confidences=retention_confidences,
    )
    return ReviewQueueRead(
        course_id=course_id,
        generated_at=queue.generated_at,
        exam_date=queue.exam_date,
        days_until_exam=queue.days_until_exam,
        tracked_topic_count=queue.tracked_topic_count,
        due_topic_count=queue.due_topic_count,
        total_recommended_minutes=queue.total_recommended_minutes,
        items=[
            ReviewTopicRead(
                topic_id=item.topic_id,
                topic_name=item.topic_name,
                raw_mastery=item.raw_mastery,
                effective_mastery=item.effective_mastery,
                raw_confidence=item.raw_confidence,
                effective_confidence=item.effective_confidence,
                last_evidence_at=item.last_evidence_at,
                days_since_evidence=item.days_since_evidence,
                half_life_days=item.half_life_days,
                forgetting_loss=item.forgetting_loss,
                forgetting_risk=item.forgetting_risk,
                exam_weight=item.exam_weight,
                review_priority=item.review_priority,
                due_for_review=item.due_for_review,
                recommended_minutes=item.recommended_minutes,
                retention_calibration_confidence=item.retention_calibration_confidence,
                retention_model=item.retention_model,
                reason=item.reason,
            )
            for item in queue.items
        ],
    )
