"""Add push and calendar subscriptions.

Revision ID: 0003_integrations
Revises: 0002_accounts
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0003_integrations"
down_revision: str | Sequence[str] | None = "0002_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if "push_subscriptions" not in tables:
        op.create_table(
            "push_subscriptions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("endpoint", sa.Text(), nullable=False),
            sa.Column("p256dh", sa.Text(), nullable=False),
            sa.Column("auth", sa.Text(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("endpoint"),
        )
        op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    if "push_deliveries" not in tables:
        op.create_table(
            "push_deliveries",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("subscription_id", sa.String(36), nullable=False),
            sa.Column("signal_key", sa.String(255), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["subscription_id"],
                ["push_subscriptions.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "subscription_id",
                "signal_key",
                name="uq_push_delivery_signal",
            ),
        )
        op.create_index(
            "ix_push_deliveries_subscription_id",
            "push_deliveries",
            ["subscription_id"],
        )

    if "calendar_subscriptions" not in tables:
        op.create_table(
            "calendar_subscriptions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("queue_id", sa.String(36), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("timezone", sa.String(80), nullable=False),
            sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("break_minutes", sa.Integer(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["queue_id"],
                ["semester_study_queues.id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index(
            "ix_calendar_subscriptions_user_id",
            "calendar_subscriptions",
            ["user_id"],
        )
        op.create_index(
            "ix_calendar_subscriptions_queue_id",
            "calendar_subscriptions",
            ["queue_id"],
        )
        op.create_index(
            "ix_calendar_subscriptions_token_hash",
            "calendar_subscriptions",
            ["token_hash"],
            unique=True,
        )


def downgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "calendar_subscriptions" in tables:
        op.drop_table("calendar_subscriptions")
    if "push_deliveries" in tables:
        op.drop_table("push_deliveries")
    if "push_subscriptions" in tables:
        op.drop_table("push_subscriptions")
