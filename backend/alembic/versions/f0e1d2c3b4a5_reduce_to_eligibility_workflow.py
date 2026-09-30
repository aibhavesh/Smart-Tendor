"""Remove data owned by retired application flows.

Revision ID: f0e1d2c3b4a5
Revises: c9f5d38b2e71
Create Date: 2026-09-26

The product is now limited to ingestion, extraction, and eligibility screening.
Review/verdict, notifications, and audit-history data are deliberately destroyed
with their retired routes. This migration is intentionally irreversible: a
downgrade cannot recreate deleted operational records honestly.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f0e1d2c3b4a5"
down_revision: str | Sequence[str] | None = "c9f5d38b2e71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("eligibility_notifications")
    op.drop_table("tender_reviews")
    op.drop_table("audit_logs")


def downgrade() -> None:
    raise NotImplementedError("Retired workflow data cannot be restored after deletion.")
