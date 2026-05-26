from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExamQuestionReference(Base):
    __tablename__ = "exam_question_references"
    __table_args__ = (
        UniqueConstraint("question_id", name="uq_exam_question_reference"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    question_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("exam_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_label: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class DiagnosticGradeArtifact(Base):
    __tablename__ = "diagnostic_grade_artifacts"
    __table_args__ = (
        UniqueConstraint("response_id", name="uq_diagnostic_grade_response"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    response_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("diagnostic_responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grader_name: Mapped[str] = mapped_column(String(60), nullable=False)
    grader_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    reference_source_label: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_extraction_method: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
