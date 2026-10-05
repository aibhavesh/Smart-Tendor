"""restore the audit trail

Revision ID: b1a4c7e2d903
Revises: f0e1d2c3b4a5
Create Date: 2026-09-27 10:15:00.000000

``f0e1d2c3b4a5`` dropped ``audit_logs`` along with the review and notification
tables. That was right for the tables those features owned, but the audit trail
is cross-cutting: the retained services still write to it, and the provider they
were given was a no-op sink, so roughly twenty ``_audit(...)`` call sites across
eleven services were silently discarding what they wrote. The system claimed an
audit trail it did not have.

This restores the table and makes the existing writes real. No service changes
are required — they were already correct.

``actor_id`` is a bare ``Uuid`` with **no foreign key**, deliberately. Every other
user-referencing column cascades or nulls on delete; an audit row that vanishes
with the user who caused it cannot answer "who did this", which is the only
question the table exists to answer. The trade-off is that orphan rows outlive
their actor, which is the correct direction for an append-only record.

The downgrade drops the table. That is genuinely destructive and is stated here
rather than left implicit: a rollback of this revision discards the audit
history, so it should never be run against a database whose audit record matters.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1a4c7e2d903"
down_revision: str | Sequence[str] | None = "f0e1d2c3b4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    # Filtered listing reads by actor, so the index is on the column itself and
    # deliberately not a composite: there is no second equality predicate to pair.
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_table("audit_logs")
