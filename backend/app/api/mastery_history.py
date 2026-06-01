from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.mastery_history import (
    CourseMasteryHistoryRead,
    MasteryHistoryPointRead,
    TopicMasteryTrendRead,
)
from app.services.mastery_history import get_course_mastery_history

router = APIRouter(prefix="/courses", tags=["mastery analytics"])


@router.get("/{course_id}/mastery/history", response_model=CourseMasteryHistoryRead)
def get_mastery_history(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CourseMasteryHistoryRead:
    if db.get(Course, course_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    history = get_course_mastery_history(db, course_id)
    return CourseMasteryHistoryRead(
        course_id=course_id,
        generated_at=history.generated_at,
        tracked_topic_count=history.tracked_topic_count,
        total_history_points=history.total_history_points,
        improving_topic_count=history.improving_topic_count,
        stable_topic_count=history.stable_topic_count,
        declining_topic_count=history.declining_topic_count,
        topics=[
            TopicMasteryTrendRead(
                topic_id=item.topic_id,
                topic_name=item.topic_name,
                point_count=len(item.points),
                raw_mastery=item.raw_mastery,
                effective_mastery=item.effective_mastery,
                confidence=item.confidence,
                effective_confidence=item.effective_confidence,
                forgetting_risk=item.forgetting_risk,
                change_from_first=item.change_from_first,
                weekly_change=item.weekly_change,
                trend_direction=item.trend_direction,
                trend_confidence=item.trend_confidence,
                recent_accuracy=item.recent_accuracy,
                recent_response_count=item.recent_response_count,
                observed_gain_per_evidence=item.observed_gain_per_evidence,
                first_evidence_at=item.first_evidence_at,
                latest_evidence_at=item.latest_evidence_at,
                evidence_span_days=item.evidence_span_days,
                points=[
                    MasteryHistoryPointRead(
                        response_id=point.response_id,
                        recorded_at=point.recorded_at,
                        mastery=point.mastery,
                        confidence=point.confidence,
                        evidence_weight=point.evidence_weight,
                        response_count=point.response_count,
                        source_score=point.source_score,
                        topic_relevance=point.topic_relevance,
                        evidence_increment=point.evidence_increment,
                    )
                    for point in item.points
                ],
            )
            for item in history.topics
        ],
    )
