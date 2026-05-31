from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import TopicMastery
from app.models.exam_intelligence import ExamTopicStat

_MEMORY_FLOOR = 0.20
_HIGH_FORGETTING_LOSS = 0.10
_MEDIUM_FORGETTING_LOSS = 0.05


@dataclass(frozen=True)
class RetentionSnapshot:
    raw_mastery: float
    effective_mastery: float
    raw_confidence: float
    effective_confidence: float
    evidence_weight: float
    last_evidence_at: datetime
    days_since_evidence: float
    half_life_days: float
    forgetting_loss: float
    forgetting_risk: str


@dataclass(frozen=True)
class ReviewItem:
    topic_id: str
    topic_name: str
    raw_mastery: float
    effective_mastery: float
    raw_confidence: float
    effective_confidence: float
    last_evidence_at: datetime
    days_since_evidence: float
    half_life_days: float
    forgetting_loss: float
    forgetting_risk: str
    exam_weight: float
    review_priority: float
    due_for_review: bool
    recommended_minutes: int
    retention_calibration_confidence: str
    retention_model: str
    reason: str


@dataclass(frozen=True)
class ReviewQueue:
    generated_at: datetime
    exam_date: date | None
    days_until_exam: int | None
    tracked_topic_count: int
    due_topic_count: int
    total_recommended_minutes: int
    items: list[ReviewItem]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _half_life_days(mastery: TopicMastery) -> float:
    return round(
        14.0
        + 18.0 * mastery.confidence
        + 8.0 * mastery.mastery
        + min(12.0, mastery.evidence_weight * 2.0),
        2,
    )


def retention_snapshot(
    mastery: TopicMastery,
    *,
    as_of: datetime | None = None,
    half_life_days: float | None = None,
) -> RetentionSnapshot:
    now = _as_utc(as_of or datetime.now(UTC))
    last_evidence = _as_utc(mastery.updated_at)
    age_days = max(0.0, (now - last_evidence).total_seconds() / 86400.0)
    half_life = round(
        max(1.0, half_life_days) if half_life_days is not None else _half_life_days(mastery),
        2,
    )
    retention = math.pow(0.5, age_days / half_life)
    effective_mastery = _MEMORY_FLOOR + (mastery.mastery - _MEMORY_FLOOR) * retention
    confidence_half_life = max(7.0, half_life * 0.60)
    effective_confidence = mastery.confidence * math.pow(
        0.5,
        age_days / confidence_half_life,
    )
    forgetting_loss = max(0.0, mastery.mastery - effective_mastery)

    if forgetting_loss >= _HIGH_FORGETTING_LOSS or (
        age_days >= 7.0 and effective_confidence < 0.20
    ):
        risk = "high"
    elif forgetting_loss >= _MEDIUM_FORGETTING_LOSS or effective_confidence < 0.35:
        risk = "medium"
    else:
        risk = "low"

    return RetentionSnapshot(
        raw_mastery=round(mastery.mastery, 4),
        effective_mastery=round(max(0.0, min(1.0, effective_mastery)), 4),
        raw_confidence=round(mastery.confidence, 4),
        effective_confidence=round(max(0.0, min(1.0, effective_confidence)), 4),
        evidence_weight=round(mastery.evidence_weight, 4),
        last_evidence_at=last_evidence,
        days_since_evidence=round(age_days, 2),
        half_life_days=half_life,
        forgetting_loss=round(forgetting_loss, 4),
        forgetting_risk=risk,
    )


def _days_until_exam(course: Course, generated_at: datetime) -> int | None:
    if course.exam_date is None:
        return None
    return (course.exam_date - generated_at.date()).days


def _review_interval_days(
    snapshot: RetentionSnapshot,
    *,
    exam_weight: float,
    topic_count: int,
    days_until_exam: int | None,
) -> float:
    interval = snapshot.half_life_days * (0.22 + 0.18 * snapshot.raw_mastery)
    relative_exam_weight = min(2.0, max(0.0, exam_weight * max(topic_count, 1)))
    interval /= 0.85 + 0.25 * relative_exam_weight

    if days_until_exam is not None and 0 <= days_until_exam <= 14:
        exam_factor = 0.55 + 0.45 * (days_until_exam / 14.0)
        interval *= exam_factor
    return max(2.0, interval)


def _review_reason(
    snapshot: RetentionSnapshot,
    exam_weight: float,
    topic_count: int,
    due_for_review: bool,
    retention_model: str,
) -> str:
    parts = [f"{snapshot.days_since_evidence:.0f} days since the latest evidence"]
    if snapshot.forgetting_loss >= 0.01:
        parts.append(f"estimated mastery decay of {snapshot.forgetting_loss * 100:.0f}%")
    relative_weight = exam_weight * max(topic_count, 1)
    if relative_weight >= 1.25:
        parts.append("above-average exam weight")
    if retention_model != "heuristic":
        parts.append("retention curve blended with longitudinal evidence")
    if not due_for_review:
        parts.append("not yet due under the current retention model")
    return "; ".join(parts) + "."


