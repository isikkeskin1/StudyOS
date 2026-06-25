from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExamDaySession(Base):
    __tablename__ = "exam_day_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_known_marks: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExamDayQuestion(Base):
    __tablename__ = "exam_day_questions"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_exam_day_question_sequence"),
        UniqueConstraint("session_id", "exam_question_id", name="uq_exam_day_exam_question"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("exam_day_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    exam_question_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("exam_questions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    question_label: Mapped[str] = mapped_column(String(40), nullable=False)
    source_label: Mapped[str] = mapped_column(String(100), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    marks: Mapped[float | None] = mapped_column(Float, nullable=True)
    primary_topic_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("course_topics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    automatic_grading_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class ExamDayAnswer(Base):
    __tablename__ = "exam_day_answers"
    __table_args__ = (
        UniqueConstraint("exam_day_question_id", name="uq_exam_day_question_answer"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("exam_day_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    exam_day_question_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("exam_day_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    self_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    grading_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
