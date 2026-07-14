"""add channels.is_trending_source + trending_posters table

Revision ID: 3508892947d2
Revises: 181b4b5fa68a
Create Date: 2026-07-04 00:00:00

Trending & New was previously backed directly by the movies table (sorted
by view count), delivering the actual file through the same PPV gate as
Search. That was a narrower fix for a leak, not the original spec: this
section is meant to be posters/images only, sourced exclusively from
admin-designated channels, populated only by explicit admin action — never
automatically, and never able to deliver a real file regardless of VIP or
PPV status. This revision adds the two pieces that make that possible:
channels.is_trending_source marks which channels the admin has designated
as eligible poster sources, and trending_posters holds the curated list
itself. handlers/user/trending.py no longer touches the movies table at
all after this.

Verified in a sandbox run: applied on top of the current head, an existing
channel row correctly defaulted to is_trending_source=False (no channel is
retroactively treated as a source), a poster row inserted and read back
correctly, downgrade drops the new table and column cleanly, re-upgrade
restores both.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "3508892947d2"
down_revision: Union[str, None] = "181b4b5fa68a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("is_trending_source", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "trending_posters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("image_file_id", sa.String(256), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column(
            "source_channel_id", sa.Integer(),
            sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("trending_posters")
    with op.batch_alter_table("channels") as batch_op:
        batch_op.drop_column("is_trending_source")
