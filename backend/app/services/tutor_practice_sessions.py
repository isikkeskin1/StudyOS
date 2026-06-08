from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tutor_practice import (
    TutorPracticeAttempt,
    TutorPracticeItem,
    TutorPracticeMistake,
    TutorPracticeSession,
    TutorPracticeSessionItem,
)
from app.schemas.tutor import (
    TutorPracticeCreateRequest,
    TutorPracticeRead,
    TutorPracticeSessionContextRead,
    TutorPracticeSessionCreateRequest,
    TutorPracticeSessionMistakeRead,
    TutorPracticeSessionRead,
    TutorPracticeSessionTopicRead,
)
from app.services.tutor_embeddings import TutorEmbeddingConfig, TutorEmbeddingProvider
from app.services.tutor_practice import (
    _practice_read as practice_item_read,
)
from app.services.tutor_practice import create_practice_item, get_practice_item
from app.services.tutor_provider import TutorProviderConfig

_RECENT_WINDOW = 5
_DIFFICULTIES = ["easy", "medium", "hard"]


class TutorPracticeSessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionAdaptation:
    strategy: str
    reason: str
    next_practice: TutorPracticeRead | None
    context: TutorPracticeSessionContextRead


@dataclass(frozen=True)
class _AttemptRow:
    sequence: int
    topic: str
    difficulty: str
    score: float
    hints: int
    attempt_id: str


def _shift_difficulty(current: str, delta: int) -> str:
    index = _DIFFICULTIES.index(current)
    return _DIFFICULTIES[min(len(_DIFFICULTIES) - 1, max(0, index + delta))]


def _session_rows(db: Session, session_id: str) -> list[_AttemptRow]:
    rows = db.execute(
        select(TutorPracticeSessionItem, TutorPracticeItem, TutorPracticeAttempt)
        .join(TutorPracticeItem, TutorPracticeItem.id == TutorPracticeSessionItem.practice_id)
        .join(TutorPracticeAttempt, TutorPracticeAttempt.practice_id == TutorPracticeItem.id)
        .where(TutorPracticeSessionItem.session_id == session_id)
        .order_by(TutorPracticeSessionItem.sequence)
    ).all()
    return [
        _AttemptRow(
            sequence=link.sequence,
            topic=item.topic_name,
            difficulty=item.difficulty,
            score=attempt.score,
            hints=attempt.hints_used,
            attempt_id=attempt.id,
        )
        for link, item, attempt in rows
    ]


def _mistakes_by_attempt(
    db: Session,
    attempt_ids: list[str],
) -> dict[str, list[TutorPracticeMistake]]:
    if not attempt_ids:
        return {}
    mistakes = list(
        db.scalars(
            select(TutorPracticeMistake).where(
                TutorPracticeMistake.attempt_id.in_(attempt_ids)
            )
        ).all()
    )
    grouped: dict[str, list[TutorPracticeMistake]] = {}
    for mistake in mistakes:
        grouped.setdefault(mistake.attempt_id, []).append(mistake)
    return grouped


def _dominant_mistakes(
    rows: list[_AttemptRow],
    mistakes: dict[str, list[TutorPracticeMistake]],
) -> list[TutorPracticeSessionMistakeRead]:
    counts: dict[str, int] = {}
    severity: dict[str, float] = {}
    for row in rows:
        for mistake in mistakes.get(row.attempt_id, []):
            counts[mistake.category] = counts.get(mistake.category, 0) + 1
            severity[mistake.category] = severity.get(mistake.category, 0.0) + mistake.severity
    ranked = sorted(
        counts,
        key=lambda category: (counts[category], severity[category], category),
        reverse=True,
    )
    return [
        TutorPracticeSessionMistakeRead(
            category=category,
            occurrences=counts[category],
            severity_total=round(severity[category], 4),
            average_severity=round(severity[category] / counts[category], 4),
        )
        for category in ranked[:5]
    ]


