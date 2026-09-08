"""Conversion between ORM models and pure-domain entities.

The metadata mapper (de)serialises each :class:`ExtractedField` into JSON,
preserving the UNKNOWN convention and exact ``Decimal`` values (stored as
strings so no float rounding occurs).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from tender_intel.domain.entities import (
    AuditLog,
    BOQItem,
    PastProject,
    RoleAssignment,
    Tender,
    TenderDocument,
    TenderMetadata,
    TenderReview,
    User,
    UserSession,
)
from tender_intel.domain.entities.metadata import METADATA_FIELDS
from tender_intel.domain.enums.document_status import DocumentStatus
from tender_intel.domain.enums.review import ReviewKind, ReviewVerdict
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.domain.value_objects.unknown import UNKNOWN, Maybe, is_known
from tender_intel.infrastructure.db.orm import (
    AuditLogModel,
    BOQItemModel,
    PastProjectModel,
    RoleAssignmentModel,
    TenderDocumentModel,
    TenderMetadataModel,
    TenderModel,
    TenderReviewModel,
    UserModel,
    UserSessionModel,
)

_DECIMAL_FIELDS = frozenset({"estimated_value", "emd_amount", "tender_fee"})
_DATE_FIELDS = frozenset({"closing_date"})


# --------------------------------------------------------------------------- #
# User / session
# --------------------------------------------------------------------------- #
def user_to_domain(m: UserModel) -> User:
    return User(
        id=m.id,
        email=m.email,
        full_name=m.full_name,
        role=UserRole(m.role),
        google_sub=m.google_sub,
        hashed_password=m.hashed_password,
        is_active=m.is_active,
        last_login_at=m.last_login_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def user_apply(m: UserModel, e: User) -> None:
    m.email = e.email
    m.full_name = e.full_name
    m.role = e.role.value
    m.google_sub = e.google_sub
    m.hashed_password = e.hashed_password
    m.is_active = e.is_active
    m.last_login_at = e.last_login_at


def user_to_model(e: User) -> UserModel:
    # created_at/updated_at are stamped from the domain entity, not left to the
    # column's DB-side default — every other entity in this module does the same
    # (see session_to_model, audit_to_model, review_to_model below). For User this
    # also sidesteps a real portability gap: the initial migration's server_default
    # is the Postgres-only ``now()``, which SQLite has no such function for, so a
    # local SQLite dev database would fail on every very first INSERT that omits
    # these columns. Explicit values make the column's default irrelevant on any
    # dialect and match what the entity already carries.
    m = UserModel(id=e.id, created_at=e.created_at, updated_at=e.updated_at)
    user_apply(m, e)
    return m


def role_assignment_to_domain(m: RoleAssignmentModel) -> RoleAssignment:
    return RoleAssignment(
        id=m.id,
        email=m.email,
        role=UserRole(m.role),
        assigned_by=m.assigned_by,
        assigned_at=m.assigned_at,
        consumed_at=m.consumed_at,
        consumed_user_id=m.consumed_user_id,
    )


def role_assignment_apply(m: RoleAssignmentModel, e: RoleAssignment) -> None:
    m.email = e.email
    m.role = e.role.value
    m.assigned_by = e.assigned_by
    m.assigned_at = e.assigned_at
    m.consumed_at = e.consumed_at
    m.consumed_user_id = e.consumed_user_id


def role_assignment_to_model(e: RoleAssignment) -> RoleAssignmentModel:
    m = RoleAssignmentModel(id=e.id)
    role_assignment_apply(m, e)
    return m


def session_to_domain(m: UserSessionModel) -> UserSession:
    return UserSession(
        id=m.id,
        user_id=m.user_id,
        refresh_token_hash=m.refresh_token_hash,
        ip_address=m.ip_address,
        user_agent=m.user_agent,
        expires_at=m.expires_at,
        revoked_at=m.revoked_at,
        created_at=m.created_at,
    )


def session_to_model(e: UserSession) -> UserSessionModel:
    return UserSessionModel(
        id=e.id,
        user_id=e.user_id,
        refresh_token_hash=e.refresh_token_hash,
        ip_address=e.ip_address,
        user_agent=e.user_agent,
        expires_at=e.expires_at,
        revoked_at=e.revoked_at,
        created_at=e.created_at,
    )


# --------------------------------------------------------------------------- #
# Tender / document
# --------------------------------------------------------------------------- #
def tender_to_domain(m: TenderModel) -> Tender:
    return Tender(
        id=m.id,
        tender_number=m.tender_number,
        title=m.title,
        status=TenderStatus(m.status),
        description=m.description,
        estimated_value=m.estimated_value,
        closing_date=m.closing_date,
        source_url=m.source_url,
        department=m.department,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def tender_apply(m: TenderModel, e: Tender) -> None:
    m.tender_number = e.tender_number
    m.title = e.title
    m.status = e.status.value
    m.description = e.description
    m.estimated_value = e.estimated_value
    m.closing_date = e.closing_date
    m.source_url = e.source_url
    m.department = e.department


def tender_to_model(e: Tender) -> TenderModel:
    m = TenderModel(id=e.id)
    tender_apply(m, e)
    return m


def document_to_domain(m: TenderDocumentModel) -> TenderDocument:
    return TenderDocument(
        id=m.id,
        tender_id=m.tender_id,
        source_url=m.source_url,
        file_name=m.file_name,
        file_path=m.file_path,
        file_size=m.file_size,
        mime_type=m.mime_type,
        sha256=m.sha256,
        status=DocumentStatus(m.status),
        attempt_count=m.attempt_count,
        last_error=m.last_error,
        downloaded_at=m.downloaded_at,
        raw_text=m.raw_text,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def document_apply(m: TenderDocumentModel, e: TenderDocument) -> None:
    m.tender_id = e.tender_id
    m.source_url = e.source_url
    m.file_name = e.file_name
    m.file_path = e.file_path
    m.file_size = e.file_size
    m.mime_type = e.mime_type
    m.sha256 = e.sha256
    m.status = e.status.value
    m.attempt_count = e.attempt_count
    m.last_error = e.last_error
    m.downloaded_at = e.downloaded_at
    m.raw_text = e.raw_text


def document_to_model(e: TenderDocument) -> TenderDocumentModel:
    m = TenderDocumentModel(id=e.id)
    document_apply(m, e)
    return m


# --------------------------------------------------------------------------- #
# Metadata (ExtractedField JSON)
# --------------------------------------------------------------------------- #
def _serialise_field(f: ExtractedField[Any]) -> dict[str, Any]:
    if not f.is_known:
        return {"value": None, "confidence": 0.0, "source": f.source}
    value = f.value
    if isinstance(value, Decimal):
        serialised: Any = str(value)
    elif isinstance(value, date):
        serialised = value.isoformat()
    else:
        serialised = value
    return {"value": serialised, "confidence": f.confidence, "source": f.source}


def _deserialise_field(name: str, data: dict[str, Any]) -> ExtractedField[Any]:
    raw = data.get("value")
    source = data.get("source")
    if raw is None:
        return ExtractedField.unknown(source=source)
    if name in _DECIMAL_FIELDS:
        value: Any = Decimal(str(raw))
    elif name in _DATE_FIELDS:
        value = date.fromisoformat(raw)
    else:
        value = raw
    return ExtractedField.known(value, float(data.get("confidence", 0.0)), source)


def metadata_to_domain(m: TenderMetadataModel) -> TenderMetadata:
    kwargs: dict[str, Any] = {"tender_id": m.tender_id, "id": m.id, "raw_text": m.raw_text}
    for name in METADATA_FIELDS:
        stored = m.fields.get(name) if m.fields else None
        kwargs[name] = _deserialise_field(name, stored) if stored else ExtractedField.unknown()
    kwargs["created_at"] = m.created_at
    kwargs["updated_at"] = m.updated_at
    return TenderMetadata(**kwargs)


def metadata_apply(m: TenderMetadataModel, e: TenderMetadata) -> None:
    m.tender_id = e.tender_id
    m.raw_text = e.raw_text
    m.fields = {name: _serialise_field(getattr(e, name)) for name in METADATA_FIELDS}
    # Persisted from the entity rather than left to the column's ``onupdate``:
    # the staleness comparison needs this on the same clock as TenderReview.
    m.updated_at = e.updated_at


def metadata_to_model(e: TenderMetadata) -> TenderMetadataModel:
    m = TenderMetadataModel(id=e.id)
    metadata_apply(m, e)
    return m


# --------------------------------------------------------------------------- #
# BOQ item (UNKNOWN <-> NULL)
# --------------------------------------------------------------------------- #
def _maybe_from_db(value: Decimal | None) -> Maybe[Decimal]:
    return UNKNOWN if value is None else value


def _maybe_to_db(value: Maybe[Decimal]) -> Decimal | None:
    return value if is_known(value) else None


def boq_to_domain(m: BOQItemModel) -> BOQItem:
    return BOQItem(
        id=m.id,
        tender_id=m.tender_id,
        item_number=m.item_number,
        description=m.description,
        unit=m.unit,
        quantity=_maybe_from_db(m.quantity),
        unit_rate=_maybe_from_db(m.unit_rate),
        amount=_maybe_from_db(m.amount),
        category=m.category,
        page_number=m.page_number,
        confidence=m.confidence,
    )


def boq_to_model(e: BOQItem) -> BOQItemModel:
    return BOQItemModel(
        id=e.id,
        tender_id=e.tender_id,
        item_number=e.item_number,
        description=e.description,
        unit=e.unit,
        quantity=_maybe_to_db(e.quantity),
        unit_rate=_maybe_to_db(e.unit_rate),
        amount=_maybe_to_db(e.amount),
        category=e.category,
        page_number=e.page_number,
        confidence=e.confidence,
    )


# --------------------------------------------------------------------------- #
# Past project / review / audit
# --------------------------------------------------------------------------- #
def past_project_to_domain(m: PastProjectModel) -> PastProject:
    return PastProject(
        id=m.id,
        name=m.name,
        client=m.client,
        work_value=m.work_value,
        category=m.category,
        location=m.location,
        description=m.description,
        completion_date=m.completion_date,
        embedding_indexed=m.embedding_indexed,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def past_project_apply(m: PastProjectModel, e: PastProject) -> None:
    m.name = e.name
    m.client = e.client
    m.work_value = e.work_value
    m.category = e.category
    m.location = e.location
    m.description = e.description
    m.completion_date = e.completion_date
    m.embedding_indexed = e.embedding_indexed


def past_project_to_model(e: PastProject) -> PastProjectModel:
    m = PastProjectModel(id=e.id)
    past_project_apply(m, e)
    return m


def review_to_domain(m: TenderReviewModel) -> TenderReview:
    return TenderReview(
        id=m.id,
        tender_id=m.tender_id,
        reviewer_id=m.reviewer_id,
        kind=ReviewKind(m.kind),
        verdict=ReviewVerdict(m.verdict) if m.verdict else None,
        comments=m.comments,
        before_snapshot=dict(m.before_snapshot),
        after_snapshot=dict(m.after_snapshot),
        created_at=m.created_at,
    )


def review_to_model(e: TenderReview) -> TenderReviewModel:
    return TenderReviewModel(
        id=e.id,
        tender_id=e.tender_id,
        reviewer_id=e.reviewer_id,
        kind=e.kind.value,
        verdict=e.verdict.value if e.verdict is not None else None,
        comments=e.comments,
        before_snapshot=e.before_snapshot,
        after_snapshot=e.after_snapshot,
        created_at=e.created_at,
    )


def audit_to_domain(m: AuditLogModel) -> AuditLog:
    return AuditLog(
        id=m.id,
        action=m.action,
        entity_type=m.entity_type,
        entity_id=m.entity_id,
        actor_id=m.actor_id,
        diff=dict(m.diff),
        ip_address=m.ip_address,
        user_agent=m.user_agent,
        created_at=m.created_at,
    )


def audit_to_model(e: AuditLog) -> AuditLogModel:
    return AuditLogModel(
        id=e.id,
        action=e.action,
        entity_type=e.entity_type,
        entity_id=e.entity_id,
        actor_id=e.actor_id,
        diff=e.diff,
        ip_address=e.ip_address,
        user_agent=e.user_agent,
        created_at=e.created_at,
    )
