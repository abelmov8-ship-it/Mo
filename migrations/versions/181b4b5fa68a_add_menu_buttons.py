"""add menu_buttons table + seed today's static menu

Revision ID: 181b4b5fa68a
Revises: eda495e06ca3
Create Date: 2026-07-02 00:00:00

Makes the main menu database-driven. The seed data in upgrade() below is
not sample data — it's the exact 11 buttons that keyboards/user/main_menu.py
used to hardcode, in the same order, all REPLY type, all visible. That's
deliberate: a bot upgrading to this revision should look and behave
identically to before, until the admin actually opens Menu Builder and
changes something. "Get Free VIP" and "Share Bot" both point at the same
REFERRAL action, exactly as the two hardcoded buttons already did.

Admin Panel is NOT seeded here — it stays a hardcoded, always-visible
button for admins (see MenuButtonAction's docstring for why: it's the
admin's only way back into this very management screen, so it shouldn't
be able to hide or delete itself).

Verified in a sandbox run: applied on top of the current head, seed rows
inserted and readable back with the right action/order, downgrade drops
the table cleanly, re-upgrade reseeds correctly. Column order versus
create_all() differs the same way eda495e06ca3's does and for the same
reason — see that revision's docstring; not repeated here.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "181b4b5fa68a"
down_revision: Union[str, None] = "eda495e06ca3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED = [
    ("🔍 Search Any Movie", "SEARCH"),
    ("🎬 Movie Channels", "CHANNELS"),
    ("🔥 Trending & New", "TRENDING"),
    ("📢 Get Free VIP", "REFERRAL"),
    ("💎 VIP Package", "VIP_PACKAGE"),
    ("💳 Payment", "PAYMENT"),
    ("🎨 Photo Editor", "PHOTO_EDITOR"),
    ("👤 Profile", "PROFILE"),
    ("🌐 Language", "LANGUAGE"),
    ("🆘 Support", "SUPPORT"),
    ("📢 Share Bot", "REFERRAL"),
]


def upgrade() -> None:
    menu_buttons = op.create_table(
        "menu_buttons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "SEARCH", "CHANNELS", "TRENDING", "REFERRAL", "VIP_PACKAGE",
                "PAYMENT", "PHOTO_EDITOR", "PROFILE", "LANGUAGE", "SUPPORT",
                name="menubuttonaction",
            ),
            nullable=False,
        ),
        sa.Column(
            "keyboard_type",
            sa.Enum("REPLY", "INLINE", name="menubuttontype"),
            server_default="REPLY",
            nullable=False,
        ),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.bulk_insert(
        menu_buttons,
        [
            {
                "label": label,
                "action": action,
                "keyboard_type": "REPLY",
                "is_visible": True,
                "display_order": i,
            }
            for i, (label, action) in enumerate(_SEED)
        ],
    )


def downgrade() -> None:
    op.drop_table("menu_buttons")
