"""Stage A matching, and the linking of its confident results to a past project.

One implementation, used by two callers:

* :class:`~tender_intel.application.services.project_import_service.ProjectImportService`,
  which tags each row as it is created.
* ``scripts/backfill_work_type_tags.py``, which tags projects that were created
  while the taxonomy was empty.

They must not diverge. A project tagged by import and the same project tagged by
backfill have to be indistinguishable in the database — same ``INFERRED`` source,
same confidence, same evidence string — or a portfolio would end up with two kinds
of link depending on which path happened to run, and stage B could not explain
itself.

**Only confident matches are linked.** A ``REVIEW``-grade match is reported and
not written, because an asserted capability the company cannot evidence is worse
than an absent one: stage B would pool the project on the strength of a guess.

Linking goes through ``WorkTypeService.tag_project`` rather than the repository
directly, so the guard against a deactivated work type, the portfolio-counter bump
and the audit entry all still apply on this path.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from tender_intel.application.services.work_type_service import WorkTypeService
from tender_intel.domain.decision.normalise import tokenise
from tender_intel.domain.decision.work_type_match import WorkTypeCandidate, match_work_types
from tender_intel.domain.entities import PastProject
from tender_intel.domain.enums.eligibility import MatchGrade
from tender_intel.domain.enums.work_type import WorkTypeLinkSource
from tender_intel.domain.interfaces.repositories import WorkTypeRepository
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Tagging:
    """What the cascade concluded for one project."""

    linked: int
    considered: tuple[str, ...]


class WorkTypeTagger:
    def __init__(self, *, work_types: WorkTypeRepository, service: WorkTypeService) -> None:
        self._work_types = work_types
        self._service = service

    async def candidates(self) -> list[WorkTypeCandidate]:
        """Build the stage A candidate set.

        Empty when the taxonomy is empty. Callers provision the taxonomy *before*
        asking for this — see ``WorkTypeSeedService.ensure_taxonomy`` — because an
        empty result here is indistinguishable from "nothing matched", and
        reporting the latter when the truth is the former is how an entire
        portfolio ends up silently unlinked.
        """
        active = await self._work_types.list_active()
        if not active:
            return []
        aliases = await self._work_types.list_aliases([wt.id for wt in active])
        candidates: list[WorkTypeCandidate] = []
        for work_type in active:
            own = [a for a in aliases if a.work_type_id == work_type.id]
            bags = [frozenset(tokenise(a.alias)) for a in own]
            bags.append(tokenise(work_type.embedding_text()))
            candidates.append(
                WorkTypeCandidate(
                    work_type_id=work_type.id,
                    code=work_type.code,
                    aliases=frozenset(a.normalised for a in own),
                    token_bags=tuple(bag for bag in bags if bag),
                    semantic_score=None,
                )
            )
        return candidates

    async def tag(
        self,
        project: PastProject,
        candidates: list[WorkTypeCandidate],
        actor_id: UUID,
    ) -> Tagging:
        """Link every confidently matched work type to ``project``."""
        if not candidates:
            return Tagging(0, ())
        scope = " ".join(
            part
            for part in (project.name, project.category, project.description)
            if part is not None and part.strip()
        )
        if not scope.strip():
            return Tagging(0, ())

        linked = 0
        considered: list[str] = []
        for match in match_work_types(scope, candidates):
            if match.grade is MatchGrade.MATCHED:
                try:
                    await self._service.tag_project(
                        project.id,
                        match.work_type_id,
                        source=WorkTypeLinkSource.INFERRED,
                        confidence=match.score,
                        evidence=f"bulk import: {match.method.value} match on project name",
                        actor_id=actor_id,
                    )
                    linked += 1
                except Exception as exc:  # a tag failure is not an import failure
                    _log.warning(
                        "work_type.tag_failed",
                        project_id=str(project.id),
                        work_type=match.code,
                        error=str(exc),
                    )
            elif match.grade is MatchGrade.REVIEW:
                considered.append(f"{match.code} ({match.score})")
        return Tagging(linked, tuple(considered))


__all__ = ["Tagging", "WorkTypeTagger"]
