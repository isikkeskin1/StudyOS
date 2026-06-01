from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MasterySnapshot(Base):
    __tablename__ = "mastery_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "topic_id",
            "response_id",
            name="uq_mastery_snapshot_topic_response",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("course_topics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    response_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("diagnostic_responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mastery: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_weight: Mapped[float] = mapped_column(Float, nullable=False)
    response_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_score: Mapped[float] = mapped_column(Float, nullable=False)
    topic_relevance: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_increment: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
