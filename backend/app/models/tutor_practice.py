from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TutorPracticeItem(Base):
    __tablename__ = "tutor_practice_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("course_topics.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    topic_name: Mapped[str] = mapped_column(String(160), nullable=False)
    topic_selection: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    marks: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_requested: Mapped[str] = mapped_column(String(16), nullable=False)
    generation_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    generation_mode: Mapped[str] = mapped_column(String(48), nullable=False)
    retrieval_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    hints: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    solution: Mapped[str] = mapped_column(Text, nullable=False)
    hints_revealed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    solution_revealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class TutorPracticeEvidence(Base):
    __tablename__ = "tutor_practice_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    practice_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutor_practice_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    source_label: Mapped[str] = mapped_column(String(100), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
