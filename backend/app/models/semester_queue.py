from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SemesterStudyQueue(Base):
    __tablename__ = "semester_study_queues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    initial_available_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_available_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    lost_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    course_configs: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SemesterStudyQueueRevision(Base):
    __tablename__ = "semester_study_queue_revisions"
    __table_args__ = (
        UniqueConstraint("queue_id", "revision", name="uq_semester_queue_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    queue_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("semester_study_queues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    optimization_model: Mapped[str] = mapped_column(String(80), nullable=False)
    remaining_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_normalized_target_gap_before: Mapped[float] = mapped_column(Float, nullable=False)
    total_normalized_target_gap_after: Mapped[float] = mapped_column(Float, nullable=False)
    total_utility_score: Mapped[float] = mapped_column(Float, nullable=False)
    course_results: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    source_fingerprint: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class SemesterStudyQueueBlock(Base):
    __tablename__ = "semester_study_queue_blocks"
    __table_args__ = (
        UniqueConstraint(
            "queue_id", "revision", "sequence", name="uq_semester_queue_block_sequence"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    queue_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("semester_study_queues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="SET NULL"), index=True
    )
    course_name: Mapped[str] = mapped_column(String(120), nullable=False)
    topic_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("course_topics.id", ondelete="SET NULL"), index=True
    )
    topic_name: Mapped[str] = mapped_column(String(160), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    expected_mark_gain: Mapped[float] = mapped_column(Float, nullable=False)
    normalized_target_gap_reduction: Mapped[float] = mapped_column(Float, nullable=False)
    utility_score: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
