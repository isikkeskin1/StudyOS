"""Add catalog source discovery queue.

Revision ID: 0006_catalog_sources
Revises: 0005_admin_catalog
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0006_catalog_sources"
down_revision: str | Sequence[str] | None = "0005_admin_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "catalog_sources" in inspector.get_table_names():
        return

    op.create_table(
        "catalog_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "catalog_course_id",
            sa.String(36),
            sa.ForeignKey("catalog_courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("discovered_from_url", sa.String(2000), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("source_kind", sa.String(40), nullable=False, server_default="other"),
        sa.Column("content_type", sa.String(160), nullable=True),
        sa.Column("extension", sa.String(16), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="candidate"),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column(
            "imported_document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("discovery_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "catalog_course_id",
            "url",
            name="uq_catalog_source_url",
        ),
    )
    op.create_index(
        "ix_catalog_sources_catalog_course_id",
        "catalog_sources",
        ["catalog_course_id"],
    )
    op.create_index(
        "ix_catalog_sources_status",
        "catalog_sources",
        ["status"],
    )
    op.create_index(
        "ix_catalog_sources_sha256",
        "catalog_sources",
        ["sha256"],
    )
    op.create_index(
        "ix_catalog_sources_imported_document_id",
        "catalog_sources",
        ["imported_document_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "catalog_sources" in inspect(bind).get_table_names():
        op.drop_table("catalog_sources")
