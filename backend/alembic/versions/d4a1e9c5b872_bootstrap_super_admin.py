"""bootstrap the first SUPER_ADMIN

Revision ID: d4a1e9c5b872
Revises: c2d8b6f4173a
Create Date: 2026-08-21 10:21:35.472980

The first SUPER_ADMIN cannot be assigned by an administrator who does not yet
exist, so it is seeded as a role assignment rather than as a user: the account
still has to be created by that person signing in with Google on the
organisation domain, and it is born SUPER_ADMIN when they do.

The address comes from ``BOOTSTRAP_SUPER_ADMIN_EMAIL`` — no real address is
committed here. When the variable is unset the migration is a no-op, so a
deployment that bootstraps by other means is unaffected.

Idempotent: the insert is guarded on the normalised email, so re-running
against a database that already holds the row (or an already-consumed one)
changes nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from tender_intel.core.config import get_settings

revision: str = "d4a1e9c5b872"
down_revision: str | None = "c2d8b6f4173a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _bootstrap_email() -> str | None:
    raw = get_settings().bootstrap_super_admin_email
    return raw.strip().lower() if raw and raw.strip() else None


def upgrade() -> None:
    email = _bootstrap_email()
    if email is None:
        return

    connection = op.get_bind()
    already_assigned = connection.execute(
        sa.text("SELECT 1 FROM role_assignments WHERE lower(email) = :email"),
        {"email": email},
    ).first()
    if already_assigned is not None:
        return

    # If the account already exists the elevation list no longer governs it —
    # seeding a row here would be dead weight that can never be consumed.
    already_a_user = connection.execute(
        sa.text("SELECT 1 FROM users WHERE lower(email) = :email"),
        {"email": email},
    ).first()
    if already_a_user is not None:
        return

    connection.execute(
        sa.text(
            "INSERT INTO role_assignments "
            "(id, email, role, assigned_by, assigned_at, consumed_at, consumed_user_id) "
            "VALUES (:id, :email, 'SUPER_ADMIN', NULL, :assigned_at, NULL, NULL)"
        ),
        {"id": str(uuid.uuid4()), "email": email, "assigned_at": datetime.now(UTC)},
    )


def downgrade() -> None:
    email = _bootstrap_email()
    if email is None:
        return
    # Only the unconsumed seed row is removed. Once an account has been created
    # from it the row is history and the role lives on the User record.
    op.get_bind().execute(
        sa.text(
            "DELETE FROM role_assignments "
            "WHERE lower(email) = :email AND consumed_at IS NULL AND assigned_by IS NULL"
        ),
        {"email": email},
    )
