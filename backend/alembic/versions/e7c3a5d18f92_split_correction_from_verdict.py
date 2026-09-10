"""split correction from verdict

Revision ID: e7c3a5d18f92
Revises: d4a1e9c5b872
Create Date: 2026-08-21 14:32:09.771204

``tender_reviews`` becomes one record type discriminated by ``kind``. A
CORRECTION carries no verdict and decides nothing; a VERDICT is the bid
decision. ``verdict`` therefore becomes nullable.

BACKFILL. Every pre-existing row is set to ``kind='VERDICT'``. This is exact,
not a guess: the only writer of this table was ``POST /tenders/{id}/reviews``,
whose request schema required a verdict with no default, so no existing row
could be anything other than a decision.

DOWNGRADE IS LOSSY. The old schema has no column in which a correction could be
represented and ``verdict`` must go back to NOT NULL, so the downgrade
**deletes every CORRECTION row** before restoring the constraint. Correction
history does not survive a downgrade. There is no alternative short of leaving
``verdict`` nullable forever, which would defeat the constraint being restored.

No staleness column is added. Whether a verdict has been superseded is derived
by comparing it against ``tender_metadata.updated_at``, which already advances
on every correction via the ORM's ``onupdate``.

Batch mode is used so the same migration runs on the SQLite database the
migration tests drive; on PostgreSQL it lowers to plain ALTER TABLE.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7c3a5d18f92"
down_revision: str | None = "d4a1e9c5b872"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add nullable, so existing rows survive the DDL.
    with op.batch_alter_table("tender_reviews") as batch:
        batch.add_column(sa.Column("kind", sa.String(length=16), nullable=True))

    # 2. Backfill — see the module docstring for why VERDICT is exact.
    op.execute(sa.text("UPDATE tender_reviews SET kind = 'VERDICT' WHERE kind IS NULL"))

    # 3. Tighten kind, loosen verdict.
    with op.batch_alter_table("tender_reviews") as batch:
        batch.alter_column("kind", existing_type=sa.String(length=16), nullable=False)
        batch.alter_column("verdict", existing_type=sa.String(length=32), nullable=True)

    op.create_index(op.f("ix_tender_reviews_kind"), "tender_reviews", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tender_reviews_kind"), table_name="tender_reviews")

    # Corrections cannot be represented in the pre-split schema. See docstring.
    op.execute(sa.text("DELETE FROM tender_reviews WHERE kind = 'CORRECTION'"))

    with op.batch_alter_table("tender_reviews") as batch:
        batch.alter_column("verdict", existing_type=sa.String(length=32), nullable=False)
        batch.drop_column("kind")
