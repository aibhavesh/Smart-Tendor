"""drop password authentication

Revision ID: b7f39d5a2e60
Revises: a1c4e07b91d2
Create Date: 2026-08-21 10:14:47.905311

Sign-in is Google-only: manual registration, credential login and the
password-reset flow have all been removed, so the column that stored bcrypt
hashes has nothing left writing to or reading from it.

DROPPING THIS COLUMN DESTROYS EVERY STORED PASSWORD HASH, IRREVERSIBLY. The
downgrade re-creates the column, but every row comes back NULL — a downgraded
database has the shape of the old schema and none of its credentials. There is
no path back to password sign-in without a fresh credential-setting flow.

Batch mode is used so the drop also runs on the SQLite database the migration
tests use; on PostgreSQL it lowers to a plain ALTER TABLE.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7f39d5a2e60"
down_revision: str | None = "a1c4e07b91d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("hashed_password")


def downgrade() -> None:
    # Restores the column, not the hashes. See the module docstring.
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("hashed_password", sa.String(length=255), nullable=True))
