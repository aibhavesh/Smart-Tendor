"""Model registry — aggregates every ORM model so Alembic autogenerate and
``Base.metadata.create_all`` see the full schema from a single import.
"""

from __future__ import annotations

from tender_intel.infrastructure.db.base import Base
from tender_intel.infrastructure.db.orm import (
    AuditLogModel,
    BOQItemModel,
    CompanyTurnoverModel,
    PastProjectModel,
    PastProjectWorkTypeModel,
    PortfolioVersionModel,
    RoleAssignmentModel,
    TenderDocumentModel,
    TenderEligibilityModel,
    TenderEligibilityProjectModel,
    TenderEligibilityWorkTypeModel,
    TenderMetadataModel,
    TenderModel,
    TenderReviewModel,
    UserModel,
    UserSessionModel,
    WorkTypeAliasModel,
    WorkTypeModel,
)

__all__ = [
    "AuditLogModel",
    "BOQItemModel",
    "Base",
    "CompanyTurnoverModel",
    "PastProjectModel",
    "PastProjectWorkTypeModel",
    "PortfolioVersionModel",
    "RoleAssignmentModel",
    "TenderDocumentModel",
    "TenderEligibilityModel",
    "TenderEligibilityProjectModel",
    "TenderEligibilityWorkTypeModel",
    "TenderMetadataModel",
    "TenderModel",
    "TenderReviewModel",
    "UserModel",
    "UserSessionModel",
    "WorkTypeAliasModel",
    "WorkTypeModel",
]
