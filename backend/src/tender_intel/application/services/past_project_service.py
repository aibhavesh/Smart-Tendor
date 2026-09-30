"""Past-project registry with embedding indexing (FR-220..FR-235).

Index-on-write: every create/update embeds the project and upserts it into the
vector store; deletes remove it. ``backfill`` re-indexes any projects that were
not indexed (e.g. created while the vector store was unavailable).
"""

from __future__ import annotations

from uuid import UUID

from tender_intel.application.dto.past_project import PastProjectCreate, PastProjectPatch
from tender_intel.domain.entities import AuditLog, PastProject
from tender_intel.domain.exceptions import EntityNotFoundError
from tender_intel.domain.interfaces.providers import EmbeddingProvider, VectorStore
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    PastProjectRepository,
)
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, Page, PageRequest
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
    "loa_reference",
    "completion_certificate_date",
    "completion_certificate_note",
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
    ) -> None:
        self._projects = projects
        self._audits = audits
        self._embeddings = embeddings
        self._vectors = vectors
        self._collection = collection

    async def create(self, data: PastProjectCreate, *, actor_id: UUID | None = None) -> PastProject:
        project = PastProject(
            name=data.name,
            client=data.client,
            work_value=data.work_value,
            category=data.category,
            location=data.location,
            description=data.description,
            completion_date=data.completion_date,
            loa_reference=data.loa_reference,
            completion_certificate_date=data.completion_certificate_date,
            completion_certificate_note=data.completion_certificate_note,
        )
        created = await self._projects.add(project)
        await self._index(created)
        await self._audit(actor_id, "past_project.create", created.id)
        return created

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

    async def delete_many(self, project_ids: list[UUID], *, actor_id: UUID | None = None) -> int:
        """Delete an explicitly selected set only when every ID still exists.

        Checking the complete selection before the first delete avoids a half-applied
        bulk operation when another user has already removed one of the projects.
        """
        unique_ids = list(dict.fromkeys(project_ids))
        projects = list(await self._projects.get_many(unique_ids))
        found_ids = {project.id for project in projects}
        missing = next((project_id for project_id in unique_ids if project_id not in found_ids), None)
        if missing is not None:
            raise EntityNotFoundError("PastProject", missing)

        for project in projects:
            await self._projects.delete(project.id)
            try:
                await self._vectors.delete(self._collection, project.id)
            except Exception as exc:
                _log.warning("past_project.vector_delete_failed", error=str(exc))
            await self._audit(actor_id, "past_project.delete", project.id)
        return len(projects)

    async def delete_all(self, *, actor_id: UUID | None = None) -> int:
        """Delete every registered past project in bounded batches.

        Each project still goes through the ordinary delete path so its vector
        embedding and audit record are handled consistently.
        """
        deleted = 0
        while True:
            batch = await self._projects.list(PageRequest(limit=MAX_LIMIT, offset=0))
            if not batch.items:
                return deleted
            deleted += await self.delete_many([project.id for project in batch.items], actor_id=actor_id)

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

    async def _audit(self, actor_id: UUID | None, action: str, project_id: UUID) -> None:
        await self._audits.add(
            AuditLog(
                action=action,
                entity_type="PastProject",
                entity_id=str(project_id),
                actor_id=actor_id,
            )
        )
