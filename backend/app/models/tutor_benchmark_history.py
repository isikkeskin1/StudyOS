from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TutorRetrievalBenchmarkSuite(Base):
    __tablename__ = "tutor_retrieval_benchmark_suites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    benchmark_model: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="retrieval-hard-negative-v1",
    )
    cases: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    default_modes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    default_k: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    default_max_results: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class TutorRetrievalBenchmarkRun(Base):
    __tablename__ = "tutor_retrieval_benchmark_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    suite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutor_retrieval_benchmark_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    benchmark_model: Mapped[str] = mapped_column(String(80), nullable=False)
    modes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, nullable=False)
    best_mode: Mapped[str | None] = mapped_column(String(24), nullable=True)
    result: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    comparison: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
