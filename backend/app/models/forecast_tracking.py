from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GradeForecastSnapshot(Base):
    __tablename__ = "grade_forecast_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    forecast_model: Mapped[str] = mapped_column(String(40), nullable=False)
    probability_status: Mapped[str] = mapped_column(String(30), nullable=False)
    max_grade: Mapped[float] = mapped_column(Float, nullable=False)
    study_hours: Mapped[float] = mapped_column(Float, nullable=False)
    target_grade: Mapped[float] = mapped_column(Float, nullable=False)
    expected_grade: Mapped[float] = mapped_column(Float, nullable=False)
    standard_deviation: Mapped[float] = mapped_column(Float, nullable=False)
    interval_probability: Mapped[float] = mapped_column(Float, nullable=False)
    likely_range_low: Mapped[float] = mapped_column(Float, nullable=False)
    likely_range_high: Mapped[float] = mapped_column(Float, nullable=False)
    target_probability: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_quality: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    request_payload: Mapped[str] = mapped_column(Text, nullable=False)
    thresholds_payload: Mapped[str] = mapped_column(Text, nullable=False)
    assumptions_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )


class GradeForecastOutcome(Base):
    __tablename__ = "grade_forecast_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    forecast_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("grade_forecast_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    actual_grade: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class GradeForecastRecalibrationArtifact(Base):
    __tablename__ = "grade_forecast_recalibration_artifacts"

    forecast_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("grade_forecast_snapshots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    raw_forecast_model: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_probability_status: Mapped[str] = mapped_column(String(30), nullable=False)
    raw_expected_grade: Mapped[float] = mapped_column(Float, nullable=False)
    raw_standard_deviation: Mapped[float] = mapped_column(Float, nullable=False)
    raw_likely_range_low: Mapped[float] = mapped_column(Float, nullable=False)
    raw_likely_range_high: Mapped[float] = mapped_column(Float, nullable=False)
    raw_target_probability: Mapped[float] = mapped_column(Float, nullable=False)
    raw_thresholds_payload: Mapped[str] = mapped_column(Text, nullable=False)
    calibration_model: Mapped[str] = mapped_column(String(40), nullable=False)
    calibration_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    paired_outcome_count: Mapped[int] = mapped_column(Integer, nullable=False)
    shrinkage_weight: Mapped[float] = mapped_column(Float, nullable=False)
    raw_bias_marks: Mapped[float] = mapped_column(Float, nullable=False)
    applied_bias_marks: Mapped[float] = mapped_column(Float, nullable=False)
    raw_width_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    applied_width_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
