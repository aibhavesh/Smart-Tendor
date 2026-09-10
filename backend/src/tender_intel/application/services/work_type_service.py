"""Work-type taxonomy administration (feature spec §8).

ADMIN only. Types are deactivated, never deleted, because a tag on a past project
is historical evidence and removing the type it points at would erase why a
tender matched.

Every mutation bumps the portfolio counter, which is what makes a stored
eligibility result go stale without this service knowing the fingerprint exists.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from tender_intel.domain.decision.normalise import normalise_alias
from tender_intel.domain.entities import AuditLog
from tender_intel.domain.entities.work_type import (
    PastProjectWorkType,
    WorkType,
    WorkTypeAlias,
)
from tender_intel.domain.enums.work_type import (
    AliasKind,
    WorkTypeCategory,
    WorkTypeLinkSource,
)
from tender_intel.domain.exceptions import (
    DomainValidationError,
    DuplicateEntityError,
    EntityNotFoundError,
)
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    PastProjectRepository,
    PortfolioVersionRepository,
    WorkTypeRepository,
)
from tender_intel.domain.value_objects.pagination import Page, PageRequest


class WorkTypeService:
    def __init__(
        self,
        *,
        work_types: WorkTypeRepository,
        projects: PastProjectRepository,
        versions: PortfolioVersionRepository,
        audits: AuditLogRepository,
    ) -> None:
        self._work_types = work_types
        self._projects = projects
        self._versions = versions
        self._audits = audits

    # ------------------------------------------------------------------ #
    # Types
    # ------------------------------------------------------------------ #
    async def create(
        self,
        *,
        code: str,
        name: str,
        category: WorkTypeCategory,
        description: str | None,
        actor_id: UUID,
    ) -> WorkType:
        if await self._work_types.get_by_code(code) is not None:
            raise DuplicateEntityError("WorkType", "code", code)
        created = await self._work_types.add(
            WorkType(code=code, name=name, category=category, description=description)
        )
        await self._bump()
        await self._audit(actor_id, "work_type.create", created.id, {"code": code})
        return created

    async def get_or_404(self, work_type_id: UUID) -> WorkType:
        work_type = await self._work_types.get(work_type_id)
        if work_type is None:
            raise EntityNotFoundError("WorkType", work_type_id)
        return work_type

    async def list(
        self, page: PageRequest, *, category: str | None = None, is_active: bool | None = None
    ) -> Page[WorkType]:
        return await self._work_types.list(page, category=category, is_active=is_active)

    async def patch(
        self,
        work_type_id: UUID,
        *,
        name: str | None,
        category: WorkTypeCategory | None,
        description: str | None,
        actor_id: UUID,
    ) -> WorkType:
        work_type = await self.get_or_404(work_type_id)
        diff: dict[str, object] = {}
        for field, value in (
            ("name", name),
            ("category", category),
            ("description", description),
        ):
            if value is not None and getattr(work_type, field) != value:
                before = getattr(work_type, field)
                setattr(work_type, field, value)
                diff[field] = {"before": _plain(before), "after": _plain(value)}
        if not diff:
            return work_type
        updated = await self._work_types.update(work_type)
        await self._bump()
        await self._audit(actor_id, "work_type.update", work_type_id, diff)
        return updated

    async def deactivate(self, work_type_id: UUID, *, actor_id: UUID) -> WorkType:
        work_type = await self.get_or_404(work_type_id)
        if not work_type.is_active:
            return work_type
        work_type.deactivate()
        updated = await self._work_types.update(work_type)
        await self._bump()
        await self._audit(
            actor_id,
            "work_type.deactivate",
            work_type_id,
            {"is_active": {"before": True, "after": False}},
        )
        return updated

    # ------------------------------------------------------------------ #
    # Aliases
    # ------------------------------------------------------------------ #
    async def add_alias(
        self, work_type_id: UUID, *, alias: str, kind: AliasKind, actor_id: UUID
    ) -> WorkTypeAlias:
        """Attach a surface form.

        The normalised form is unique across the whole taxonomy, not per type:
        two types behind one alias would make the exact stage of the cascade
        non-deterministic, so a collision is refused rather than resolved.
        """
        await self.get_or_404(work_type_id)
        normalised = normalise_alias(alias)
        existing = await self._work_types.find_alias(normalised)
        if existing is not None:
            raise DuplicateEntityError("WorkTypeAlias", "alias_normalised", normalised)

        created = await self._work_types.add_alias(
            WorkTypeAlias(work_type_id=work_type_id, alias=alias, kind=kind)
        )
        await self._bump()
        await self._audit(
            actor_id, "work_type.alias_add", work_type_id, {"alias": alias, "kind": kind.value}
        )
        return created

    async def remove_alias(self, work_type_id: UUID, alias_id: UUID, *, actor_id: UUID) -> None:
        alias = await self._work_types.get_alias(alias_id)
        if alias is None or alias.work_type_id != work_type_id:
            raise EntityNotFoundError("WorkTypeAlias", alias_id)
        await self._work_types.delete_alias(alias_id)
        await self._bump()
        await self._audit(actor_id, "work_type.alias_remove", work_type_id, {"alias": alias.alias})

    # ------------------------------------------------------------------ #
    # Project tags
    # ------------------------------------------------------------------ #
    async def tag_project(
        self,
        project_id: UUID,
        work_type_id: UUID,
        *,
        source: WorkTypeLinkSource,
        confidence: Decimal | None,
        evidence: str | None,
        actor_id: UUID,
    ) -> PastProjectWorkType:
        if await self._projects.get(project_id) is None:
            raise EntityNotFoundError("PastProject", project_id)
        work_type = await self.get_or_404(work_type_id)
        if not work_type.is_active:
            raise DomainValidationError("cannot tag a project with a deactivated work type")

        tag = await self._work_types.add_tag(
            PastProjectWorkType(
                project_id=project_id,
                work_type_id=work_type_id,
                source=source,
                confidence=confidence,
                evidence=evidence,
            )
        )
        await self._bump()
        await self._audit(
            actor_id,
            "past_project.tag_add",
            project_id,
            {"work_type": work_type.code, "source": source.value},
            entity_type="PastProject",
        )
        return tag

    async def untag_project(self, project_id: UUID, work_type_id: UUID, *, actor_id: UUID) -> None:
        await self._work_types.delete_tag(project_id, work_type_id)
        await self._bump()
        await self._audit(
            actor_id,
            "past_project.tag_remove",
            project_id,
            {"work_type_id": str(work_type_id)},
            entity_type="PastProject",
        )

    # ------------------------------------------------------------------ #
    async def _bump(self) -> None:
        await self._versions.bump()

    async def _audit(
        self,
        actor_id: UUID,
        action: str,
        entity_id: UUID,
        diff: dict[str, object],
        *,
        entity_type: str = "WorkType",
    ) -> None:
        await self._audits.add(
            AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id),
                actor_id=actor_id,
                diff=diff,
            )
        )


def _plain(value: object) -> object:
    return value.value if isinstance(value, WorkTypeCategory) else value
