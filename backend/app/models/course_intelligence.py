from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CourseAnalysis(Base):
    __tablename__ = "course_analyses"

    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    analyzed_document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_count: Mapped[int] = mapped_column(Integer, nullable=False)
    relationship_count: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class CourseTopic(Base):
    __tablename__ = "course_topics"
    __table_args__ = (
        UniqueConstraint("course_id", "normalized_name", name="uq_course_topic_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_mention_count: Mapped[int] = mapped_column(Integer, nullable=False)
    lecture_mention_count: Mapped[int] = mapped_column(Integer, nullable=False)


class TopicEvidence(Base):
    __tablename__ = "topic_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("course_topics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_label: Mapped[str] = mapped_column(String(100), nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_score: Mapped[float] = mapped_column(Float, nullable=False)


class TopicRelationship(Base):
    __tablename__ = "topic_relationships"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "source_topic_id",
            "target_topic_id",
            name="uq_course_topic_relationship",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("course_topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_topic_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("course_topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    cooccurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
