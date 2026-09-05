from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReviewSession(Base):
    __tablename__ = "review_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"), index=True)
    topic_id: Mapped[str] = mapped_column(String(36), ForeignKey("course_topics.id"))
    practice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tutor_practice_items.id"), unique=True
    )
    active_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    selection_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
