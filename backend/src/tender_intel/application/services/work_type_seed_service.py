"""Load the work-type seed into the database (feature spec §6).

Two passes, blocked on different things:

* **Types and aliases** key on ``code`` and reconcile against nothing, so they
  load as soon as the seed file exists.
* **Project tags** reconcile each LOA reference against ``past_projects``, which
  needs the portfolio loaded with its LOA references first.

The loader never guesses. A reference that matches no project aborts the whole
run and names it, rather than dropping the tag quietly — a silently missing tag
is a capability the company can no longer evidence, and nothing downstream would
report it.

Two hazards it cannot detect on its own, which is why ``plan()`` exists and why
the script defaults to reporting before writing:

* One reference naming two different real projects. ``Mumbai`` is the known
  instance. Nothing in the seed distinguishes them, so the reconciliation report
  has to be read by a person.
* Two references collapsing to one key under normalisation. ``NTPC Vindhyachal``
  and ``NTPC\\nVindhyachal `` are the known instance; this one *is* detected and
  reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from tender_intel.domain.decision.normalise import normalise_alias
from tender_intel.domain.entities import AuditLog
from tender_intel.domain.entities.work_type import (
    PastProjectWorkType,
    WorkType,
    WorkTypeAlias,
)
from tender_intel.domain.enums.work_type import WorkTypeLinkSource
from tender_intel.domain.exceptions import DomainValidationError
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    PastProjectRepository,
    PortfolioVersionRepository,
    WorkTypeRepository,
)
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest
from tender_intel.infrastructure.observability.logging import get_logger
from tender_intel.infrastructure.seed.work_type_seed import WorkTypeSeed

_log = get_logger(__name__)


@dataclass(slots=True)
class SeedPlan:
    """What a load would do, computed without writing anything."""

    work_types_created: int = 0
    work_types_existing: int = 0
    aliases_created: int = 0
    aliases_existing: int = 0
    #: Raw LOA reference -> the project name it resolves to. Read this before
    #: committing: a reference naming the wrong project looks identical to one
    #: naming the right project.
    resolved: dict[str, str] = field(default_factory=dict)
    #: References matching no project. Blocking.
    unmatched: list[str] = field(default_factory=list)
    #: Distinct raw references sharing one normalised key. Blocking.
    collisions: dict[str, list[str]] = field(default_factory=dict)
    tags_to_create: int = 0

    @property
    def can_load_tags(self) -> bool:
        return not self.unmatched and not self.collisions

    def describe(self) -> str:
        lines = [
            f"work types : {self.work_types_created} to create, "
            f"{self.work_types_existing} already present",
            f"aliases    : {self.aliases_created} to create, "
            f"{self.aliases_existing} already present",
            f"project tags: {self.tags_to_create} to create, "
            f"{len(self.resolved)} reference(s) resolved",
        ]
        if self.collisions:
            lines.append("")
            lines.append("BLOCKED — references sharing one normalised key:")
            for key, refs in sorted(self.collisions.items()):
                lines.append(f"  {key!r} <- {', '.join(repr(r) for r in refs)}")
        if self.unmatched:
            lines.append("")
            lines.append("BLOCKED — references matching no past project:")
            lines.extend(f"  {ref!r}" for ref in sorted(self.unmatched))
        if self.resolved:
            lines.append("")
            lines.append("Reconciliation — check each pairing before committing:")
            for ref, name in sorted(self.resolved.items()):
                lines.append(f"  {ref!r} -> {name}")
        return "\n".join(lines)


@dataclass(slots=True)
class SeedOutcome:
    work_types_created: int = 0
    aliases_created: int = 0
    tags_created: int = 0
    tags_skipped: bool = False


class WorkTypeSeedService:
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
    async def plan(self, seed: WorkTypeSeed) -> SeedPlan:
        """Compute what a load would do. Writes nothing."""
        plan = SeedPlan(collisions=seed.normalisation_collisions())

        for entry in seed.work_types:
            if await self._work_types.get_by_code(entry.code) is None:
                plan.work_types_created += 1
            else:
                plan.work_types_existing += 1
            for alias in entry.aliases:
                if await self._work_types.find_alias(alias.normalised) is None:
                    plan.aliases_created += 1
                else:
                    plan.aliases_existing += 1

        by_key = await self._projects_by_loa()
        for ref in seed.distinct_project_refs:
            project = by_key.get(normalise_alias(ref))
            if project is None:
                plan.unmatched.append(ref)
            else:
                plan.resolved[ref] = project[1]
        plan.tags_to_create = seed.link_count if plan.can_load_tags else 0
        return plan

    async def load(
        self, seed: WorkTypeSeed, *, actor_id: UUID | None = None, types_only: bool = False
    ) -> SeedOutcome:
        """Load the seed. Idempotent — re-running changes nothing already present.

        Raises before writing anything when the tag pass cannot reconcile, unless
        ``types_only`` is set, which loads the first pass alone.
        """
        plan = await self.plan(seed)
        if not types_only and not plan.can_load_tags:
            raise DomainValidationError(
                "seed cannot be reconciled against past_projects:\n" + plan.describe()
            )

        outcome = SeedOutcome(tags_skipped=types_only)
        by_code: dict[str, UUID] = {}

        for entry in seed.work_types:
            existing = await self._work_types.get_by_code(entry.code)
            if existing is None:
                created = await self._work_types.add(
                    WorkType(
                        code=entry.code,
                        name=entry.name,
                        category=entry.category,
                        description=entry.description,
                    )
                )
                by_code[entry.code] = created.id
                outcome.work_types_created += 1
            else:
                by_code[entry.code] = existing.id

            for alias in entry.aliases:
                if await self._work_types.find_alias(alias.normalised) is not None:
                    continue
                await self._work_types.add_alias(
                    WorkTypeAlias(
                        work_type_id=by_code[entry.code], alias=alias.alias, kind=alias.kind
                    )
                )
                outcome.aliases_created += 1

        if not types_only:
            by_key = await self._projects_by_loa()
            for entry in seed.work_types:
                for ref in entry.project_refs:
                    project = by_key[normalise_alias(ref)]
                    await self._work_types.add_tag(
                        PastProjectWorkType(
                            project_id=project[0],
                            work_type_id=by_code[entry.code],
                            source=WorkTypeLinkSource.SEED,
                            evidence=f"portfolio workbook reference {ref!r}",
                        )
                    )
                    outcome.tags_created += 1

        # One bump and one audit entry for the whole load: it is a single act,
        # and a per-row trail would bury the fact that a seed ran at all.
        await self._versions.bump()
        await self._audits.add(
            AuditLog(
                action="work_type.seed_load",
                entity_type="WorkType",
                actor_id=actor_id,
                diff={
                    "source": seed.source,
                    "version": seed.version,
                    "work_types_created": outcome.work_types_created,
                    "aliases_created": outcome.aliases_created,
                    "tags_created": outcome.tags_created,
                    "types_only": types_only,
                },
            )
        )
        _log.info(
            "work_type.seed_loaded",
            work_types=outcome.work_types_created,
            aliases=outcome.aliases_created,
            tags=outcome.tags_created,
        )
        return outcome

    # ------------------------------------------------------------------ #
    async def _projects_by_loa(self) -> dict[str, tuple[UUID, str]]:
        """Normalised LOA reference -> (project id, name).

        Normalising here is what absorbs the workbook's embedded newlines and
        trailing spaces, so ``"NTPC\\nVindhyachal "`` reconciles against a stored
        ``"NTPC Vindhyachal"``.
        """
        page = await self._projects.list(PageRequest(limit=MAX_LIMIT))
        return {
            normalise_alias(p.loa_reference): (p.id, p.name) for p in page.items if p.loa_reference
        }
