from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TutorPracticeTeachingArtifact(Base):
    __tablename__ = "tutor_practice_teaching_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "practice_id",
            name="uq_practice_teaching_session_practice",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutor_practice_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    practice_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutor_practice_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    focus_topic: Mapped[str | None] = mapped_column(String(160), nullable=True)
    dominant_mistake: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dominant_mistake_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recent_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recent_average_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recent_average_hints: Mapped[float | None] = mapped_column(Float, nullable=True)
    teaching_intro: Mapped[str] = mapped_column(Text, nullable=False)
    coaching_steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    model_name: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="deterministic-session-remediation-v1",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
