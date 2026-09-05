from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import (
    DiagnosticQuestion,
    DiagnosticResponse,
    DiagnosticSession,
    TopicMastery,
)
from app.models.exam_intelligence import ExamQuestionTopic
from app.models.mastery_history import MasterySnapshot
from app.services.retention import retention_snapshot


@dataclass(frozen=True)
class MasteryHistoryPoint:
    response_id: str
    recorded_at: datetime
    mastery: float
    confidence: float
    evidence_weight: float
    response_count: int
    source_score: float
    topic_relevance: float
    evidence_increment: float


@dataclass(frozen=True)
class TopicMasteryTrend:
    topic_id: str
    topic_name: str
    raw_mastery: float
    effective_mastery: float
    confidence: float
    effective_confidence: float
    forgetting_risk: str
    change_from_first: float
    weekly_change: float | None
    trend_direction: str
    trend_confidence: str
    recent_accuracy: float
    recent_response_count: int
    observed_gain_per_evidence: float | None
    first_evidence_at: datetime
    latest_evidence_at: datetime
    evidence_span_days: float
    points: list[MasteryHistoryPoint]


@dataclass(frozen=True)
class CourseMasteryHistory:
    generated_at: datetime
    tracked_topic_count: int
    total_history_points: int
    improving_topic_count: int
    stable_topic_count: int
    declining_topic_count: int
    topics: list[TopicMasteryTrend]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _evidence_increment(
    relevance_score: float,
    difficulty: float,
    response_confidence: float,
) -> float:
    return (
        max(0.05, relevance_score)
        * (0.8 + 0.4 * difficulty)
        * (0.75 + 0.25 * response_confidence)
    )


def rebuild_course_mastery_history(db: Session, course_id: str) -> list[MasterySnapshot]:
    session_ids = list(
        db.scalars(
            select(DiagnosticSession.id).where(DiagnosticSession.course_id == course_id)
        ).all()
    )
    db.execute(delete(MasterySnapshot).where(MasterySnapshot.course_id == course_id))
    if not session_ids:
        db.commit()
        return []

    diagnostic_questions = list(
        db.scalars(
            select(DiagnosticQuestion).where(DiagnosticQuestion.session_id.in_(session_ids))
        ).all()
    )
    question_by_id = {question.id: question for question in diagnostic_questions}
    exam_question_ids = list({question.exam_question_id for question in diagnostic_questions})
    mappings_by_question: dict[str, list[ExamQuestionTopic]] = defaultdict(list)
    if exam_question_ids:
        mappings = db.scalars(
            select(ExamQuestionTopic).where(
                ExamQuestionTopic.question_id.in_(exam_question_ids)
            )
        ).all()
        for mapping in mappings:
            mappings_by_question[mapping.question_id].append(mapping)

    responses = list(
        db.scalars(
            select(DiagnosticResponse)
            .where(DiagnosticResponse.session_id.in_(session_ids))
            .order_by(DiagnosticResponse.created_at, DiagnosticResponse.id)
        ).all()
    )
    state: dict[str, dict[str, float]] = defaultdict(
        lambda: {"weight": 0.0, "success": 0.0, "count": 0.0}
    )
    snapshots: list[MasterySnapshot] = []

    for response in responses:
        diagnostic_question = question_by_id.get(response.diagnostic_question_id)
        if diagnostic_question is None:
            continue
        response_time = _as_utc(response.created_at)
        for mapping in mappings_by_question.get(diagnostic_question.exam_question_id, []):
            increment = _evidence_increment(
                mapping.relevance_score,
                diagnostic_question.difficulty,
                response.confidence,
            )
            row = state[mapping.topic_id]
            row["weight"] += increment
            row["success"] += increment * response.score
            row["count"] += 1.0
            alpha = 2.0 + row["success"]
            beta = 2.0 + row["weight"] - row["success"]
            mastery = alpha / (alpha + beta)
            confidence = 1.0 - math.exp(-row["weight"] / 3.0)

            snapshot = MasterySnapshot(
                id=str(uuid4()),
                course_id=course_id,
                topic_id=mapping.topic_id,
                response_id=response.id,
                mastery=mastery,
                confidence=confidence,
                evidence_weight=row["weight"],
                response_count=int(row["count"]),
                source_score=response.score,
                topic_relevance=mapping.relevance_score,
                evidence_increment=increment,
                recorded_at=response_time,
            )
            db.add(snapshot)
            snapshots.append(snapshot)

    db.commit()
    return snapshots


def _ensure_history(db: Session, course_id: str) -> None:
    snapshot_count = db.scalar(
        select(func.count(MasterySnapshot.id)).where(MasterySnapshot.course_id == course_id)
    )
    if snapshot_count:
        return

    session_ids = list(
        db.scalars(
            select(DiagnosticSession.id).where(DiagnosticSession.course_id == course_id)
        ).all()
    )
    if not session_ids:
        return
    response_count = db.scalar(
        select(func.count(DiagnosticResponse.id)).where(
            DiagnosticResponse.session_id.in_(session_ids)
        )
    )
    if response_count:
        rebuild_course_mastery_history(db, course_id)


