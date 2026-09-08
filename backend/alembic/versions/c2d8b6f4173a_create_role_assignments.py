"""create role_assignments

Revision ID: c2d8b6f4173a
Revises: b7f39d5a2e60
Create Date: 2026-08-21 10:17:22.640518

The pre-provisioned elevation list: the role an account is born with, keyed by
normalised email. Consulted once, at account creation, and never during
authorisation.

``assigned_by`` is nullable because the bootstrap row is seeded by a migration
and has no administrator behind it. Both user references are ON DELETE SET NULL
so deleting a user leaves the provisioning history intact rather than cascading
rows away.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d8b6f4173a"
down_revision: str | None = "b7f39d5a2e60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["users.id"],
            name=op.f("fk_role_assignments_assigned_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["consumed_user_id"],
            ["users.id"],
            name=op.f("fk_role_assignments_consumed_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_assignments")),
    )
    op.create_index(
        op.f("ix_role_assignments_email"), "role_assignments", ["email"], unique=True
    )
    op.create_index(
        op.f("ix_role_assignments_assigned_by"), "role_assignments", ["assigned_by"], unique=False
    )
    op.create_index(
        op.f("ix_role_assignments_consumed_user_id"),
        "role_assignments",
        ["consumed_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_role_assignments_consumed_user_id"), table_name="role_assignments")
    op.drop_index(op.f("ix_role_assignments_assigned_by"), table_name="role_assignments")
    op.drop_index(op.f("ix_role_assignments_email"), table_name="role_assignments")
    op.drop_table("role_assignments")
