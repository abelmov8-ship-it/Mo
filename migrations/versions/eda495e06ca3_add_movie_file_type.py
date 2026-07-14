"""add movies.file_type

Revision ID: eda495e06ca3
Revises: a7480ad88b78
Create Date: 2026-07-02 00:00:00

Adds MovieFileType (video/audio/document) so search/trending/PPV-unlock can
dispatch to the correct Telegram send_* method instead of always calling
answer_document. Every existing row was, until now, always delivered via
answer_document regardless of what it actually was — so DOCUMENT is the
behaviour-preserving default for pre-existing data, not a guess.

Actually run end to end in a sandbox (not just hand-checked):
  1. `alembic upgrade head` through a7480ad88b78 on a fresh sqlite file,
     then inserted a row to simulate pre-existing production data.
  2. This revision applied on top — the pre-existing row backfilled to
     file_type='DOCUMENT' correctly, no NULLs, no failure.
  3. `alembic downgrade a7480ad88b78` — column removed cleanly, the row's
     other data survived untouched.
  4. Re-upgraded, then diffed the resulting `movies` schema against one
     built by Base.metadata.create_all() from the current models.

That diff found one real, *expected* difference, worth recording here
instead of silently papering over: this migration's file_type column has
`DEFAULT 'DOCUMENT'` at the database level; create_all()'s does not.
That's correct, not a mismatch to fix — adding a NOT NULL column to a
table that already has rows requires a server-side default to backfill
them, which is exactly what op.add_column's server_default= does here.
create_all() only ever builds a brand-new, empty table, so it never hits
that constraint — new rows get their value from the model's `default=`
(Python/ORM-side, no DDL) at INSERT time instead. Column order in the
CREATE TABLE also differs (file_type lands at the end via ALTER instead
of inline); harmless, since SQLAlchemy always does named-column
INSERT/SELECT and never relies on positional order.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "eda495e06ca3"
down_revision: Union[str, None] = "a7480ad88b78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "movies",
        sa.Column(
            "file_type",
            sa.Enum("VIDEO", "AUDIO", "DOCUMENT", name="moviefiletype"),
            server_default="DOCUMENT",
            nullable=False,
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("movies") as batch_op:
        batch_op.drop_column("file_type")
