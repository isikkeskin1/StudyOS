from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.tutor import _course, _embedding_config, _provider_config, _raise_tutor_error
from app.core.database import get_db
from app.models.review_session import ReviewSession
from app.models.tutor_practice import TutorPracticeItem
from app.schemas.review_session import (
    ReviewAnswerRead,
    ReviewAnswerRequest,
    ReviewSessionCreateRequest,
    ReviewSessionRead,
)
from app.schemas.tutor import TutorPracticeEvaluateRequest
from app.services.review_session import create_review, read_review, review_status, skip_review
from app.services.tutor_embeddings import TutorEmbeddingFailure, TutorEmbeddingUnavailable
from app.services.tutor_practice import TutorPracticeUnavailable
from app.services.tutor_practice_evaluation import (
    TutorPracticeEvaluationError,
    evaluate_practice_item,
)
from app.services.tutor_provider import TutorProviderFailure, TutorProviderUnavailable

router = APIRouter(prefix="/courses/{course_id}/review-sessions", tags=["review scheduling"])
_ERRORS = (
    TutorPracticeUnavailable,
    TutorPracticeEvaluationError,
    TutorProviderFailure,
    TutorProviderUnavailable,
    TutorEmbeddingFailure,
    TutorEmbeddingUnavailable,
)


def _review(db: Session, course_id: str, review_id: str):
    row = db.get(ReviewSession, review_id)
    if row is None or row.course_id != course_id:
        raise HTTPException(status_code=404, detail="Review session not found")
    return row


@router.post("", response_model=ReviewSessionRead, status_code=201)
def start_review(
    course_id: str,
    payload: ReviewSessionCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ReviewSessionRead:
    course = _course(db, course_id)
    try:
        row = create_review(
            db,
            course,
            payload,
            provider_config=_provider_config(request),
            embedding_config=_embedding_config(request),
        )
        return read_review(db, course, row)
    except _ERRORS as exc:
        db.rollback()
        _raise_tutor_error(exc)


@router.get("", response_model=list[ReviewSessionRead])
def list_reviews(course_id: str, db: Annotated[Session, Depends(get_db)]):
    course = _course(db, course_id)
    rows = db.scalars(
        select(ReviewSession)
        .where(ReviewSession.course_id == course_id)
        .order_by(ReviewSession.created_at.desc())
    ).all()
    return [read_review(db, course, row) for row in rows]


@router.get("/{review_id}", response_model=ReviewSessionRead)
def get_review(course_id: str, review_id: str, db: Annotated[Session, Depends(get_db)]):
    return read_review(db, _course(db, course_id), _review(db, course_id, review_id))


@router.post("/{review_id}/answer", response_model=ReviewAnswerRead)
def answer_review(
    course_id: str,
    review_id: str,
    payload: ReviewAnswerRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    course = _course(db, course_id)
    row = _review(db, course_id, review_id)
    try:
        if review_status(db, row) != "active":
            raise TutorPracticeUnavailable("Only an active review accepts an answer")
        evaluation = evaluate_practice_item(
            db,
            db.get(TutorPracticeItem, row.practice_id),
            TutorPracticeEvaluateRequest(**payload.model_dump(), generate_next=False),
            provider_config=_provider_config(request),
            embedding_config=_embedding_config(request),
        )
        row.active_key = None
        db.commit()
        return ReviewAnswerRead(evaluation=evaluation, review=read_review(db, course, row))
    except _ERRORS as exc:
        db.rollback()
        _raise_tutor_error(exc)


@router.post("/{review_id}/skip", response_model=ReviewSessionRead)
def skip(course_id: str, review_id: str, db: Annotated[Session, Depends(get_db)]):
    course = _course(db, course_id)
    row = _review(db, course_id, review_id)
    try:
        skip_review(db, row)
        return read_review(db, course, row)
    except _ERRORS as exc:
        _raise_tutor_error(exc)
