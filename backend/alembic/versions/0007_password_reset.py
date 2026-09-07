"""Add password reset verification codes.

Revision ID: 0007_password_reset
Revises: 0006_catalog_sources
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0007_password_reset"
down_revision: str | Sequence[str] | None = "0006_catalog_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "password_reset_codes" in inspector.get_table_names():
        return

    op.create_table(
        "password_reset_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_reset_codes_user_id", "password_reset_codes", ["user_id"])
    op.create_index("ix_password_reset_codes_code_hash", "password_reset_codes", ["code_hash"])
    op.create_index("ix_password_reset_codes_expires_at", "password_reset_codes", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if "password_reset_codes" in inspect(bind).get_table_names():
        op.drop_table("password_reset_codes")
