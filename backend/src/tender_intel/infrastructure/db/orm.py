"""SQLAlchemy 2.0 ORM models.

Kept separate from the domain entities so the domain stays framework-free;
:mod:`tender_intel.infrastructure.repositories.mappers` converts between the two.

Conventions:
* Primary keys are UUIDs.
* Money is ``Numeric(20, 2)`` and quantities/rates ``Numeric(20, 4)`` — exact
  decimal end to end, never float.
* Enums are stored as their string value (portable across Postgres and the
  SQLite used in tests).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tender_intel.infrastructure.db.base import Base, TimestampMixin, UTCDateTime

MONEY = Numeric(20, 2)
QUANTITY = Numeric(20, 4)


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    # PBKDF2 hash for manual (email/password) sign-in; NULL for a Google-only account.
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class RoleAssignmentModel(Base):
    """Pre-provisioned elevation, keyed by normalised email.

    ``assigned_by`` is nullable: the bootstrap row is seeded by a migration and
    has no administrator behind it.
    """

    __tablename__ = "role_assignments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32))
    assigned_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    consumed_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )


class UserSessionModel(Base):
    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class TenderModel(TimestampMixin, Base):
    __tablename__ = "tenders"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tender_number: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    estimated_value: Mapped[Decimal | None] = mapped_column(MONEY)
    closing_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(String(512))

    documents: Mapped[list[TenderDocumentModel]] = relationship(
        back_populates="tender", cascade="all, delete-orphan"
    )


class TenderDocumentModel(TimestampMixin, Base):
    __tablename__ = "tender_documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tender_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenders.id", ondelete="CASCADE"), index=True
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(String(512))
    file_path: Mapped[str | None] = mapped_column(String(1024))
    file_size: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    downloaded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    raw_text: Mapped[str | None] = mapped_column(Text)

    tender: Mapped[TenderModel] = relationship(back_populates="documents")


class TenderMetadataModel(TimestampMixin, Base):
    __tablename__ = "tender_metadata"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tender_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenders.id", ondelete="CASCADE"), unique=True, index=True
    )
    # {field: {"value": <serialised|null>, "confidence": float, "source": str|null}}
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_text: Mapped[str] = mapped_column(Text, default="")


class BOQItemModel(Base):
    __tablename__ = "boq_items"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tender_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenders.id", ondelete="CASCADE"), index=True
    )
    item_number: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[Decimal | None] = mapped_column(QUANTITY)
    unit_rate: Mapped[Decimal | None] = mapped_column(QUANTITY)
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    category: Mapped[str | None] = mapped_column(String(255), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(default=0.0)


class PastProjectModel(TimestampMixin, Base):
    __tablename__ = "past_projects"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(1024))
    client: Mapped[str | None] = mapped_column(String(512))
    work_value: Mapped[Decimal | None] = mapped_column(MONEY, index=True)
    category: Mapped[str | None] = mapped_column(String(255), index=True)
    location: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    completion_date: Mapped[date | None] = mapped_column(Date)
    embedding_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Letter-of-award reference, the identifier the portfolio workbook keys on.
    # Stored verbatim alongside its normalised form so reconciliation matches on
    # a canonical key while the source string stays visible.
    loa_reference: Mapped[str | None] = mapped_column(String(255))
    loa_reference_normalised: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True
    )
    # The completion-certificate test (feature spec §3) has to tell a blank date
    # from a non-date entry such as "Running". A nullable Date cannot hold the
    # second, so the raw string is kept beside it and the test is simply whether
    # the date is present.
    completion_certificate_date: Mapped[date | None] = mapped_column(Date)
    completion_certificate_note: Mapped[str | None] = mapped_column(String(64))


class TenderReviewModel(Base):
    __tablename__ = "tender_reviews"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tender_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenders.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # CORRECTION or VERDICT. Indexed because the platform statistics and the
    # staleness lookup both filter on it.
    kind: Mapped[str] = mapped_column(String(16), index=True)
    # NULL on a CORRECTION record.
    verdict: Mapped[str | None] = mapped_column(String(32))
    comments: Mapped[str | None] = mapped_column(Text)
    before_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    after_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), index=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    diff: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


# --------------------------------------------------------------------------- #
# Eligibility screening (feature spec §7)
#
# Portable column types throughout: sa.JSON rather than JSONB, and association
# tables rather than array columns, so the integration suite keeps building the
# schema on in-memory SQLite.
# --------------------------------------------------------------------------- #
class WorkTypeModel(TimestampMixin, Base):
    __tablename__ = "work_types"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    # Deactivated, never deleted: a tag on a past project is historical evidence
    # and deleting the type it points at would erase why a tender matched.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class WorkTypeAliasModel(Base):
    """One surface form for a work type.

    ``alias_normalised`` is unique **globally**, not per work type. Two types
    behind one alias would make stage 1 of the cascade non-deterministic, so the
    constraint exists to fail a migration rather than resolve an ambiguity at
    runtime.
    """

    __tablename__ = "work_type_aliases"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    work_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_types.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(255))
    alias_normalised: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    alias_kind: Mapped[str] = mapped_column(String(16))


class PastProjectWorkTypeModel(Base):
    __tablename__ = "past_project_work_types"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("past_projects.id", ondelete="CASCADE"), primary_key=True
    )
    work_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_types.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    evidence: Mapped[str | None] = mapped_column(Text)


class CompanyTurnoverModel(Base):
    __tablename__ = "company_turnover"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    financial_year: Mapped[str] = mapped_column(String(9), unique=True, index=True)
    contractual_turnover: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    # No foreign key: there is no store for non-tender documents yet, so the
    # reference dangles until one exists.
    certificate_document_id: Mapped[UUID | None] = mapped_column(Uuid)
    recorded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime)


class TenderEligibilityModel(Base):
    __tablename__ = "tender_eligibility"

    tender_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenders.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), index=True)
    # Null on a criterion that could not be evaluated, which is distinct from
    # False. The difference is what routes a tender to REVIEW instead of NO_BID.
    financial_pass: Mapped[bool | None] = mapped_column(Boolean)
    financial_required: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    financial_actual: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    technical_pass: Mapped[bool | None] = mapped_column(Boolean)
    rule_satisfied: Mapped[str | None] = mapped_column(String(16))
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # Staleness is derived by comparing this against a freshly computed digest.
    # No stored flag, so nothing has to be remembered when inputs move.
    inputs_fingerprint: Mapped[str] = mapped_column(String(64))
    evaluated_at: Mapped[datetime] = mapped_column(UTCDateTime)


class TenderEligibilityWorkTypeModel(Base):
    __tablename__ = "tender_eligibility_work_types"

    tender_id: Mapped[UUID] = mapped_column(
        ForeignKey("tender_eligibility.tender_id", ondelete="CASCADE"), primary_key=True
    )
    work_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_types.id", ondelete="CASCADE"), primary_key=True
    )
    match_method: Mapped[str] = mapped_column(String(16))
    match_score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    match_grade: Mapped[str] = mapped_column(String(16))


class TenderEligibilityProjectModel(Base):
    __tablename__ = "tender_eligibility_projects"

    tender_id: Mapped[UUID] = mapped_column(
        ForeignKey("tender_eligibility.tender_id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("past_projects.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(Integer)
    work_value: Mapped[Decimal] = mapped_column(MONEY)


class PortfolioVersionModel(Base):
    """A single-row counter bumped by every portfolio mutation.

    It exists so the eligibility fingerprint invalidates without any mutation
    path needing to know the fingerprint exists.
    """

    __tablename__ = "portfolio_version"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    counter: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
