from __future__ import annotations

from dataclasses import dataclass
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
from app.models.tutor_remediation import TutorPracticeTeachingArtifact
from app.schemas.tutor_remediation import (
    TutorPracticeTeachingHintRead,
    TutorPracticeTeachingRead,
)
from app.services.tutor_practice import get_practice_item, reveal_next_hint
from app.services.tutor_practice_sessions import (
    TutorPracticeSessionError,
    get_practice_session,
    validate_practice_session_item,
)

_RECENT_WINDOW = 5
_MODEL_NAME = "deterministic-session-remediation-v1"


class TutorPracticeTeachingError(RuntimeError):
    pass


@dataclass(frozen=True)
class _AttemptRow:
    topic: str
    score: float
    hints: int
    attempt_id: str


_COACHING: dict[str, tuple[str, list[str]]] = {
    "concept": (
        "The recurring issue is conceptual setup. Before calculating, state the governing "
        "principle in one sentence and explain why it applies here.",
        [
            "Name the governing principle before writing equations.",
            "Connect each given quantity to that principle before substituting values.",
            "After solving, explain in one sentence why the result follows from the principle.",
        ],
    ),
    "formula_selection": (
        "The recurring issue is choosing the right relationship. Identify the target quantity "
        "first, then write the governing equation before touching the numbers.",
        [
            "Write the unknown you are solving for and its required units.",
            "List only equations that connect that unknown to the given quantities.",
            "Choose the equation symbolically, rearrange it, and only then substitute values.",
        ],
    ),
    "algebra": (
        "The recurring issue is algebra after the physics setup. Keep the equation symbolic "
        "until the target variable is isolated, then substitute once.",
        [
            "Isolate the target variable symbolically before inserting numbers.",
            "Carry one algebraic operation per line so sign and factor changes stay visible.",
            "Check the rearranged equation by substituting dimensions or reversing the operation.",
        ],
    ),
    "arithmetic": (
        "The recurring issue is numerical execution. Separate the correct setup from the "
        "calculation and sanity-check the magnitude before finalizing.",
        [
            "Write the full numerical substitution on one line before calculating.",
            "Estimate the order of magnitude before using the exact arithmetic.",
            "Recalculate the final operation independently and compare it with your estimate.",
        ],
    ),
    "sign": (
        "The recurring issue is sign convention. Define the positive direction, label every "
        "relevant direction, and assign signs before writing the final equation.",
        [
            "Choose and write the positive axis before doing any algebra.",
            "Mark each velocity, force, or displacement as positive or negative from that axis.",
            "Substitute signed quantities only after the symbolic relationship is correct.",
        ],
    ),
    "units": (
        "The recurring issue is units. Keep a unit beside every numerical quantity and use "
        "dimensional consistency as a check on the equation and final result.",
        [
            "Write the unit next to every given quantity before substituting.",
            "Convert quantities to a consistent unit system before calculating.",
            "Check that the final dimensions match the quantity the question asks for.",
        ],
    ),
    "interpretation": (
        "The recurring issue is translating the question into a model. Separate what is given, "
        "what is asked, and what physical event or constraint connects them.",
        [
            "Rewrite the question as a short list of knowns and one explicit unknown.",
            "Identify the physical event or constraint that links the knowns to the unknown.",
            "Before calculating, state what your final value will mean physically.",
        ],
    ),
    "incomplete_reasoning": (
        "The recurring issue is missing justification. Make every major step explicit: state "
        "the principle, show the setup, then explain why the conclusion follows.",
        [
            "Add one sentence naming the principle or assumption used.",
            "Show the intermediate equation or reasoning step instead of jumping to the result.",
            "Finish with a sentence that connects the computed result back to the question.",
        ],
    ),
    "careless": (
        "Recent work suggests avoidable execution errors. Use a short final check before "
        "submitting rather than changing the underlying method.",
        [
            "Pause after setup and verify copied values, signs, and exponents.",
            "Check the final line against the exact quantity and units requested.",
            "Do a quick magnitude and direction sanity check before submitting.",
        ],
    ),
    "other": (
        "A recurring error pattern is present. Slow the setup down and make the reasoning "
        "visible before calculating.",
        [
            "State what the problem is asking for before solving.",
            "Write the governing relationship and justify why it applies.",
            "Check the final result against the question, units, and physical meaning.",
        ],
    ),
}


def _attempt_rows(db: Session, session_id: str) -> list[_AttemptRow]:
    rows = db.execute(
        select(TutorPracticeItem, TutorPracticeAttempt)
        .join(
            TutorPracticeSessionItem,
            TutorPracticeSessionItem.practice_id == TutorPracticeItem.id,
        )
        .join(
            TutorPracticeAttempt,
            TutorPracticeAttempt.practice_id == TutorPracticeItem.id,
        )
        .where(TutorPracticeSessionItem.session_id == session_id)
        .order_by(TutorPracticeSessionItem.sequence)
    ).all()
    return [
        _AttemptRow(
            topic=item.topic_name,
            score=attempt.score,
            hints=attempt.hints_used,
            attempt_id=attempt.id,
        )
        for item, attempt in rows
    ]