def _recommended_minutes(
    snapshot: RetentionSnapshot,
    exam_weight: float,
    topic_count: int,
) -> int:
    relative_weight = min(2.0, exam_weight * max(topic_count, 1))
    raw_minutes = (
        10.0
        + 25.0 * (1.0 - snapshot.effective_mastery)
        + 20.0 * snapshot.forgetting_loss
        + 5.0 * relative_weight
    )
    rounded = int(5 * round(raw_minutes / 5.0))
    return max(10, min(45, rounded))


def build_review_queue(
    db: Session,
    course: Course,
    *,
    as_of: datetime | None = None,
    retention_half_lives: dict[str, float] | None = None,
    retention_confidences: dict[str, str] | None = None,
) -> ReviewQueue:
    generated_at = _as_utc(as_of or datetime.now(UTC))
    half_lives = retention_half_lives or {}
    confidence_by_topic = retention_confidences or {}
    topics = list(
        db.scalars(
            select(CourseTopic).where(CourseTopic.course_id == course.id)
        ).all()
    )
    topic_by_id = {topic.id: topic for topic in topics}
    mastery_rows = list(
        db.scalars(
            select(TopicMastery).where(TopicMastery.course_id == course.id)
        ).all()
    )
    exam_stats = {
        stat.topic_id: stat
        for stat in db.scalars(
            select(ExamTopicStat).where(ExamTopicStat.course_id == course.id)
        ).all()
    }

    total_importance = sum(topic.importance_score for topic in topics) or 1.0
    days_until_exam = _days_until_exam(course, generated_at)
    items: list[ReviewItem] = []

    for mastery in mastery_rows:
        topic = topic_by_id.get(mastery.topic_id)
        if topic is None:
            continue
        stat = exam_stats.get(topic.id)
        exam_weight = (
            stat.exam_weight
            if stat is not None
            else topic.importance_score / total_importance
        )
        calibration_confidence = confidence_by_topic.get(topic.id, "low")
        calibrated_half_life = half_lives.get(topic.id)
        snapshot = retention_snapshot(
            mastery,
            as_of=generated_at,
            half_life_days=calibrated_half_life,
        )
        retention_model = (
            "calibrated"
            if calibrated_half_life is not None and calibration_confidence in {"medium", "high"}
            else "heuristic"
        )
        interval_days = _review_interval_days(
            snapshot,
            exam_weight=exam_weight,
            topic_count=len(topics),
            days_until_exam=days_until_exam,
        )
        due = (
            snapshot.days_since_evidence >= interval_days
            or snapshot.forgetting_loss >= _HIGH_FORGETTING_LOSS
        )
        if (
            days_until_exam is not None
            and 0 <= days_until_exam <= 7
            and snapshot.days_since_evidence >= 2.0
            and snapshot.effective_mastery < 0.85
        ):
            due = True

        urgency = 1.0
        if days_until_exam is not None and 0 <= days_until_exam <= 14:
            urgency += (14.0 - days_until_exam) / 14.0
        priority = (
            exam_weight
            * (0.35 + 0.65 * (1.0 - snapshot.effective_mastery))
            * (1.0 + 2.5 * snapshot.forgetting_loss)
            * urgency
        )

        items.append(
            ReviewItem(
                topic_id=topic.id,
                topic_name=topic.name,
                raw_mastery=snapshot.raw_mastery,
                effective_mastery=snapshot.effective_mastery,
                raw_confidence=snapshot.raw_confidence,
                effective_confidence=snapshot.effective_confidence,
                last_evidence_at=snapshot.last_evidence_at,
                days_since_evidence=snapshot.days_since_evidence,
                half_life_days=snapshot.half_life_days,
                forgetting_loss=snapshot.forgetting_loss,
                forgetting_risk=snapshot.forgetting_risk,
                exam_weight=round(exam_weight, 4),
                review_priority=round(priority, 4),
                due_for_review=due,
                recommended_minutes=_recommended_minutes(
                    snapshot,
                    exam_weight,
                    len(topics),
                ),
                retention_calibration_confidence=calibration_confidence,
                retention_model=retention_model,
                reason=_review_reason(
                    snapshot,
                    exam_weight,
                    len(topics),
                    due,
                    retention_model,
                ),
            )
        )

    items.sort(
        key=lambda item: (item.due_for_review, item.review_priority),
        reverse=True,
    )
    due_items = [item for item in items if item.due_for_review]
    return ReviewQueue(
        generated_at=generated_at,
        exam_date=course.exam_date,
        days_until_exam=days_until_exam,
        tracked_topic_count=len(items),
        due_topic_count=len(due_items),
        total_recommended_minutes=sum(item.recommended_minutes for item in due_items),
        items=items,
    )
