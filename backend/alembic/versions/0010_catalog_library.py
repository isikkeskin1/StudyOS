"""Add institutional library folders and document placement.

Revision ID: 0010_catalog_library
Revises: 0009_spotify_integration
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_catalog_library"
down_revision: str | Sequence[str] | None = "0009_spotify_integration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "catalog_folders" not in tables:
        op.create_table(
            "catalog_folders",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "catalog_course_id",
                sa.String(36),
                sa.ForeignKey("catalog_courses.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "parent_id",
                sa.String(36),
                sa.ForeignKey("catalog_folders.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("name", sa.String(180), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "catalog_course_id",
                "parent_id",
                "name",
                name="uq_catalog_folder_sibling_name",
            ),
        )
        op.create_index(
            "ix_catalog_folders_catalog_course_id",
            "catalog_folders",
            ["catalog_course_id"],
        )
        op.create_index(
            "ix_catalog_folders_parent_id",
            "catalog_folders",
            ["parent_id"],
        )

    # Some old desktop databases are stamped at the legacy v0.4 baseline even
    # when they only contain the historical users table. The desktop lifespan
    # creates any still-missing application tables after Alembic finishes, so
    # the migration must tolerate documents not existing yet. Fresh/cloud
    # databases already have documents here and receive the FK normally.
    if "documents" in tables:
        document_columns = {
            column["name"] for column in inspector.get_columns("documents")
        }
        if "catalog_folder_id" not in document_columns:
            with op.batch_alter_table("documents") as batch:
                batch.add_column(
                    sa.Column("catalog_folder_id", sa.String(36), nullable=True)
                )
                batch.create_foreign_key(
                    "fk_documents_catalog_folder_id",
                    "catalog_folders",
                    ["catalog_folder_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
                batch.create_index(
                    "ix_documents_catalog_folder_id",
                    ["catalog_folder_id"],
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "documents" in tables:
        columns = {column["name"] for column in inspector.get_columns("documents")}
        if "catalog_folder_id" in columns:
            with op.batch_alter_table("documents") as batch:
                batch.drop_index("ix_documents_catalog_folder_id")
                batch.drop_constraint(
                    "fk_documents_catalog_folder_id",
                    type_="foreignkey",
                )
                batch.drop_column("catalog_folder_id")
    if "catalog_folders" in tables:
        op.drop_table("catalog_folders")
