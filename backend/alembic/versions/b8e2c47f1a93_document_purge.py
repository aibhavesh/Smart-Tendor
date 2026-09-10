"""document purge marker for tender retirement

Revision ID: b8e2c47f1a93
Revises: a3f81b6c9d24
Create Date: 2026-09-10 16:40:00.000000

Bulk retirement of expired tenders purges the stored bytes and keeps the record.
This adds the one column that distinguishes the two reasons a ``file_path`` is
null: a document that was never downloaded, and a document whose bytes were
deliberately reclaimed.

Without the distinction the download worker cannot tell a purged document from a
pending one, and would re-fetch what an administrator just reclaimed.

``purged_at`` is nullable with no default and no backfill: every existing row
predates the feature and was, correctly, never purged. The downgrade drops the
column and with it the record of which documents were reclaimed; the files
themselves are already gone and are not recoverable either way.

``batch_alter_table`` so the same chain runs against the SQLite database the
migration tests use.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e2c47f1a93"
down_revision: str | Sequence[str] | None = "a3f81b6c9d24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tender_documents") as batch:
        batch.add_column(sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tender_documents") as batch:
        batch.drop_column("purged_at")
