"""restore password authentication

Revision ID: 7690fc277a01
Revises: e7c3a5d18f92
Create Date: 2026-09-03 00:00:00.000000

Google authentication becomes optional: the platform now also supports
manual email/password sign-in (``POST /auth/register``, ``POST /auth/login``),
so the column ``b7f39d5a2e60`` dropped is needed again to store the hash.

The column is nullable, unlike the pre-drop schema's implicit expectation
that every row would eventually hold one: a Google-only account has no
password and none is required — ``hashed_password IS NULL`` simply means
"this account signs in with Google", exactly as ``google_sub IS NULL`` means
"this account signs in with a password". Nothing here touches existing rows;
every current user keeps their account, role and Google linkage untouched.

Batch mode is used so the same migration runs on the SQLite database the
migration tests use; on PostgreSQL it lowers to a plain ALTER TABLE.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7690fc277a01"
down_revision: str | None = "e7c3a5d18f92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("hashed_password", sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Drops every stored hash. A Google-linked account is unaffected — this
    # column was never what it signs in with — but any account that signs in
    # only with a password becomes unable to authenticate until it is either
    # re-registered or linked to Google.
    with op.batch_alter_table("users") as batch:
        batch.drop_column("hashed_password")
