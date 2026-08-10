from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.document import Document


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_grade: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_grade: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    documents: Mapped[list[Document]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )
