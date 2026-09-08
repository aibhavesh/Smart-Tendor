"""Past-project registry with embedding indexing (FR-220..FR-235).

Index-on-write: every create/update embeds the project and upserts it into the
vector store; deletes remove it. ``backfill`` re-indexes any projects that were
not indexed (e.g. created while the vector store was unavailable).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from tender_intel.application.dto.past_project import PastProjectCreate, PastProjectPatch
from tender_intel.domain.entities import AuditLog, PastProject
from tender_intel.domain.exceptions import EntityNotFoundError
from tender_intel.domain.interfaces.providers import (
    DocumentTextExtractor,
    EmbeddingProvider,
    MetadataExtractionBackend,
    VectorStore,
)
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    PastProjectRepository,
)
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.domain.value_objects.unknown import is_known
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)

_PATCH_FIELDS = (
    "name",
    "client",
    "work_value",
    "category",
    "location",
    "description",
    "completion_date",
)


class PastProjectService:
    def __init__(
        self,
        *,
        projects: PastProjectRepository,
        audits: AuditLogRepository,
        embeddings: EmbeddingProvider,
        vectors: VectorStore,
        collection: str,
        text_extractor: DocumentTextExtractor,
        metadata_backend: MetadataExtractionBackend,
    ) -> None:
        self._projects = projects
        self._audits = audits
        self._embeddings = embeddings
        self._vectors = vectors
        self._collection = collection
        self._text_extractor = text_extractor
        self._metadata_backend = metadata_backend

    async def create(self, data: PastProjectCreate, *, actor_id: UUID | None = None) -> PastProject:
        project = PastProject(
            name=data.name,
            client=data.client,
            work_value=data.work_value,
            category=data.category,
            location=data.location,
            description=data.description,
            completion_date=data.completion_date,
        )
        created = await self._projects.add(project)
        await self._index(created)
        await self._audit(actor_id, "past_project.create", created.id)
        return created

    async def create_from_document(
        self,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None,
        overrides: PastProjectCreate | None = None,
        actor_id: UUID | None = None,
    ) -> PastProject:
        text = self._extract_text(content, mime_type, filename)
        fields = self._metadata_backend.extract(text)

        name = self._field_str(fields, "work_name") or filename
        work_value = self._field_decimal(fields, "estimated_value")
        location = self._field_str(fields, "location")

        if overrides is not None:
            name = overrides.name or name
            work_value = overrides.work_value if overrides.work_value is not None else work_value
            location = overrides.location or location

        data = PastProjectCreate(
            name=name,
            client=overrides.client if overrides else None,
            work_value=work_value,
            category=overrides.category if overrides else None,
            location=location,
            description=(overrides.description if overrides else None) or text[:1000],
            completion_date=overrides.completion_date if overrides else None,
        )
        return await self.create(data, actor_id=actor_id)

    async def get_or_404(self, project_id: UUID) -> PastProject:
        project = await self._projects.get(project_id)
        if project is None:
            raise EntityNotFoundError("PastProject", project_id)
        return project

    async def list(self, page: PageRequest) -> Page[PastProject]:
        return await self._projects.list(page)

    async def patch(
        self, project_id: UUID, data: PastProjectPatch, *, actor_id: UUID | None = None
    ) -> PastProject:
        project = await self.get_or_404(project_id)
        changed = False
        for name in _PATCH_FIELDS:
            value = getattr(data, name)
            if value is not None and getattr(project, name) != value:
                setattr(project, name, value)
                changed = True
        if not changed:
            return project
        project.embedding_indexed = False
        updated = await self._projects.update(project)
        await self._index(updated)
        await self._audit(actor_id, "past_project.update", project_id)
        return updated

    async def delete(self, project_id: UUID, *, actor_id: UUID | None = None) -> None:
        await self.get_or_404(project_id)
        await self._projects.delete(project_id)
        try:
            await self._vectors.delete(self._collection, project_id)
        except Exception as exc:
            _log.warning("past_project.vector_delete_failed", error=str(exc))
        await self._audit(actor_id, "past_project.delete", project_id)

    async def backfill(self, batch_size: int = 50) -> int:
        pending = await self._projects.list_unindexed(batch_size)
        for project in pending:
            await self._index(project)
        return len(pending)

    # ------------------------------------------------------------------ #
    async def _index(self, project: PastProject) -> None:
        vectors = await self._embeddings.embed([project.embedding_text()])
        await self._vectors.ensure_collection(self._collection, self._embeddings.dimension)
        await self._vectors.upsert(
            self._collection,
            project.id,
            vectors[0],
            {
                "name": project.name,
                "work_value": str(project.work_value) if project.work_value is not None else None,
                "category": project.category,
                "location": project.location,
            },
        )
        project.embedding_indexed = True
        await self._projects.update(project)

    def _extract_text(self, content: bytes, mime: str | None, filename: str) -> str:
        is_pdf = (mime and "pdf" in mime.lower()) or filename.lower().endswith(".pdf")
        if is_pdf:
            return self._text_extractor.extract_text(content)
        return content.decode("utf-8", errors="ignore")

    @staticmethod
    def _field_str(fields: dict[str, Any], name: str) -> str | None:
        field = fields.get(name)
        if field is not None and is_known(field.value):
            return str(field.value)
        return None

    @staticmethod
    def _field_decimal(fields: dict[str, Any], name: str) -> Decimal | None:
        field = fields.get(name)
        if field is None:
            return None
        value = field.value
        if is_known(value) and isinstance(value, Decimal):
            return value
        return None

    async def _audit(self, actor_id: UUID | None, action: str, project_id: UUID) -> None:
        await self._audits.add(
            AuditLog(
                action=action,
                entity_type="PastProject",
                entity_id=str(project_id),
                actor_id=actor_id,
            )
        )
