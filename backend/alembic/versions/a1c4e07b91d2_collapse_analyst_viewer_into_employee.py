"""collapse ANALYST and VIEWER into EMPLOYEE

Revision ID: a1c4e07b91d2
Revises: df21fab595ca
Create Date: 2026-08-21 10:12:04.118742

``users.role`` is a plain ``String(32)`` with no database-level enum type and no
CHECK constraint, so this is a data migration only — there is no type to alter.

DOWNGRADE IS LOSSY AND CANNOT BE MADE OTHERWISE. Two roles are being merged
into one, and nothing in the row records which of the two an account held
before the merge. The downgrade therefore maps every EMPLOYEE back to VIEWER —
the *lower* of the two — rather than guessing. Choosing VIEWER means a
downgrade under-grants instead of over-granting: former analysts lose the
ability to ingest tenders and run analysis until an administrator re-promotes
them by hand, which is a visible inconvenience rather than a silent privilege
escalation. Anyone downgrading must expect to re-promote those accounts.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e07b91d2"
down_revision: str | None = "df21fab595ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text("UPDATE users SET role = 'EMPLOYEE' WHERE role IN ('ANALYST', 'VIEWER')")
    )


def downgrade() -> None:
    # See the module docstring: the ANALYST/VIEWER split is unrecoverable.
    op.execute(sa.text("UPDATE users SET role = 'VIEWER' WHERE role = 'EMPLOYEE'"))
