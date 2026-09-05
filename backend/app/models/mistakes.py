from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DiagnosticAnswerArtifact(Base):
    __tablename__ = "diagnostic_answer_artifacts"
    __table_args__ = (
        UniqueConstraint("response_id", name="uq_diagnostic_response_answer_artifact"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    response_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("diagnostic_responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class DiagnosticMistake(Base):
    __tablename__ = "diagnostic_mistakes"
    __table_args__ = (
        UniqueConstraint("response_id", "category", name="uq_diagnostic_response_mistake"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    response_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("diagnostic_responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="self")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