def _trend_direction(points: list[MasterySnapshot]) -> str:
    if len(points) < 2:
        return "insufficient_data"
    change = points[-1].mastery - points[0].mastery
    if change >= 0.03:
        return "improving"
    if change <= -0.03:
        return "declining"
    return "stable"


def _trend_confidence(point_count: int, span_days: float) -> str:
    if point_count >= 6 and span_days >= 7.0:
        return "high"
    if point_count >= 3 and span_days >= 1.0:
        return "medium"
    return "low"


def _recent_accuracy(points: list[MasterySnapshot]) -> tuple[float, int]:
    recent = points[-5:]
    total_weight = sum(max(point.evidence_increment, 0.001) for point in recent)
    accuracy = sum(
        point.source_score * max(point.evidence_increment, 0.001) for point in recent
    ) / total_weight
    return round(accuracy, 4), len(recent)


def _weekly_change(points: list[MasterySnapshot], span_days: float) -> float | None:
    if len(points) < 2 or span_days < 1.0:
        return None
    return round((points[-1].mastery - points[0].mastery) / span_days * 7.0, 4)


def _observed_gain_per_evidence(points: list[MasterySnapshot]) -> float | None:
    if len(points) < 2:
        return None
    evidence_delta = points[-1].evidence_weight - points[0].evidence_weight
    if evidence_delta <= 0:
        return None
    return round((points[-1].mastery - points[0].mastery) / evidence_delta, 4)


def get_course_mastery_history(db: Session, course_id: str) -> CourseMasteryHistory:
    _ensure_history(db, course_id)
    generated_at = datetime.now(UTC)
    topics = {
        topic.id: topic
        for topic in db.scalars(
            select(CourseTopic).where(CourseTopic.course_id == course_id)
        ).all()
    }
    current_mastery = {
        item.topic_id: item
        for item in db.scalars(
            select(TopicMastery).where(TopicMastery.course_id == course_id)
        ).all()
    }
    snapshots = list(
        db.scalars(
            select(MasterySnapshot)
            .where(MasterySnapshot.course_id == course_id)
            .order_by(MasterySnapshot.recorded_at, MasterySnapshot.id)
        ).all()
    )
    grouped: dict[str, list[MasterySnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[snapshot.topic_id].append(snapshot)

    trends: list[TopicMasteryTrend] = []
    for topic_id, points in grouped.items():
        topic = topics.get(topic_id)
        mastery = current_mastery.get(topic_id)
        if topic is None or mastery is None or not points:
            continue

        first_time = _as_utc(points[0].recorded_at)
        latest_time = _as_utc(points[-1].recorded_at)
        span_days = max(0.0, (latest_time - first_time).total_seconds() / 86400.0)
        retained = retention_snapshot(mastery, as_of=generated_at)
        recent_accuracy, recent_count = _recent_accuracy(points)
        change = points[-1].mastery - points[0].mastery
        point_reads = [
            MasteryHistoryPoint(
                response_id=point.response_id,
                recorded_at=_as_utc(point.recorded_at),
                mastery=round(point.mastery, 4),
                confidence=round(point.confidence, 4),
                evidence_weight=round(point.evidence_weight, 4),
                response_count=point.response_count,
                source_score=round(point.source_score, 4),
                topic_relevance=round(point.topic_relevance, 4),
                evidence_increment=round(point.evidence_increment, 4),
            )
            for point in points
        ]
        trends.append(
            TopicMasteryTrend(
                topic_id=topic_id,
                topic_name=topic.name,
                raw_mastery=round(mastery.mastery, 4),
                effective_mastery=retained.effective_mastery,
                confidence=round(mastery.confidence, 4),
                effective_confidence=retained.effective_confidence,
                forgetting_risk=retained.forgetting_risk,
                change_from_first=round(change, 4),
                weekly_change=_weekly_change(points, span_days),
                trend_direction=_trend_direction(points),
                trend_confidence=_trend_confidence(len(points), span_days),
                recent_accuracy=recent_accuracy,
                recent_response_count=recent_count,
                observed_gain_per_evidence=_observed_gain_per_evidence(points),
                first_evidence_at=first_time,
                latest_evidence_at=latest_time,
                evidence_span_days=round(span_days, 2),
                points=point_reads,
            )
        )

    trends.sort(
        key=lambda item: (item.trend_confidence, len(item.points), item.confidence),
        reverse=True,
    )
    return CourseMasteryHistory(
        generated_at=generated_at,
        tracked_topic_count=len(trends),
        total_history_points=sum(len(item.points) for item in trends),
        improving_topic_count=sum(item.trend_direction == "improving" for item in trends),
        stable_topic_count=sum(item.trend_direction == "stable" for item in trends),
        declining_topic_count=sum(item.trend_direction == "declining" for item in trends),
        topics=trends,
    )