def _mistakes_by_attempt(
    db: Session,
    attempt_ids: list[str],
) -> dict[str, list[TutorPracticeMistake]]:
    if not attempt_ids:
        return {}
    items = list(
        db.scalars(
            select(TutorPracticeMistake).where(
                TutorPracticeMistake.attempt_id.in_(attempt_ids)
            )
        ).all()
    )
    grouped: dict[str, list[TutorPracticeMistake]] = {}
    for item in items:
        grouped.setdefault(item.attempt_id, []).append(item)
    return grouped


def _dominant_mistake(
    rows: list[_AttemptRow],
    mistakes: dict[str, list[TutorPracticeMistake]],
) -> tuple[str | None, int, str | None]:
    counts: dict[str, int] = {}
    severity: dict[str, float] = {}
    topic_burden: dict[tuple[str, str], float] = {}
    for row in rows:
        for mistake in mistakes.get(row.attempt_id, []):
            counts[mistake.category] = counts.get(mistake.category, 0) + 1
            severity[mistake.category] = severity.get(mistake.category, 0.0) + mistake.severity
            key = (mistake.category, row.topic)
            topic_burden[key] = topic_burden.get(key, 0.0) + mistake.severity
    if not counts:
        return None, 0, None
    category = max(
        counts,
        key=lambda name: (counts[name], severity[name], name),
    )
    topics = {
        topic: burden
        for (mistake_category, topic), burden in topic_burden.items()
        if mistake_category == category
    }
    focus = max(topics, key=lambda topic: (topics[topic], topic)) if topics else None
    return category, counts[category], focus


def _current_unanswered_item(
    db: Session,
    session: TutorPracticeSession,
) -> TutorPracticeItem:
    links = list(
        db.scalars(
            select(TutorPracticeSessionItem)
            .where(TutorPracticeSessionItem.session_id == session.id)
            .order_by(TutorPracticeSessionItem.sequence.desc())
        ).all()
    )
    for link in links:
        attempted = db.scalar(
            select(TutorPracticeAttempt.id).where(
                TutorPracticeAttempt.practice_id == link.practice_id
            )
        )
        if attempted is None:
            item = get_practice_item(db, session.course_id, link.practice_id)
            if item is not None:
                return item
    raise TutorPracticeTeachingError("Practice session has no unanswered practice item")


def _strategy(
    rows: list[_AttemptRow],
    dominant: str | None,
    dominant_count: int,
) -> str:
    if dominant is not None and dominant_count >= 2:
        return "remediate_pattern"
    recent_three = rows[-3:]
    if recent_three:
        avg_hints = sum(row.hints for row in recent_three) / len(recent_three)
        avg_score = sum(row.score for row in recent_three) / len(recent_three)
        if avg_hints >= 1.5:
            return "reduce_scaffolding"
        if avg_score < 0.60:
            return "reinforce"
    recent_two = rows[-2:]
    if len(recent_two) == 2 and all(row.score >= 0.85 and row.hints == 0 for row in recent_two):
        return "challenge"
    if rows:
        return "maintain"
    return "baseline"


def _generic_teaching(
    strategy: str,
    topic: str,
) -> tuple[str, list[str]]:
    if strategy == "reduce_scaffolding":
        return (
            "You have been relying on hints recently. For this question, complete the setup "
            "independently before opening Hint 1; the hints are there only after a genuine try.",
            [
                "Try to finish the setup before reading the underlying course hint.",
                "Use the next hint only to check your direction, not to replace your own work.",
                "Before viewing the solution, write a complete final attempt in your own words.",
            ],
        )
    if strategy == "reinforce":
        return (
            f"Recent accuracy is weak, so this {topic} question is a reinforcement attempt. "
            "Slow down the setup and make each step visible before calculating.",
            [
                "List the known quantities and the target before using the course hint.",
                "State the governing relationship and check that it matches the target.",
                "Verify the final value, units, and physical meaning before submitting.",
            ],
        )
    if strategy == "challenge":
        return (
            "You solved the last two questions strongly without hints. Treat this as an "
            "independent check: solve it fully before opening any support.",
            [
                "Only open this after completing your own setup; compare the principle you chose.",
                "Use this to check one intermediate step rather than restart the solution.",
                "Use the final hint as a verification checkpoint before submitting.",
            ],
        )
    if strategy == "maintain":
        return (
            f"Use this {topic} question as another independent check. Keep your reasoning "
            "explicit so StudyOS can distinguish understanding from a lucky final answer.",
            [
                "Write the governing principle before opening the course-specific hint.",
                "Keep intermediate reasoning visible rather than jumping to the final value.",
                "Do a final check of signs, units, and interpretation before submitting.",
            ],
        )
    return (
        "Start this first session question independently. Write your setup before using hints so "
        "later session adaptation has a clean baseline.",
        [
            "Try the setup yourself before reading the course-specific hint.",
            "Use the next hint as a checkpoint, not as a replacement for your reasoning.",
            "Before revealing the solution, make one complete final attempt.",
        ],
    )


