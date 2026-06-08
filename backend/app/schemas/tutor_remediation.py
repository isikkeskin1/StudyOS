from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.diagnostics import MistakeCategory

TeachingStrategy = Literal[
    "baseline",
    "remediate_pattern",
    "reduce_scaffolding",
    "reinforce",
    "challenge",
    "maintain",
]


class TutorPracticeTeachingRead(BaseModel):
    session_id: str
    practice_id: str
    model_name: str
    strategy: TeachingStrategy
    focus_topic: str | None
    dominant_mistake: MistakeCategory | None
    dominant_mistake_count: int
    recent_attempt_count: int
    recent_average_score: float | None
    recent_average_hints: float | None
    teaching_intro: str
    coaching_steps: list[str]


class TutorPracticeTeachingHintRead(BaseModel):
    session_id: str
    practice_id: str
    level: int
    hint: str
    remaining_hints: int
    strategy: TeachingStrategy
    dominant_mistake: MistakeCategory | None
