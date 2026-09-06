"""Baseline existing StudyOS schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-06
"""

from collections.abc import Sequence

from alembic import op

import app.models  # noqa: F401
from app.core.database import Base

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
