from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import DiagnosticResponse, DiagnosticSession, TopicMastery
from app.models.mastery_history import MasterySnapshot
from app.services.mastery_history import rebuild_course_mastery_history

_GENERIC_LEARNING_SCALE_HOURS = 2.8
_NOMINAL_GAIN_PER_EVIDENCE = 0.08
_MEMORY_FLOOR = 0.20
_MIN_RETENTION_GAP_DAYS = 2.0


@dataclass(frozen=True)
class TopicCalibration:
    topic_id: str
    topic_name: str
    history_point_count: int
    evidence_span_days: float
    learning_rate_multiplier: float
    learning_scale_hours: float
    learning_confidence: str
    observed_gain_per_evidence: float | None
    heuristic_half_life_days: float | None
    retention_half_life_days: float | None
    retention_confidence: str
    retention_observation_count: int
    calibration_source: str


@dataclass(frozen=True)
class CourseCalibration:
    generated_at: datetime
    topic_count: int
    history_point_count: int
    calibrated_learning_topic_count: int
    calibrated_retention_topic_count: int
    topics: list[TopicCalibration]
    notes: list[str]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _heuristic_half_life_days(mastery: TopicMastery) -> float:
    return round(
        14.0
        + 18.0 * mastery.confidence
        + 8.0 * mastery.mastery
        + min(12.0, mastery.evidence_weight * 2.0),
        2,
    )


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


def _gain_per_evidence(points: list[MasterySnapshot]) -> float | None:
    if len(points) < 2:
        return None
    evidence_delta = points[-1].evidence_weight - points[0].evidence_weight
    if evidence_delta <= 0:
        return None
    return (points[-1].mastery - points[0].mastery) / evidence_delta


def _learning_confidence(
    point_count: int,
    evidence_delta: float,
    span_days: float,
) -> tuple[str, float]:
    if point_count >= 6 and evidence_delta >= 4.0 and span_days >= 1.0:
        return "high", 0.70
    if point_count >= 3 and evidence_delta >= 1.5:
        return "medium", 0.40
    if point_count >= 2:
        return "low", 0.18
    return "low", 0.0


def _learning_multiplier(observed_gain: float | None, confidence_weight: float) -> float:
    if observed_gain is None or confidence_weight <= 0:
        return 1.0
    trend_signal = max(
        -1.0,
        min(1.0, observed_gain / _NOMINAL_GAIN_PER_EVIDENCE),
    )
    raw_multiplier = 1.0 + 0.35 * trend_signal
    return 1.0 + confidence_weight * (raw_multiplier - 1.0)


def _retention_observations(points: list[MasterySnapshot]) -> list[float]:
    estimates: list[float] = []
    for previous, current in zip(points, points[1:], strict=False):
        previous_at = _as_utc(previous.recorded_at)
        current_at = _as_utc(current.recorded_at)
        gap_days = (current_at - previous_at).total_seconds() / 86400.0
        if gap_days < _MIN_RETENTION_GAP_DAYS:
            continue
        if current.source_score >= previous.source_score - 0.02:
            continue

        previous_signal = previous.source_score - _MEMORY_FLOOR
        current_signal = current.source_score - _MEMORY_FLOOR
        if previous_signal <= 0.10 or current_signal <= 0.01:
            continue

        ratio = max(0.15, min(0.99, current_signal / previous_signal))
        half_life = gap_days * math.log(0.5) / math.log(ratio)
        estimates.append(max(3.0, min(120.0, half_life)))
    return estimates


def _retention_confidence(
    observation_count: int,
    span_days: float,
) -> tuple[str, float]:
    if observation_count >= 4 and span_days >= 21.0:
        return "high", 0.70
    if observation_count >= 2 and span_days >= 7.0:
        return "medium", 0.40
    if observation_count >= 1:
        return "low", 0.15
    return "low", 0.0


def get_course_calibration(db: Session, course_id: str) -> CourseCalibration:
    _ensure_history(db, course_id)
    generated_at = datetime.now(UTC)
    topics = list(
        db.scalars(
            select(CourseTopic)
            .where(CourseTopic.course_id == course_id)
            .order_by(CourseTopic.importance_score.desc())
        ).all()
    )
    mastery_by_topic = {
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

    rows: list[TopicCalibration] = []
    for topic in topics:
        points = grouped.get(topic.id, [])
        point_count = len(points)
        if points:
            first_at = _as_utc(points[0].recorded_at)
            latest_at = _as_utc(points[-1].recorded_at)
            span_days = max(0.0, (latest_at - first_at).total_seconds() / 86400.0)
            evidence_delta = max(0.0, points[-1].evidence_weight - points[0].evidence_weight)
        else:
            span_days = 0.0
            evidence_delta = 0.0

        observed_gain = _gain_per_evidence(points)
        learning_label, learning_weight = _learning_confidence(
            point_count,
            evidence_delta,
            span_days,
        )
        learning_multiplier = _learning_multiplier(observed_gain, learning_weight)
        learning_scale = _GENERIC_LEARNING_SCALE_HOURS / learning_multiplier

        mastery = mastery_by_topic.get(topic.id)
        heuristic_half_life = (
            _heuristic_half_life_days(mastery) if mastery is not None else None
        )
        retention_observations = _retention_observations(points)
        retention_label, retention_weight = _retention_confidence(
            len(retention_observations),
            span_days,
        )
        if heuristic_half_life is None:
            calibrated_half_life = None
        elif retention_observations:
            observed_half_life = median(retention_observations)
            calibrated_half_life = (
                heuristic_half_life * (1.0 - retention_weight)
                + observed_half_life * retention_weight
            )
        else:
            calibrated_half_life = heuristic_half_life

        if learning_label == "high" or retention_label == "high":
            source = "personalized"
        elif point_count >= 2 or retention_observations:
            source = "blended"
        else:
            source = "heuristic"

        rows.append(
            TopicCalibration(
                topic_id=topic.id,
                topic_name=topic.name,
                history_point_count=point_count,
                evidence_span_days=round(span_days, 2),
                learning_rate_multiplier=round(learning_multiplier, 4),
                learning_scale_hours=round(learning_scale, 4),
                learning_confidence=learning_label,
                observed_gain_per_evidence=(
                    round(observed_gain, 4) if observed_gain is not None else None
                ),
                heuristic_half_life_days=heuristic_half_life,
                retention_half_life_days=(
                    round(calibrated_half_life, 2)
                    if calibrated_half_life is not None
                    else None
                ),
                retention_confidence=retention_label,
                retention_observation_count=len(retention_observations),
                calibration_source=source,
            )
        )

    return CourseCalibration(
        generated_at=generated_at,
        topic_count=len(rows),
        history_point_count=len(snapshots),
        calibrated_learning_topic_count=sum(
            item.history_point_count >= 2 for item in rows
        ),
        calibrated_retention_topic_count=sum(
            item.retention_observation_count > 0 for item in rows
        ),
        topics=rows,
        notes=[
            (
                "Learning multipliers are confidence-shrunk adjustments to the generic "
                "study-gain curve; diagnostic response time is not treated as study time."
            ),
            (
                "Retention calibration uses only time-separated performance drops and is "
                "shrunk toward the heuristic half-life when evidence is sparse."
            ),
            "Low-confidence calibration should be treated as directional, not predictive truth.",
        ],
    )


def calibration_by_topic(db: Session, course_id: str) -> dict[str, TopicCalibration]:
    calibration = get_course_calibration(db, course_id)
    return {item.topic_id: item for item in calibration.topics}
