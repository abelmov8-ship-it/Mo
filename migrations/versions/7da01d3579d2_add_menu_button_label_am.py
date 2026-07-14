"""add menu_buttons.label_am for bilingual main menu button labels

Revision ID: 7da01d3579d2
Revises: d8f9bf71f12c
Create Date: 2026-07-12 00:00:00

Nullable/optional by design, matching every other admin-editable text in
this codebase: NULL means "no Amharic override yet, falls back to the
existing label column" — which becomes the button's English/primary
value — not "no label at all." Every button created before this revision
gets label_am=NULL on upgrade, so it keeps behaving exactly as before
(same single label shown to every user) until an admin explicitly sets
an Amharic label for it via Menu Builder.

Not verified with a live `alembic upgrade head` run — this sandbox has no
network to install alembic/sqlalchemy. A single nullable ADD COLUMN is
about as low-risk as a migration gets, but please run it for real (and
`downgrade` back down once) before trusting this in production.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7da01d3579d2"
down_revision: Union[str, None] = "d8f9bf71f12c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("menu_buttons", sa.Column("label_am", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("menu_buttons", "label_am")
