"""Add Spotify integration state and connection storage.

Revision ID: 0009_spotify_integration
Revises: 0008_email_verification
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_spotify_integration"
down_revision: str | Sequence[str] | None = "0008_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "spotify_connections" not in tables:
        op.create_table(
            "spotify_connections",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("spotify_user_id", sa.String(128), nullable=False),
            sa.Column("display_name", sa.String(255), nullable=True),
            sa.Column("product", sa.String(32), nullable=True),
            sa.Column("scopes", sa.Text(), nullable=False),
            sa.Column("access_token_encrypted", sa.Text(), nullable=False),
            sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", name="uq_spotify_connections_user_id"),
        )
        op.create_index(
            "ix_spotify_connections_user_id",
            "spotify_connections",
            ["user_id"],
        )

    if "spotify_oauth_states" not in tables:
        op.create_table(
            "spotify_oauth_states",
            sa.Column("state_hash", sa.String(64), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_spotify_oauth_states_user_id",
            "spotify_oauth_states",
            ["user_id"],
        )
        op.create_index(
            "ix_spotify_oauth_states_expires_at",
            "spotify_oauth_states",
            ["expires_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "spotify_oauth_states" in tables:
        op.drop_table("spotify_oauth_states")
    if "spotify_connections" in tables:
        op.drop_table("spotify_connections")
