from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.diagnostics import TopicMastery
from app.models.tutor_practice import (
    TutorPracticeAttempt,
    TutorPracticeGradeArtifact,
    TutorPracticeItem,
    TutorPracticeMistake,
)
from app.schemas.tutor import (
    TutorPracticeCreateRequest,
    TutorPracticeEvaluateRequest,
    TutorPracticeEvaluationRead,
    TutorPracticeGradingRead,
    TutorPracticeMasteryRead,
    TutorPracticeMistakeRead,
    TutorPracticeRubricCriterionRead,
)
from app.services.diagnostics import recompute_course_mastery
from app.services.mastery_history import rebuild_course_mastery_history
from app.services.practice_grading import PracticeGradeResult, grade_practice_answer
from app.services.tutor_embeddings import (
    TutorEmbeddingConfig,
    TutorEmbeddingFailure,
    TutorEmbeddingProvider,
    TutorEmbeddingUnavailable,
)
from app.services.tutor_practice import TutorPracticeUnavailable, create_practice_item
from app.services.tutor_provider import (
    TutorProviderConfig,
    TutorProviderFailure,
    TutorProviderUnavailable,
)

_DIFFICULTIES = ["easy", "medium", "hard"]
_HINT_FACTORS = {0: 1.0, 1: 0.82, 2: 0.64, 3: 0.48}
_DIFFICULTY_FACTORS = {"easy": 0.80, "medium": 1.0, "hard": 1.20}


class TutorPracticeEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True)
class _NextPlan:
    difficulty: str
    target_topic: str | None
    strategy: str
    reason: str


def _mastery_read(db: Session, item: TutorPracticeItem) -> TutorPracticeMasteryRead | None:
    if item.topic_id is None:
        return None
    mastery = db.scalar(
        select(TopicMastery).where(
            TopicMastery.course_id == item.course_id,
            TopicMastery.topic_id == item.topic_id,
        )
    )
    if mastery is None:
        return None
    return TutorPracticeMasteryRead(
        topic_id=item.topic_id,
        topic_name=item.topic_name,
        mastery=round(mastery.mastery, 4),
        confidence=round(mastery.confidence, 4),
        evidence_weight=round(mastery.evidence_weight, 4),
        response_count=mastery.response_count,
    )


def _mastery_weight(item: TutorPracticeItem, result: PracticeGradeResult) -> float:
    hint_factor = _HINT_FACTORS.get(item.hints_revealed, 0.40)
    difficulty_factor = _DIFFICULTY_FACTORS[item.difficulty]
    source_factor = 0.90 if item.generation_mode == "novel-grounded-v1" else 1.0
    weight = (
        difficulty_factor
        * hint_factor
        * source_factor
        * result.grader_confidence
        * result.evidence_coverage
    )
    return round(min(1.20, max(0.05, weight)), 4)


def _reference_confidence(item: TutorPracticeItem) -> float:
    return 0.90 if item.generation_mode == "past-exam-reuse-v1" else 0.75


def _shift_difficulty(current: str, delta: int) -> str:
    index = _DIFFICULTIES.index(current)
    return _DIFFICULTIES[min(len(_DIFFICULTIES) - 1, max(0, index + delta))]


def _next_plan(
    item: TutorPracticeItem,
    score: float,
    mastery_after: TutorPracticeMasteryRead | None,
) -> _NextPlan:
    mastery = mastery_after.mastery if mastery_after is not None else 0.5
    hints = item.hints_revealed

    if score < 0.55 or hints >= 2:
        return _NextPlan(
            difficulty=_shift_difficulty(item.difficulty, -1),
            target_topic=item.topic_name,
            strategy="reinforce",
            reason=(
                "Weak or hint-dependent performance; reinforce the same topic with a lower "
                "or equal difficulty."
            ),
        )

    if score >= 0.85 and hints == 0:
        next_difficulty = _shift_difficulty(item.difficulty, 1)
        if mastery >= 0.72:
            return _NextPlan(
                difficulty=next_difficulty,
                target_topic=None,
                strategy="reoptimize",
                reason=(
                    "Strong unassisted performance raised mastery enough to re-optimize across "
                    "course weaknesses."
                ),
            )
        return _NextPlan(
            difficulty=next_difficulty,
            target_topic=item.topic_name,
            strategy="increase_difficulty",
            reason="Strong unassisted performance; stay on the topic and increase difficulty.",
        )

    if score >= 0.70 and hints <= 1 and mastery >= 0.75:
        return _NextPlan(
            difficulty=item.difficulty,
            target_topic=None,
            strategy="reoptimize",
            reason="Current topic is sufficiently strong; re-optimize toward the next weakness.",
        )

    return _NextPlan(
        difficulty=item.difficulty,
        target_topic=item.topic_name,
        strategy="maintain",
        reason="Performance is mixed; keep the same topic and difficulty for another check.",
    )


def _next_provider(item: TutorPracticeItem) -> str:
    if item.generation_provider.startswith("openai-practice:"):
        return "openai"
    return "local"


def _criteria_payload(result: PracticeGradeResult) -> list[dict]:
    return [
        {
            "criterion": criterion.criterion,
            "max_points": criterion.max_points,
            "awarded_points": criterion.awarded_points,
            "rationale": criterion.rationale,
            "mistake_category": criterion.mistake_category,
            "mistake_severity": criterion.mistake_severity,
        }
        for criterion in result.criteria
    ]


