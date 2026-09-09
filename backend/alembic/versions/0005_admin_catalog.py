"""Add admin roles and institutional course catalog.

Revision ID: 0005_admin_catalog
Revises: 0004_ingestion_quality
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0005_admin_catalog"
down_revision: str | Sequence[str] | None = "0004_ingestion_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_admin" not in user_columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(
                sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
            )

    if "catalog_courses" not in inspector.get_table_names():
        op.create_table(
            "catalog_courses",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "source_course_id",
                sa.String(36),
                sa.ForeignKey("courses.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("institution_name", sa.String(180), nullable=False),
            sa.Column("institution_code", sa.String(40), nullable=True),
            sa.Column("course_code", sa.String(80), nullable=True),
            sa.Column("academic_year", sa.String(32), nullable=True),
            sa.Column("language", sa.String(40), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "created_by_user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_catalog_courses_source_course_id",
            "catalog_courses",
            ["source_course_id"],
        )
        op.create_index(
            "ix_catalog_courses_institution_name",
            "catalog_courses",
            ["institution_name"],
        )
        op.create_index(
            "ix_catalog_courses_institution_code",
            "catalog_courses",
            ["institution_code"],
        )
        op.create_index(
            "ix_catalog_courses_course_code",
            "catalog_courses",
            ["course_code"],
        )
        op.create_index("ix_catalog_courses_published", "catalog_courses", ["published"])
        op.create_index(
            "ix_catalog_courses_created_by_user_id",
            "catalog_courses",
            ["created_by_user_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "catalog_courses" in inspector.get_table_names():
        op.drop_table("catalog_courses")

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_admin" in user_columns:
        with op.batch_alter_table("users") as batch:
            batch.drop_column("is_admin")