def _topic_summaries(
    rows: list[_AttemptRow],
    mistakes: dict[str, list[TutorPracticeMistake]],
) -> list[TutorPracticeSessionTopicRead]:
    grouped: dict[str, list[_AttemptRow]] = {}
    for row in rows:
        grouped.setdefault(row.topic, []).append(row)
    summaries: list[TutorPracticeSessionTopicRead] = []
    for topic, topic_rows in grouped.items():
        mistake_count = sum(len(mistakes.get(row.attempt_id, [])) for row in topic_rows)
        summaries.append(
            TutorPracticeSessionTopicRead(
                topic=topic,
                attempt_count=len(topic_rows),
                average_score=round(sum(row.score for row in topic_rows) / len(topic_rows), 4),
                average_hints=round(sum(row.hints for row in topic_rows) / len(topic_rows), 4),
                mistake_count=mistake_count,
            )
        )
    return sorted(
        summaries,
        key=lambda item: (item.average_score, -item.mistake_count, item.topic),
    )


def _focus_for_category(
    rows: list[_AttemptRow],
    mistakes: dict[str, list[TutorPracticeMistake]],
    category: str,
) -> str | None:
    burden: dict[str, float] = {}
    for row in rows:
        for mistake in mistakes.get(row.attempt_id, []):
            if mistake.category == category:
                burden[row.topic] = burden.get(row.topic, 0.0) + mistake.severity
    if not burden:
        return None
    return max(burden, key=lambda topic: (burden[topic], topic))


def get_practice_session(
    db: Session,
    course_id: str,
    session_id: str,
) -> TutorPracticeSession | None:
    session = db.get(TutorPracticeSession, session_id)
    if session is None or session.course_id != course_id:
        return None
    return session


def _links(db: Session, session_id: str) -> list[TutorPracticeSessionItem]:
    return list(
        db.scalars(
            select(TutorPracticeSessionItem)
            .where(TutorPracticeSessionItem.session_id == session_id)
            .order_by(TutorPracticeSessionItem.sequence)
        ).all()
    )


def validate_practice_session_item(
    db: Session,
    course_id: str,
    session_id: str,
    item: TutorPracticeItem,
) -> TutorPracticeSession:
    session = get_practice_session(db, course_id, session_id)
    if session is None:
        raise TutorPracticeSessionError("Practice session not found")
    link = db.scalar(
        select(TutorPracticeSessionItem).where(
            TutorPracticeSessionItem.session_id == session.id,
            TutorPracticeSessionItem.practice_id == item.id,
        )
    )
    if link is None:
        raise TutorPracticeSessionError("Practice item does not belong to this practice session")
    if session.status != "active":
        raise TutorPracticeSessionError("Practice session is already completed")
    return session


def _session_context(
    db: Session,
    session: TutorPracticeSession,
    *,
    focus_reason: str | None = None,
) -> TutorPracticeSessionContextRead:
    rows = _session_rows(db, session.id)
    recent = rows[-_RECENT_WINDOW:]
    mistakes = _mistakes_by_attempt(db, [row.attempt_id for row in recent])
    dominant = _dominant_mistakes(recent, mistakes)
    dominant_category = dominant[0].category if dominant else None
    focus_topic = (
        _focus_for_category(recent, mistakes, dominant_category)
        if dominant_category is not None
        else (recent[-1].topic if recent else None)
    )
    return TutorPracticeSessionContextRead(
        session_id=session.id,
        recent_attempt_count=len(recent),
        recent_average_score=(
            round(sum(row.score for row in recent) / len(recent), 4) if recent else None
        ),
        recent_average_hints=(
            round(sum(row.hints for row in recent) / len(recent), 4) if recent else None
        ),
        dominant_mistake=dominant_category,
        dominant_mistake_count=dominant[0].occurrences if dominant else 0,
        focus_topic=focus_topic,
        focus_reason=focus_reason,
    )


