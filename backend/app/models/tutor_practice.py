from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class TutorPracticeAttempt(Base):
    __tablename__ = "tutor_practice_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    practice_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutor_practice_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_answer: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    grader_name: Mapped[str] = mapped_column(String(80), nullable=False)
    grader_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    mastery_weight: Mapped[float] = mapped_column(Float, nullable=False)
    hints_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class TutorPracticeMistake(Base):
    __tablename__ = "tutor_practice_mistakes"
    __table_args__ = (
        UniqueConstraint("attempt_id", "category", name="uq_practice_attempt_mistake_category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutor_practice_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TutorPracticeGradeArtifact(Base):
    __tablename__ = "tutor_practice_grade_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutor_practice_attempts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    grading_mode: Mapped[str] = mapped_column(String(48), nullable=False)
    grading_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    criteria: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    total_awarded: Mapped[float] = mapped_column(Float, nullable=False)
    total_possible: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
