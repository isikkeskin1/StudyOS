from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SemesterCalendarPlan(Base):
    __tablename__ = "semester_calendar_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    queue_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("semester_study_queues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    events: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    queue_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("semester_study_queues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("semester_study_queue_blocks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    queue_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    active_key: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
