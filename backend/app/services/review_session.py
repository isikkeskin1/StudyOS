from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.review_session import ReviewSession
from app.models.tutor_practice import TutorPracticeAttempt, TutorPracticeItem
from app.schemas.review_session import ReviewSessionCreateRequest, ReviewSessionRead
from app.schemas.tutor import TutorPracticeCreateRequest
from app.services.calibration import get_course_calibration
from app.services.retention import build_review_queue
from app.services.tutor_practice import (
    TutorPracticeUnavailable,
    _practice_read,
    create_practice_item,
)


def review_queue(db: Session, course: Course):
    calibration = get_course_calibration(db, course.id)
    return build_review_queue(
        db,
        course,
        retention_half_lives={
            t.topic_id: t.retention_half_life_days
            for t in calibration.topics
            if t.retention_half_life_days is not None
        },
        retention_confidences={t.topic_id: t.retention_confidence for t in calibration.topics},
    )


def _attempt(db: Session, review: ReviewSession):
    return db.scalar(
        select(TutorPracticeAttempt).where(TutorPracticeAttempt.practice_id == review.practice_id)
    )


def review_status(db: Session, review: ReviewSession) -> str:
    if _attempt(db, review) is not None:
        return "completed"
    if review.skipped_at is not None:
        return "skipped"
    item = db.get(TutorPracticeItem, review.practice_id)
    if item is None or item.topic_id != review.topic_id:
        return "unavailable"
    return "solution_revealed" if item.solution_revealed else "active"


def read_review(db: Session, course: Course, review: ReviewSession) -> ReviewSessionRead:
    item = db.get(TutorPracticeItem, review.practice_id)
    attempt = _attempt(db, review)
    current = next(
        (t for t in review_queue(db, course).items if t.topic_id == review.topic_id), None
    )
    return ReviewSessionRead(
        id=review.id,
        course_id=course.id,
        topic_id=review.topic_id,
        status=review_status(db, review),
        practice=_practice_read(db, item) if item else None,
        selection_snapshot=review.selection_snapshot,
        due_now=current.due_for_review if current else None,
        current_review_priority=current.review_priority if current else None,
        attempt_id=attempt.id if attempt else None,
        score=attempt.score if attempt else None,
        created_at=review.created_at,
    )


def create_review(db: Session, course: Course, payload: ReviewSessionCreateRequest, **configs):
    # Release reservations consumed through the ordinary tutor endpoints too.
    active = list(
        db.scalars(
            select(ReviewSession).where(
                ReviewSession.course_id == course.id, ReviewSession.active_key.is_not(None)
            )
        ).all()
    )
    for existing in active:
        if review_status(db, existing) != "active":
            existing.active_key = None
    db.flush()
    if payload.topic_id:
        existing = next(
            (r for r in active if r.active_key and r.topic_id == payload.topic_id), None
        )
    else:
        existing = next((r for r in active if r.active_key), None)
    if existing:
        return existing
    due = [t for t in review_queue(db, course).items if t.due_for_review]
    if payload.topic_id:
        due = [t for t in due if t.topic_id == payload.topic_id]
    if not due:
        raise TutorPracticeUnavailable("No due review topic matches this request")
    topic = due[0]
    key = f"{course.id}:{topic.topic_id}"
    try:
        practice = create_practice_item(
            db,
            course.id,
            TutorPracticeCreateRequest(
                target_topic=topic.topic_name,
                provider=payload.provider,
                difficulty=payload.difficulty,
            ),
            commit=False,
            **configs,
        )
        item = db.get(TutorPracticeItem, practice.id)
        if item.topic_id != topic.topic_id:
            raise TutorPracticeUnavailable("Generated practice does not match the due topic")
        review = ReviewSession(
            course_id=course.id,
            topic_id=topic.topic_id,
            practice_id=practice.id,
            active_key=key,
            selection_snapshot={
                "topic_name": topic.topic_name,
                "reason": topic.reason,
                "review_priority": topic.review_priority,
                "effective_mastery": topic.effective_mastery,
                "last_evidence_at": topic.last_evidence_at.isoformat(),
                "recommended_minutes": topic.recommended_minutes,
            },
        )
        db.add(review)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(ReviewSession).where(ReviewSession.active_key == key))
        if existing is None:
            raise
        return existing
    return review


def skip_review(db: Session, review: ReviewSession):
    if review_status(db, review) == "skipped":
        return
    if review_status(db, review) != "active":
        raise TutorPracticeUnavailable("Only an active review can be skipped")
    review.skipped_at = datetime.now(UTC)
    review.active_key = None
    db.commit()
