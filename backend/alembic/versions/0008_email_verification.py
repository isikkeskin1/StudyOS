"""Add verified email identity.

Revision ID: 0008_email_verification
Revises: 0007_password_reset
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0008_email_verification"
down_revision: str | Sequence[str] | None = "0007_password_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "email_verified_at" not in user_columns:
        op.add_column(
            "users",
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.execute(
            sa.text(
                "UPDATE users SET email_verified_at = created_at "
                "WHERE email_verified_at IS NULL"
            )
        )

    inspector = inspect(bind)
    if "email_verification_codes" not in inspector.get_table_names():
        op.create_table(
            "email_verification_codes",
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
        op.create_index(
            "ix_email_verification_codes_user_id",
            "email_verification_codes",
            ["user_id"],
        )
        op.create_index(
            "ix_email_verification_codes_code_hash",
            "email_verification_codes",
            ["code_hash"],
        )
        op.create_index(
            "ix_email_verification_codes_expires_at",
            "email_verification_codes",
            ["expires_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "email_verification_codes" in inspector.get_table_names():
        op.drop_table("email_verification_codes")
    user_columns = {column["name"] for column in inspect(bind).get_columns("users")}
    if "email_verified_at" in user_columns:
        op.drop_column("users", "email_verified_at")
