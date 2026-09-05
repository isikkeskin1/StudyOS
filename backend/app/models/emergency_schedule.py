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


class EmergencyStudySchedule(Base):
    __tablename__ = "emergency_study_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    target_grade: Mapped[float] = mapped_column(Float, nullable=False)
    max_grade: Mapped[float] = mapped_column(Float, nullable=False)
    initial_available_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_available_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    lost_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    skip_threshold_marks_per_hour: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    topic_mastery_overrides: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    use_stored_mastery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exam_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmergencyStudyScheduleRevision(Base):
    __tablename__ = "emergency_study_schedule_revisions"
    __table_args__ = (
        UniqueConstraint(
            "schedule_id",
            "revision",
            name="uq_emergency_schedule_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    schedule_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("emergency_study_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    remaining_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    current_estimated_grade: Mapped[float] = mapped_column(Float, nullable=False)
    projected_grade: Mapped[float] = mapped_column(Float, nullable=False)
    expected_mark_gain: Mapped[float] = mapped_column(Float, nullable=False)
    target_gap_after: Mapped[float] = mapped_column(Float, nullable=False)
    mastery_basis: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class EmergencyStudyScheduleBlock(Base):
    __tablename__ = "emergency_study_schedule_blocks"
    __table_args__ = (
        UniqueConstraint(
            "schedule_id",
            "revision",
            "sequence",
            name="uq_emergency_schedule_block_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    schedule_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("emergency_study_schedules.id", ondelete="CASCADE"),
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
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starting_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    ending_mastery: Mapped[float] = mapped_column(Float, nullable=False)
    expected_mark_gain: Mapped[float] = mapped_column(Float, nullable=False)
    expected_marks_per_hour: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
