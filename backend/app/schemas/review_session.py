from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.tutor import TutorPracticeEvaluationRead, TutorPracticeRead, TutorProvider


class ReviewSessionCreateRequest(BaseModel):
    topic_id: str | None = None
    provider: TutorProvider = "auto"
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class ReviewAnswerRequest(BaseModel):
    student_answer: str = Field(min_length=1, max_length=20000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    grading_provider: TutorProvider = "auto"


class ReviewSessionRead(BaseModel):
    id: str
    course_id: str
    topic_id: str
    status: Literal["active", "completed", "skipped", "solution_revealed", "unavailable"]
    practice: TutorPracticeRead | None
    selection_snapshot: dict
    due_now: bool | None
    current_review_priority: float | None
    attempt_id: str | None
    score: float | None
    created_at: datetime


class ReviewAnswerRead(BaseModel):
    evaluation: TutorPracticeEvaluationRead
    review: ReviewSessionRead
