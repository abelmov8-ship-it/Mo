"""add payments.reminder_sent_at + unique constraint on payments.reference

Revision ID: d8f9bf71f12c
Revises: 8e8bf205399c
Create Date: 2026-07-10 00:00:00

Two additions needed for Chapa webhook automation:
  - reminder_sent_at: lets the abandoned-payment-recovery job send exactly
    one nudge per unpaid checkout instead of re-nagging every time it runs.
  - a unique constraint on reference: Chapa tx_refs are already unique by
    construction (uuid4 per checkout), but a webhook is an untrusted network
    caller — this makes "two rows can never claim the same tx_ref" a DB
    guarantee instead of just an application assumption. SQLite (and every
    other backend) treats each NULL in a unique column as distinct, so
    existing bank-transfer rows (reference=NULL) are unaffected.

Caution before running on an existing production DB: if any duplicate
non-null `reference` values already exist (would only happen if the old
pre-webhook verify flow ever double-inserted under a race), this migration
fails fast rather than silently — reconcile those rows first.

Verified: applied on top of head, existing NULL-reference bank-transfer
payments untouched, reminder_sent_at defaults NULL for all existing rows,
downgrade drops both cleanly.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d8f9bf71f12c"
down_revision: Union[str, None] = "8e8bf205399c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint("uq_payments_reference", ["reference"])


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_constraint("uq_payments_reference", type_="unique")
        batch_op.drop_column("reminder_sent_at")
