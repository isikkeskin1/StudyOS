"""Add accounts and tenant ownership.

Revision ID: 0002_accounts
Revises: 0001_baseline
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0002_accounts"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("password_hash", sa.String(512), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if "auth_sessions" not in tables:
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
        op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    inspector = inspect(bind)
    course_columns = {column["name"] for column in inspector.get_columns("courses")}
    if "user_id" not in course_columns:
        with op.batch_alter_table("courses") as batch:
            batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_courses_user_id_users",
                "users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch.create_index("ix_courses_user_id", ["user_id"])

    inspector = inspect(bind)
    queue_columns = {
        column["name"] for column in inspector.get_columns("semester_study_queues")
    }
    if "user_id" not in queue_columns:
        with op.batch_alter_table("semester_study_queues") as batch:
            batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_semester_study_queues_user_id_users",
                "users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch.create_index("ix_semester_study_queues_user_id", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    queue_columns = {
        column["name"] for column in inspector.get_columns("semester_study_queues")
    }
    if "user_id" in queue_columns:
        with op.batch_alter_table("semester_study_queues") as batch:
            batch.drop_index("ix_semester_study_queues_user_id")
            batch.drop_constraint(
                "fk_semester_study_queues_user_id_users",
                type_="foreignkey",
            )
            batch.drop_column("user_id")

    inspector = inspect(bind)
    course_columns = {column["name"] for column in inspector.get_columns("courses")}
    if "user_id" in course_columns:
        with op.batch_alter_table("courses") as batch:
            batch.drop_index("ix_courses_user_id")
            batch.drop_constraint("fk_courses_user_id_users", type_="foreignkey")
            batch.drop_column("user_id")

    tables = set(inspect(bind).get_table_names())
    if "auth_sessions" in tables:
        op.drop_table("auth_sessions")
    if "users" in tables:
        op.drop_table("users")
