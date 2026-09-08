"""Model registry — aggregates every ORM model so Alembic autogenerate and
``Base.metadata.create_all`` see the full schema from a single import.
"""

from __future__ import annotations

from tender_intel.infrastructure.db.base import Base
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

__all__ = [
    "AuditLogModel",
    "BOQItemModel",
    "Base",
    "PastProjectModel",
    "RoleAssignmentModel",
    "TenderDocumentModel",
    "TenderMetadataModel",
    "TenderModel",
    "TenderReviewModel",
    "UserModel",
    "UserSessionModel",
]
