from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExamAnalysis(Base):
    __tablename__ = "exam_analyses"

    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    exam_document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    marked_question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_known_marks: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (
        UniqueConstraint("document_id", "question_index", name="uq_exam_question_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_label: Mapped[str] = mapped_column(String(40), nullable=False)
    source_label: Mapped[str] = mapped_column(String(100), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    marks: Mapped[float | None] = mapped_column(Float, nullable=True)


class ExamQuestionTopic(Base):
    __tablename__ = "exam_question_topics"
    __table_args__ = (
        UniqueConstraint("question_id", "topic_id", name="uq_exam_question_topic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("exam_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("course_topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    allocated_marks: Mapped[float | None] = mapped_column(Float, nullable=True)


class ExamTopicStat(Base):
    __tablename__ = "exam_topic_stats"
    __table_args__ = (
        UniqueConstraint("course_id", "topic_id", name="uq_exam_topic_stat"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("course_topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    known_marks: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    question_share: Mapped[float] = mapped_column(Float, nullable=False)
    mark_share: Mapped[float] = mapped_column(Float, nullable=False)
    exam_weight: Mapped[float] = mapped_column(Float, nullable=False)