def practice_session_read(
    db: Session,
    session: TutorPracticeSession,
) -> TutorPracticeSessionRead:
    links = _links(db, session.id)
    rows = _session_rows(db, session.id)
    mistakes = _mistakes_by_attempt(db, [row.attempt_id for row in rows])
    dominant = _dominant_mistakes(rows, mistakes)
    topics = _topic_summaries(rows, mistakes)
    current = None
    if links:
        item = get_practice_item(db, session.course_id, links[-1].practice_id)
        if item is not None:
            current = practice_item_read(db, item)
    context = _session_context(db, session)
    return TutorPracticeSessionRead(
        id=session.id,
        course_id=session.course_id,
        status=session.status,
        provider_requested=session.provider_requested,
        retrieval_mode=session.retrieval_mode,
        max_items=session.max_items,
        item_count=len(links),
        attempt_count=len(rows),
        average_score=(round(sum(row.score for row in rows) / len(rows), 4) if rows else None),
        average_hints=(round(sum(row.hints for row in rows) / len(rows), 4) if rows else None),
        dominant_mistakes=dominant,
        topic_summaries=topics,
        remediation_focus=context.focus_topic,
        current_practice=current,
        created_at=session.created_at,
        completed_at=session.completed_at,
    )


def _link_practice(
    db: Session,
    session: TutorPracticeSession,
    practice_id: str,
) -> TutorPracticeSessionItem:
    links = _links(db, session.id)
    link = TutorPracticeSessionItem(
        id=str(uuid4()),
        session_id=session.id,
        practice_id=practice_id,
        sequence=len(links) + 1,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def create_practice_session(
    db: Session,
    course_id: str,
    payload: TutorPracticeSessionCreateRequest,
    *,
    provider_config: TutorProviderConfig | None = None,
    embedding_config: TutorEmbeddingConfig | None = None,
    embedding_provider: TutorEmbeddingProvider | None = None,
) -> TutorPracticeSessionRead:
    practice = create_practice_item(
        db,
        course_id,
        TutorPracticeCreateRequest(
            target_topic=payload.target_topic,
            difficulty=payload.difficulty,
            marks=payload.marks,
            provider=payload.provider,
            retrieval_mode=payload.retrieval_mode,
            max_sources=payload.max_sources,
        ),
        provider_config=provider_config,
        embedding_config=embedding_config,
        embedding_provider=embedding_provider,
    )
    session = TutorPracticeSession(
        id=str(uuid4()),
        course_id=course_id,
        provider_requested=payload.provider,
        retrieval_mode=payload.retrieval_mode,
        max_items=payload.max_items,
        status="active",
    )
    db.add(session)
    db.flush()
    db.add(
        TutorPracticeSessionItem(
            id=str(uuid4()),
            session_id=session.id,
            practice_id=practice.id,
            sequence=1,
        )
    )
    db.commit()
    db.refresh(session)
    return practice_session_read(db, session)


def _plan_from_history(
    db: Session,
    session: TutorPracticeSession,
    current_item: TutorPracticeItem,
) -> tuple[str, str, str | None, str]:
    rows = _session_rows(db, session.id)
    recent = rows[-_RECENT_WINDOW:]
    mistakes = _mistakes_by_attempt(db, [row.attempt_id for row in recent])
    dominant = _dominant_mistakes(recent, mistakes)

    if dominant and dominant[0].occurrences >= 2:
        category = dominant[0].category
        focus = _focus_for_category(recent, mistakes, category) or current_item.topic_name
        topic_rows = [row for row in recent if row.topic == focus]
        topic_score = sum(row.score for row in topic_rows) / len(topic_rows)
        difficulty = (
            _shift_difficulty(current_item.difficulty, -1)
            if topic_score < 0.65
            else current_item.difficulty
        )
        return (
            "remediate_pattern",
            difficulty,
            focus,
            f"Recurring {category} mistakes appeared {dominant[0].occurrences} times in recent "
            f"session attempts; target {focus} directly before moving on.",
        )

    recent_three = recent[-3:]
    if recent_three:
        average_hints = sum(row.hints for row in recent_three) / len(recent_three)
        average_score = sum(row.score for row in recent_three) / len(recent_three)
        if average_hints >= 1.5:
            difficulty = (
                _shift_difficulty(current_item.difficulty, -1)
                if average_score < 0.70
                else current_item.difficulty
            )
            return (
                "reduce_scaffolding",
                difficulty,
                current_item.topic_name,
                "Recent answers depend heavily on hints; reinforce the same topic with less "
                "difficulty pressure before removing scaffolding.",
            )
        if average_score < 0.60:
            weakest = min(
                _topic_summaries(recent, mistakes),
                key=lambda item: item.average_score,
            )
            return (
                "reinforce",
                _shift_difficulty(current_item.difficulty, -1),
                weakest.topic,
                "Recent session accuracy is weak; reinforce the lowest-scoring recent topic.",
            )

    recent_two = recent[-2:]
    if len(recent_two) == 2 and all(row.score >= 0.85 and row.hints == 0 for row in recent_two):
        return (
            "session_reoptimize",
            _shift_difficulty(current_item.difficulty, 1),
            None,
            "Two strong unassisted answers in a row; return to the course-wide weakness optimizer.",
        )

    last = recent[-1]
    if last.score < 0.55 or last.hints >= 2:
        return (
            "reinforce",
            _shift_difficulty(current_item.difficulty, -1),
            current_item.topic_name,
            "Latest attempt is weak or hint-dependent; reinforce the current topic.",
        )
    if last.score >= 0.85 and last.hints == 0:
        return (
            "increase_difficulty",
            _shift_difficulty(current_item.difficulty, 1),
            current_item.topic_name,
            "Latest answer is strong and unassisted; increase difficulty on the same topic.",
        )
    return (
        "maintain",
        current_item.difficulty,
        current_item.topic_name,
        "Session evidence is mixed; keep the same topic and difficulty for another check.",
    )


def adapt_practice_session(
    db: Session,
    course_id: str,
    session_id: str,
    item: TutorPracticeItem,
    *,
    generate_next: bool,
    provider_config: TutorProviderConfig | None = None,
    embedding_config: TutorEmbeddingConfig | None = None,
    embedding_provider: TutorEmbeddingProvider | None = None,
) -> SessionAdaptation:
    session = validate_practice_session_item(db, course_id, session_id, item)
    links = _links(db, session.id)
    if len(links) >= session.max_items:
        session.status = "completed"
        session.completed_at = datetime.now(UTC)
        db.commit()
        return SessionAdaptation(
            strategy="session_complete",
            reason="Practice session reached its configured item limit.",
            next_practice=None,
            context=_session_context(db, session, focus_reason="Session item limit reached."),
        )

    strategy, difficulty, target_topic, reason = _plan_from_history(db, session, item)
    next_practice = None
    if generate_next:
        next_practice = create_practice_item(
            db,
            course_id,
            TutorPracticeCreateRequest(
                target_topic=target_topic,
                difficulty=difficulty,
                provider=session.provider_requested,
                retrieval_mode=session.retrieval_mode,
            ),
            provider_config=provider_config,
            embedding_config=embedding_config,
            embedding_provider=embedding_provider,
        )
        _link_practice(db, session, next_practice.id)

    return SessionAdaptation(
        strategy=strategy,
        reason=reason,
        next_practice=next_practice,
        context=_session_context(db, session, focus_reason=reason),
    )


def complete_practice_session(
    db: Session,
    session: TutorPracticeSession,
) -> TutorPracticeSessionRead:
    if session.status != "completed":
        session.status = "completed"
        session.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(session)
    return practice_session_read(db, session)
