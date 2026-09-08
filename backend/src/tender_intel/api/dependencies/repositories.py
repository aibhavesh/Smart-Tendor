"""Repository providers — construct request-scoped repositories from the session."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.api.dependencies.db import get_session
from tender_intel.infrastructure.repositories.audit_repo import SqlAlchemyAuditLogRepository
from tender_intel.infrastructure.repositories.project_repo import SqlAlchemyPastProjectRepository
from tender_intel.infrastructure.repositories.review_repo import SqlAlchemyTenderReviewRepository
from tender_intel.infrastructure.repositories.role_assignment_repo import (
    SqlAlchemyRoleAssignmentRepository,
)
from tender_intel.infrastructure.repositories.stats_repo import SqlAlchemyStatsRepository
from tender_intel.infrastructure.repositories.tender_repo import (
    SqlAlchemyBOQItemRepository,
    SqlAlchemyTenderDocumentRepository,
    SqlAlchemyTenderMetadataRepository,
    SqlAlchemyTenderRepository,
)
from tender_intel.infrastructure.repositories.user_repo import (
    SqlAlchemyUserRepository,
    SqlAlchemyUserSessionRepository,
)


def get_user_repo(session: AsyncSession = Depends(get_session)) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(session)


def get_role_assignment_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAlchemyRoleAssignmentRepository:
    return SqlAlchemyRoleAssignmentRepository(session)


def get_tender_repo(session: AsyncSession = Depends(get_session)) -> SqlAlchemyTenderRepository:
    return SqlAlchemyTenderRepository(session)


def get_tender_document_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAlchemyTenderDocumentRepository:
    return SqlAlchemyTenderDocumentRepository(session)


def get_tender_metadata_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAlchemyTenderMetadataRepository:
    return SqlAlchemyTenderMetadataRepository(session)


def get_boq_repo(session: AsyncSession = Depends(get_session)) -> SqlAlchemyBOQItemRepository:
    return SqlAlchemyBOQItemRepository(session)


def get_past_project_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAlchemyPastProjectRepository:
    return SqlAlchemyPastProjectRepository(session)


def get_tender_review_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAlchemyTenderReviewRepository:
    return SqlAlchemyTenderReviewRepository(session)


def get_stats_repo(session: AsyncSession = Depends(get_session)) -> SqlAlchemyStatsRepository:
    return SqlAlchemyStatsRepository(session)


def get_user_session_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAlchemyUserSessionRepository:
    return SqlAlchemyUserSessionRepository(session)


def get_audit_repo(session: AsyncSession = Depends(get_session)) -> SqlAlchemyAuditLogRepository:
    return SqlAlchemyAuditLogRepository(session)