def _store_attempt(
    db: Session,
    item: TutorPracticeItem,
    payload: TutorPracticeEvaluateRequest,
    result: PracticeGradeResult,
    mastery_weight: float,
) -> TutorPracticeAttempt:
    attempt = TutorPracticeAttempt(
        id=str(uuid4()),
        practice_id=item.id,
        course_id=item.course_id,
        student_answer=payload.student_answer,
        score=result.score,
        grader_name=result.grader_name,
        grader_confidence=result.grader_confidence,
        evidence_coverage=result.evidence_coverage,
        mastery_weight=mastery_weight,
        hints_used=item.hints_revealed,
        duration_seconds=payload.duration_seconds,
        feedback=result.feedback,
    )
    db.add(attempt)
    db.flush()
    for mistake in result.mistakes:
        db.add(
            TutorPracticeMistake(
                id=str(uuid4()),
                attempt_id=attempt.id,
                category=mistake.category,
                severity=mistake.severity,
                source="automatic",
                note=mistake.note,
            )
        )
    db.add(
        TutorPracticeGradeArtifact(
            id=str(uuid4()),
            attempt_id=attempt.id,
            grading_mode=result.grading_mode,
            grading_provider=result.grader_name,
            criteria=_criteria_payload(result),
            total_awarded=result.total_awarded,
            total_possible=result.total_possible,
        )
    )
    db.commit()
    db.refresh(attempt)
    return attempt


def _grading_read(result: PracticeGradeResult) -> TutorPracticeGradingRead:
    return TutorPracticeGradingRead(
        grading_mode=result.grading_mode,
        grading_provider=result.grader_name,
        total_awarded=result.total_awarded,
        total_possible=result.total_possible,
        criteria=[
            TutorPracticeRubricCriterionRead(
                criterion=criterion.criterion,
                max_points=criterion.max_points,
                awarded_points=criterion.awarded_points,
                rationale=criterion.rationale,
                mistake_category=criterion.mistake_category,
                mistake_severity=criterion.mistake_severity,
            )
            for criterion in result.criteria
        ],
    )


def evaluate_practice_item(
    db: Session,
    item: TutorPracticeItem,
    payload: TutorPracticeEvaluateRequest,
    *,
    provider_config: TutorProviderConfig | None = None,
    embedding_config: TutorEmbeddingConfig | None = None,
    embedding_provider: TutorEmbeddingProvider | None = None,
) -> TutorPracticeEvaluationRead:
    if item.topic_id is None:
        raise TutorPracticeEvaluationError(
            "Practice topic is no longer available, so this item cannot update mastery"
        )
    if item.solution_revealed:
        raise TutorPracticeEvaluationError(
            "This practice solution has already been revealed and is no longer valid "
            "mastery evidence"
        )
    existing = db.scalar(
        select(TutorPracticeAttempt).where(TutorPracticeAttempt.practice_id == item.id)
    )
    if existing is not None:
        raise TutorPracticeEvaluationError("This practice item has already been evaluated")

    resolved_provider_config = provider_config or TutorProviderConfig()
    mastery_before = _mastery_read(db, item)
    result = grade_practice_answer(
        requested_provider=payload.grading_provider,
        config=resolved_provider_config,
        question=item.question,
        reference_solution=item.solution,
        student_answer=payload.student_answer,
        marks=item.marks,
        reference_confidence=_reference_confidence(item),
    )
    mastery_weight = _mastery_weight(item, result)
    attempt = _store_attempt(db, item, payload, result, mastery_weight)

    recompute_course_mastery(db, item.course_id)
    rebuild_course_mastery_history(db, item.course_id)
    mastery_after = _mastery_read(db, item)
    plan = _next_plan(item, result.score, mastery_after)

    next_practice = None
    next_reason = plan.reason
    if payload.generate_next:
        try:
            next_practice = create_practice_item(
                db,
                item.course_id,
                TutorPracticeCreateRequest(
                    target_topic=plan.target_topic,
                    difficulty=plan.difficulty,
                    provider=_next_provider(item),
                    retrieval_mode="auto",
                ),
                provider_config=resolved_provider_config,
                embedding_config=embedding_config or TutorEmbeddingConfig(),
                embedding_provider=embedding_provider,
            )
        except (
            TutorPracticeUnavailable,
            TutorProviderUnavailable,
            TutorProviderFailure,
            TutorEmbeddingUnavailable,
            TutorEmbeddingFailure,
        ) as exc:
            next_reason = f"{plan.reason} Next practice could not be generated: {exc}"

    mistakes = [
        TutorPracticeMistakeRead(
            category=mistake.category,
            severity=mistake.severity,
            source="automatic",
            note=mistake.note,
        )
        for mistake in result.mistakes
    ]
    return TutorPracticeEvaluationRead(
        attempt_id=attempt.id,
        practice_id=item.id,
        score=result.score,
        grader_name=attempt.grader_name,
        grader_confidence=result.grader_confidence,
        evidence_coverage=result.evidence_coverage,
        mastery_weight=mastery_weight,
        hints_used=item.hints_revealed,
        duration_seconds=payload.duration_seconds,
        feedback=result.feedback,
        mistakes=mistakes,
        grading=_grading_read(result),
        mastery_before=mastery_before,
        mastery_after=mastery_after,
        next_strategy=plan.strategy,
        next_reason=next_reason,
        next_practice=next_practice,
    )