def _build_artifact(
    db: Session,
    session: TutorPracticeSession,
    item: TutorPracticeItem,
) -> TutorPracticeTeachingArtifact:
    rows = _attempt_rows(db, session.id)[-_RECENT_WINDOW:]
    mistakes = _mistakes_by_attempt(db, [row.attempt_id for row in rows])
    dominant, dominant_count, mistake_focus = _dominant_mistake(rows, mistakes)
    strategy = _strategy(rows, dominant, dominant_count)
    focus_topic = mistake_focus or item.topic_name

    if strategy == "remediate_pattern" and dominant is not None:
        base_intro, coaching_steps = _COACHING.get(dominant, _COACHING["other"])
        teaching_intro = (
            f"{base_intro} This pattern appeared {dominant_count} times in the recent session "
            f"window, so this {focus_topic} attempt is deliberately targeting it."
        )
    else:
        teaching_intro, coaching_steps = _generic_teaching(strategy, focus_topic)

    recent_average_score = (
        round(sum(row.score for row in rows) / len(rows), 4) if rows else None
    )
    recent_average_hints = (
        round(sum(row.hints for row in rows) / len(rows), 4) if rows else None
    )
    artifact = TutorPracticeTeachingArtifact(
        id=str(uuid4()),
        session_id=session.id,
        practice_id=item.id,
        strategy=strategy,
        focus_topic=focus_topic,
        dominant_mistake=dominant if dominant_count >= 2 else None,
        dominant_mistake_count=dominant_count if dominant_count >= 2 else 0,
        recent_attempt_count=len(rows),
        recent_average_score=recent_average_score,
        recent_average_hints=recent_average_hints,
        teaching_intro=teaching_intro,
        coaching_steps=coaching_steps,
        model_name=_MODEL_NAME,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def _read(artifact: TutorPracticeTeachingArtifact) -> TutorPracticeTeachingRead:
    return TutorPracticeTeachingRead(
        session_id=artifact.session_id,
        practice_id=artifact.practice_id,
        model_name=artifact.model_name,
        strategy=artifact.strategy,
        focus_topic=artifact.focus_topic,
        dominant_mistake=artifact.dominant_mistake,
        dominant_mistake_count=artifact.dominant_mistake_count,
        recent_attempt_count=artifact.recent_attempt_count,
        recent_average_score=artifact.recent_average_score,
        recent_average_hints=artifact.recent_average_hints,
        teaching_intro=artifact.teaching_intro,
        coaching_steps=list(artifact.coaching_steps),
    )


def ensure_teaching_artifact(
    db: Session,
    course_id: str,
    session_id: str,
    item: TutorPracticeItem,
) -> TutorPracticeTeachingArtifact:
    validate_practice_session_item(db, course_id, session_id, item)
    existing = db.scalar(
        select(TutorPracticeTeachingArtifact).where(
            TutorPracticeTeachingArtifact.session_id == session_id,
            TutorPracticeTeachingArtifact.practice_id == item.id,
        )
    )
    if existing is not None:
        return existing
    session = get_practice_session(db, course_id, session_id)
    if session is None:
        raise TutorPracticeSessionError("Practice session not found")
    return _build_artifact(db, session, item)


def current_teaching_plan(
    db: Session,
    course_id: str,
    session_id: str,
) -> TutorPracticeTeachingRead:
    session = get_practice_session(db, course_id, session_id)
    if session is None:
        raise TutorPracticeTeachingError("Practice session not found")
    if session.status != "active":
        raise TutorPracticeTeachingError("Practice session is already completed")
    item = _current_unanswered_item(db, session)
    artifact = ensure_teaching_artifact(db, course_id, session_id, item)
    return _read(artifact)


def reveal_teaching_hint(
    db: Session,
    course_id: str,
    session_id: str,
    practice_id: str,
) -> TutorPracticeTeachingHintRead:
    item = get_practice_item(db, course_id, practice_id)
    if item is None:
        raise TutorPracticeTeachingError("Practice item not found")
    artifact = ensure_teaching_artifact(db, course_id, session_id, item)
    base_hint = reveal_next_hint(db, item)
    index = min(base_hint.level - 1, len(artifact.coaching_steps) - 1)
    coaching = artifact.coaching_steps[index] if artifact.coaching_steps else ""
    hint = f"{coaching} {base_hint.hint}".strip()
    return TutorPracticeTeachingHintRead(
        session_id=session_id,
        practice_id=practice_id,
        level=base_hint.level,
        hint=hint,
        remaining_hints=base_hint.remaining_hints,
        strategy=artifact.strategy,
        dominant_mistake=artifact.dominant_mistake,
    )
