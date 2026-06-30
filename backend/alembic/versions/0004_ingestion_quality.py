"""Add ingestion quality metadata.

Revision ID: 0004_ingestion_quality
Revises: 0003_integrations
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0004_ingestion_quality"
down_revision: str | Sequence[str] | None = "0003_integrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {
        column["name"] for column in inspector.get_columns("document_analyses")
    }

    with op.batch_alter_table("document_analyses") as batch:
        if "empty_unit_count" not in columns:
            batch.add_column(
                sa.Column(
                    "empty_unit_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
        if "extraction_quality" not in columns:
            batch.add_column(
                sa.Column(
                    "extraction_quality",
                    sa.Float(),
                    nullable=False,
                    server_default="0",
                )
            )
        if "text_sha256" not in columns:
            batch.add_column(sa.Column("text_sha256", sa.String(64), nullable=True))
            batch.create_index(
                "ix_document_analyses_text_sha256",
                ["text_sha256"],
            )
        if "duplicate_of_document_id" not in columns:
            batch.add_column(
                sa.Column("duplicate_of_document_id", sa.String(36), nullable=True)
            )
            batch.create_foreign_key(
                "fk_document_analyses_duplicate_document",
                "documents",
                ["duplicate_of_document_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_index(
                "ix_document_analyses_duplicate_of_document_id",
                ["duplicate_of_document_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"] for column in inspect(bind).get_columns("document_analyses")
    }
    with op.batch_alter_table("document_analyses") as batch:
        if "duplicate_of_document_id" in columns:
            batch.drop_index("ix_document_analyses_duplicate_of_document_id")
            batch.drop_constraint(
                "fk_document_analyses_duplicate_document",
                type_="foreignkey",
            )
            batch.drop_column("duplicate_of_document_id")
        if "text_sha256" in columns:
            batch.drop_index("ix_document_analyses_text_sha256")
            batch.drop_column("text_sha256")
        if "extraction_quality" in columns:
            batch.drop_column("extraction_quality")
        if "empty_unit_count" in columns:
            batch.drop_column("empty_unit_count")
