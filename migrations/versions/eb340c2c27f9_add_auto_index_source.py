"""add channels.is_auto_index_source

Revision ID: eb340c2c27f9
Revises: 3508892947d2
Create Date: 2026-07-04 12:00:00

Adds the channel-level flag that opts a channel into automatic movie
indexing (any video/audio/document posted there gets registered into
search, priced with the same default_ppv_price gate batch upload already
uses). Deliberately a separate column from is_trending_source — the admin
was explicit that these should be independent toggles, not the same flag
reused for two features.

Verified: applied on top of head, an existing channel row defaulted to
is_auto_index_source=False (no channel becomes an auto-index source
retroactively), downgrade drops the column cleanly, re-upgrade restores it.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "eb340c2c27f9"
down_revision: Union[str, None] = "3508892947d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("is_auto_index_source", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    with op.batch_alter_table("channels") as batch_op:
        batch_op.drop_column("is_auto_index_source")
