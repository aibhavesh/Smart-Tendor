"""eligibility notification ledger

Revision ID: c9f5d38b2e71
Revises: b8e2c47f1a93
Create Date: 2026-09-10 17:20:00.000000

Records which tender was notified on which eligibility result, so a tender is
not re-sent every time the screen is re-evaluated.

The unique key is ``(tender_id, inputs_fingerprint)``, not ``tender_id`` alone.
The fingerprint already identifies the inputs a result was computed from, so
re-running the screen over unchanged inputs is silent, while a result that
genuinely changed — new turnover, a new past project, corrected metadata —
notifies again. That is the intended behaviour: the second result is news.

``recipients`` is a JSON array of the addresses actually resolved at send time,
kept because the recipient set changes as roles change and the question six
months from now is who received a given tender, not merely that a send occurred.

``sa.JSON`` rather than JSONB so the integration suite keeps building this
schema on in-memory SQLite.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9f5d38b2e71"
down_revision: str | Sequence[str] | None = "b8e2c47f1a93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eligibility_notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tender_id",
            sa.Uuid(),
            sa.ForeignKey("tenders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("inputs_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tender_id", "inputs_fingerprint", name="uq_eligibility_notification_inputs"
        ),
    )


def downgrade() -> None:
    op.drop_table("eligibility_notifications")
