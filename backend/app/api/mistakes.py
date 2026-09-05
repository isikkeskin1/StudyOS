from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.schemas.mistakes import (
    MistakeCategoryStatRead,
    MistakeIntelligenceRead,
    TopicMistakePatternRead,
)
from app.services.mistake_intelligence import summarize_course_mistakes

router = APIRouter(prefix="/courses", tags=["mistake intelligence"])


@router.get("/{course_id}/mistakes", response_model=MistakeIntelligenceRead)
def get_course_mistake_intelligence(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> MistakeIntelligenceRead:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    summary = summarize_course_mistakes(db, course_id)
    return MistakeIntelligenceRead(
        course_id=course_id,
        response_count=summary.response_count,
        responses_with_mistakes=summary.responses_with_mistakes,
        lost_score_total=summary.lost_score_total,
        classified_loss_total=summary.classified_loss_total,
        classification_coverage=summary.classification_coverage,
        categories=[
            MistakeCategoryStatRead(
                category=item.category,
                occurrences=item.occurrences,
                weighted_lost_score=item.weighted_lost_score,
                share_of_classified_loss=item.share_of_classified_loss,
            )
            for item in summary.categories
        ],
        topics=[
            TopicMistakePatternRead(
                topic_id=item.topic_id,
                topic_name=item.topic_name,
                mistake_burden=item.mistake_burden,
                dominant_categories=item.dominant_categories,
            )
            for item in summary.topics
        ],
    )
