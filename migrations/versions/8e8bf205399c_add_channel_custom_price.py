"""add channels.custom_ppv_price

Revision ID: 8e8bf205399c
Revises: eb340c2c27f9
Create Date: 2026-07-05 00:00:00

Per-channel PPV price override, for admins running multiple source
channels priced differently (e.g. multi-part files priced lower than
complete bundles). Nullable, not defaulted to 0 — a channel with no
override still falls back to the global default_ppv_price setting; only
an explicit number here (including 0.0 for "always free from this
channel") changes that. Existing channels all start with no override,
so nothing changes in pricing behaviour until an admin actively sets one.

Verified: applied on top of head, an existing channel defaulted to NULL
(not 0), downgrade drops the column cleanly, re-upgrade restores it.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8e8bf205399c"
down_revision: Union[str, None] = "eb340c2c27f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("custom_ppv_price", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("channels") as batch_op:
        batch_op.drop_column("custom_ppv_price")
