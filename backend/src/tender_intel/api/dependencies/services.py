"""Application-service providers."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from tender_intel.api.dependencies.db import get_app_settings, get_session
from tender_intel.api.dependencies.providers import (
    get_downloader,
    get_embedding_provider,
    get_llm_provider,
    get_metadata_backend,
    get_storage,
    get_table_extractor,
    get_text_extractor,
    get_vector_store,
)
from tender_intel.api.dependencies.repositories import (
    get_audit_repo,
    get_boq_repo,
    get_past_project_repo,
    get_role_assignment_repo,
    get_stats_repo,
    get_tender_document_repo,
    get_tender_metadata_repo,
    get_tender_repo,
    get_tender_review_repo,
    get_user_repo,
    get_user_session_repo,
)
from tender_intel.application.services.admin_service import AdminService
from tender_intel.application.services.analyst_service import AnalystService
from tender_intel.application.services.auth_service import AuthService
from tender_intel.application.services.decision_service import DecisionService
from tender_intel.application.services.document_service import DocumentService
from tender_intel.application.services.extraction_service import ExtractionService
from tender_intel.application.services.matching_service import MatchingService
from tender_intel.application.services.past_project_service import PastProjectService
from tender_intel.application.services.platform_service import PlatformService
from tender_intel.application.services.review_service import ReviewService
from tender_intel.application.services.tender_service import TenderService
from tender_intel.core.config import Settings
from tender_intel.domain.interfaces.providers import (
    DocumentTextExtractor,
    EmbeddingProvider,
    LLMProvider,
    VectorStore,
)
from tender_intel.infrastructure.downloader import HttpxDownloader
from tender_intel.infrastructure.extraction.pdf_backends import PdfPlumberBOQExtractor
from tender_intel.infrastructure.extraction.rule_metadata import RuleBasedMetadataExtractor
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
from tender_intel.infrastructure.security.google import GoogleTokenVerifierImpl
from tender_intel.infrastructure.security.tokens import TokenService
from tender_intel.infrastructure.storage import LocalFileStorage


def get_token_service(settings: Settings = Depends(get_app_settings)) -> TokenService:
    return TokenService(settings)


def get_google_verifier(
    settings: Settings = Depends(get_app_settings),
) -> GoogleTokenVerifierImpl:
    return GoogleTokenVerifierImpl(settings.google_client_id)


def get_auth_service(
    users: SqlAlchemyUserRepository = Depends(get_user_repo),
    sessions: SqlAlchemyUserSessionRepository = Depends(get_user_session_repo),
    assignments: SqlAlchemyRoleAssignmentRepository = Depends(get_role_assignment_repo),
    audits: SqlAlchemyAuditLogRepository = Depends(get_audit_repo),
    tokens: TokenService = Depends(get_token_service),
    google: GoogleTokenVerifierImpl = Depends(get_google_verifier),
    settings: Settings = Depends(get_app_settings),
) -> AuthService:
    return AuthService(
        users=users,
        sessions=sessions,
        assignments=assignments,
        audits=audits,
        tokens=tokens,
        google=google,
        settings=settings,
    )


def get_document_service(
    tenders: SqlAlchemyTenderRepository = Depends(get_tender_repo),
    documents: SqlAlchemyTenderDocumentRepository = Depends(get_tender_document_repo),
    audits: SqlAlchemyAuditLogRepository = Depends(get_audit_repo),
    downloader: HttpxDownloader = Depends(get_downloader),
    storage: LocalFileStorage = Depends(get_storage),
) -> DocumentService:
    return DocumentService(
        tenders=tenders,
        documents=documents,
        audits=audits,
        downloader=downloader,
        storage=storage,
    )


def get_tender_service(
    tenders: SqlAlchemyTenderRepository = Depends(get_tender_repo),
    audits: SqlAlchemyAuditLogRepository = Depends(get_audit_repo),
    documents: DocumentService = Depends(get_document_service),
) -> TenderService:
    return TenderService(tenders=tenders, audits=audits, documents=documents)


def get_extraction_service(
    tenders: SqlAlchemyTenderRepository = Depends(get_tender_repo),
    documents: SqlAlchemyTenderDocumentRepository = Depends(get_tender_document_repo),
    metadata_repo: SqlAlchemyTenderMetadataRepository = Depends(get_tender_metadata_repo),
    boq_repo: SqlAlchemyBOQItemRepository = Depends(get_boq_repo),
    audits: SqlAlchemyAuditLogRepository = Depends(get_audit_repo),
    storage: LocalFileStorage = Depends(get_storage),
    text_extractor: DocumentTextExtractor = Depends(get_text_extractor),
    table_extractor: PdfPlumberBOQExtractor = Depends(get_table_extractor),
    metadata_backend: RuleBasedMetadataExtractor = Depends(get_metadata_backend),
) -> ExtractionService:
    return ExtractionService(
        tenders=tenders,
        documents=documents,
        metadata_repo=metadata_repo,
        boq_repo=boq_repo,
        audits=audits,
        storage=storage,
        text_extractor=text_extractor,
        table_extractor=table_extractor,
        metadata_backend=metadata_backend,
    )


def get_past_project_service(
    projects: SqlAlchemyPastProjectRepository = Depends(get_past_project_repo),
    audits: SqlAlchemyAuditLogRepository = Depends(get_audit_repo),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider),
    vectors: VectorStore = Depends(get_vector_store),
    text_extractor: DocumentTextExtractor = Depends(get_text_extractor),
    metadata_backend: RuleBasedMetadataExtractor = Depends(get_metadata_backend),
    settings: Settings = Depends(get_app_settings),
) -> PastProjectService:
    return PastProjectService(
        projects=projects,
        audits=audits,
        embeddings=embeddings,
        vectors=vectors,
        collection=settings.qdrant_collection,
        text_extractor=text_extractor,
        metadata_backend=metadata_backend,
    )


def get_matching_service(
    tenders: SqlAlchemyTenderRepository = Depends(get_tender_repo),
    metadata_repo: SqlAlchemyTenderMetadataRepository = Depends(get_tender_metadata_repo),
    projects: SqlAlchemyPastProjectRepository = Depends(get_past_project_repo),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider),
    vectors: VectorStore = Depends(get_vector_store),
    settings: Settings = Depends(get_app_settings),
) -> MatchingService:
    return MatchingService(
        tenders=tenders,
        metadata_repo=metadata_repo,
        projects=projects,
        embeddings=embeddings,
        vectors=vectors,
        collection=settings.qdrant_collection,
    )


def get_decision_service(
    tenders: SqlAlchemyTenderRepository = Depends(get_tender_repo),
    metadata_repo: SqlAlchemyTenderMetadataRepository = Depends(get_tender_metadata_repo),
    projects: SqlAlchemyPastProjectRepository = Depends(get_past_project_repo),
    matching: MatchingService = Depends(get_matching_service),
    audits: SqlAlchemyAuditLogRepository = Depends(get_audit_repo),
    settings: Settings = Depends(get_app_settings),
) -> DecisionService:
    return DecisionService(
        tenders=tenders,
        metadata_repo=metadata_repo,
        projects=projects,
        matching=matching,
        audits=audits,
        settings=settings,
    )


def get_analyst_service(
    decision: DecisionService = Depends(get_decision_service),
    tenders: SqlAlchemyTenderRepository = Depends(get_tender_repo),
    llm: LLMProvider = Depends(get_llm_provider),
) -> AnalystService:
    return AnalystService(decision=decision, tenders=tenders, llm=llm)


def get_review_service(
    reviews: SqlAlchemyTenderReviewRepository = Depends(get_tender_review_repo),
    tenders: SqlAlchemyTenderRepository = Depends(get_tender_repo),
    metadata_repo: SqlAlchemyTenderMetadataRepository = Depends(get_tender_metadata_repo),
    audits: SqlAlchemyAuditLogRepository = Depends(get_audit_repo),
) -> ReviewService:
    return ReviewService(
        reviews=reviews, tenders=tenders, metadata_repo=metadata_repo, audits=audits
    )


def get_admin_service(
    users: SqlAlchemyUserRepository = Depends(get_user_repo),
    sessions: SqlAlchemyUserSessionRepository = Depends(get_user_session_repo),
    assignments: SqlAlchemyRoleAssignmentRepository = Depends(get_role_assignment_repo),
    audits: SqlAlchemyAuditLogRepository = Depends(get_audit_repo),
    settings: Settings = Depends(get_app_settings),
) -> AdminService:
    return AdminService(
        users=users,
        sessions=sessions,
        assignments=assignments,
        audits=audits,
        settings=settings,
    )


def get_platform_service(
    stats: SqlAlchemyStatsRepository = Depends(get_stats_repo),
    session: AsyncSession = Depends(get_session),
    vectors: VectorStore = Depends(get_vector_store),
) -> PlatformService:
    return PlatformService(stats=stats, session=session, vectors=vectors)
