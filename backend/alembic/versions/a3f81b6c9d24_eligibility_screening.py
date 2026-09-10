"""eligibility screening

Revision ID: a3f81b6c9d24
Revises: 7690fc277a01
Create Date: 2026-09-10 08:15:00.000000

The tender eligibility screen (feature spec §7): a work-type taxonomy with
aliases, per-financial-year certified turnover, the screen's own result table,
and a portfolio counter the fingerprint reads.

Portable column types throughout — ``sa.JSON`` rather than ``JSONB``, and
association tables rather than array columns — so the integration suite keeps
building this schema on in-memory SQLite.

``work_type_aliases.alias_normalised`` is unique **globally**, not per work type.
Two types behind one alias would make stage 1 of the match cascade
non-deterministic and break auditability, so the constraint is here to fail a
migration rather than resolve an ambiguity at runtime.

The four columns added to ``past_projects`` are dropped by the downgrade along
with their data, which is not recoverable.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f81b6c9d24"
down_revision: str | None = "7690fc277a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_types")),
    )
    op.create_index(op.f("ix_work_types_code"), "work_types", ["code"], unique=True)
    op.create_index(op.f("ix_work_types_category"), "work_types", ["category"], unique=False)
    op.create_index(op.f("ix_work_types_is_active"), "work_types", ["is_active"], unique=False)

    op.create_table(
        "work_type_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("work_type_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("alias_normalised", sa.String(length=255), nullable=False),
        sa.Column("alias_kind", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["work_type_id"],
            ["work_types.id"],
            name=op.f("fk_work_type_aliases_work_type_id_work_types"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_type_aliases")),
    )
    op.create_index(
        op.f("ix_work_type_aliases_work_type_id"), "work_type_aliases", ["work_type_id"], unique=False
    )
    op.create_index(
        op.f("ix_work_type_aliases_alias_normalised"),
        "work_type_aliases",
        ["alias_normalised"],
        unique=True,
    )

    op.create_table(
        "past_project_work_types",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("work_type_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["past_projects.id"],
            name=op.f("fk_past_project_work_types_project_id_past_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["work_type_id"],
            ["work_types.id"],
            name=op.f("fk_past_project_work_types_work_type_id_work_types"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "work_type_id", name=op.f("pk_past_project_work_types")),
    )

    op.create_table(
        "company_turnover",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("financial_year", sa.String(length=9), nullable=False),
        sa.Column("contractual_turnover", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("certificate_document_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["users.id"],
            name=op.f("fk_company_turnover_recorded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_turnover")),
    )
    op.create_index(
        op.f("ix_company_turnover_financial_year"), "company_turnover", ["financial_year"], unique=True
    )
    op.create_index(
        op.f("ix_company_turnover_recorded_by"), "company_turnover", ["recorded_by"], unique=False
    )

    op.create_table(
        "tender_eligibility",
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("financial_pass", sa.Boolean(), nullable=True),
        sa.Column("financial_required", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("financial_actual", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("technical_pass", sa.Boolean(), nullable=True),
        sa.Column("rule_satisfied", sa.String(length=16), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("inputs_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_tender_eligibility_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tender_id", name=op.f("pk_tender_eligibility")),
    )
    op.create_index(op.f("ix_tender_eligibility_status"), "tender_eligibility", ["status"], unique=False)

    op.create_table(
        "tender_eligibility_work_types",
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("work_type_id", sa.Uuid(), nullable=False),
        sa.Column("match_method", sa.String(length=16), nullable=False),
        sa.Column("match_score", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("match_grade", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tender_eligibility.tender_id"],
            name=op.f("fk_tender_eligibility_work_types_tender_id_tender_eligibility"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["work_type_id"],
            ["work_types.id"],
            name=op.f("fk_tender_eligibility_work_types_work_type_id_work_types"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tender_id", "work_type_id", name=op.f("pk_tender_eligibility_work_types")
        ),
    )

    op.create_table(
        "tender_eligibility_projects",
        sa.Column("tender_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("work_value", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tender_eligibility.tender_id"],
            name=op.f("fk_tender_eligibility_projects_tender_id_tender_eligibility"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["past_projects.id"],
            name=op.f("fk_tender_eligibility_projects_project_id_past_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tender_id", "project_id", name=op.f("pk_tender_eligibility_projects")
        ),
    )

    op.create_table(
        "portfolio_version",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("counter", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_version")),
    )

    # Batch mode so the same migration runs on the SQLite database the migration
    # tests use; on PostgreSQL it lowers to plain ALTER TABLE statements.
    with op.batch_alter_table("past_projects") as batch:
        batch.add_column(sa.Column("loa_reference", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("loa_reference_normalised", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("completion_certificate_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("completion_certificate_note", sa.String(length=64), nullable=True))
    op.create_index(
        op.f("ix_past_projects_loa_reference_normalised"),
        "past_projects",
        ["loa_reference_normalised"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_past_projects_loa_reference_normalised"), table_name="past_projects")
    with op.batch_alter_table("past_projects") as batch:
        batch.drop_column("completion_certificate_note")
        batch.drop_column("completion_certificate_date")
        batch.drop_column("loa_reference_normalised")
        batch.drop_column("loa_reference")

    op.drop_table("portfolio_version")
    op.drop_table("tender_eligibility_projects")
    op.drop_table("tender_eligibility_work_types")
    op.drop_index(op.f("ix_tender_eligibility_status"), table_name="tender_eligibility")
    op.drop_table("tender_eligibility")
    op.drop_index(op.f("ix_company_turnover_recorded_by"), table_name="company_turnover")
    op.drop_index(op.f("ix_company_turnover_financial_year"), table_name="company_turnover")
    op.drop_table("company_turnover")
    op.drop_table("past_project_work_types")
    op.drop_index(op.f("ix_work_type_aliases_alias_normalised"), table_name="work_type_aliases")
    op.drop_index(op.f("ix_work_type_aliases_work_type_id"), table_name="work_type_aliases")
    op.drop_table("work_type_aliases")
    op.drop_index(op.f("ix_work_types_is_active"), table_name="work_types")
    op.drop_index(op.f("ix_work_types_category"), table_name="work_types")
    op.drop_index(op.f("ix_work_types_code"), table_name="work_types")
    op.drop_table("work_types")
