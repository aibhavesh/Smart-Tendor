"""Eligibility screening orchestration (feature spec §1-§7).

Gathers what the engine needs, runs it, records the result with the fingerprint
of its inputs, and audits the evaluation. Every decision belongs to the pure
engine; this layer only fetches, converts and persists.

Stage 3 of the match cascade reuses the embeddings already written to the
past-project collection on every project write. Roughly thirty vectors are pulled
back and scored in process rather than issuing a similarity query, so no second
index exists and nothing has to be kept in sync.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from uuid import UUID

from tender_intel.domain.decision import thresholds as th
from tender_intel.domain.decision.duration import parse_years
from tender_intel.domain.decision.eligibility import (
    CandidateProject,
    EligibilityEngine,
    EligibilityInput,
    EligibilityResult,
    TurnoverYear,
    WorkTypeMatch,
)
from tender_intel.domain.decision.fingerprint import compute_fingerprint, is_stale
from tender_intel.domain.decision.normalise import tokenise
from tender_intel.domain.decision.work_type_match import (
    WorkTypeCandidate,
    match_work_types,
)
from tender_intel.domain.entities import AuditLog, PastProject, Tender, TenderMetadata
from tender_intel.domain.entities.eligibility import TenderEligibility
from tender_intel.domain.entities.work_type import WorkType, WorkTypeAlias
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.exceptions import DomainValidationError, EntityNotFoundError
from tender_intel.domain.interfaces.providers import EmbeddingProvider, VectorStore
from tender_intel.domain.interfaces.repositories import (
    AuditLogRepository,
    CompanyTurnoverRepository,
    PastProjectRepository,
    PortfolioVersionRepository,
    TenderEligibilityRepository,
    TenderMetadataRepository,
    TenderRepository,
    WorkTypeRepository,
)
from tender_intel.domain.services.financial_year import completed_years_before
from tender_intel.domain.value_objects.pagination import MAX_LIMIT, PageRequest
from tender_intel.domain.value_objects.unknown import is_known
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)

#: A tender must be extracted before it can be screened. Later states stay
#: screenable so a re-evaluation after a correction is possible.
_SCREENABLE = frozenset({TenderStatus.PARSED, TenderStatus.ANALYZED, TenderStatus.REVIEWED})


def cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity, guarding the zero vector the hash backend can emit."""
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


class EligibilityService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        metadata_repo: TenderMetadataRepository,
        projects: PastProjectRepository,
        work_types: WorkTypeRepository,
        turnover: CompanyTurnoverRepository,
        results: TenderEligibilityRepository,
        versions: PortfolioVersionRepository,
        audits: AuditLogRepository,
        embeddings: EmbeddingProvider,
        vectors: VectorStore,
        collection: str,
    ) -> None:
        self._tenders = tenders
        self._metadata_repo = metadata_repo
        self._projects = projects
        self._work_types = work_types
        self._turnover = turnover
        self._results = results
        self._versions = versions
        self._audits = audits
        self._embeddings = embeddings
        self._vectors = vectors
        self._collection = collection
        self._engine = EligibilityEngine()

    # ------------------------------------------------------------------ #
    async def screen(self, tender_id: UUID, *, actor_id: UUID | None = None) -> TenderEligibility:
        """Evaluate and persist. Replaces any previous result for the tender."""
        tender = await self._require_screenable(tender_id)
        metadata = await self._metadata_repo.get_for_tender(tender_id)

        data, fingerprint = await self._gather(tender, metadata)
        result = self._engine.evaluate(data)
        record = TenderEligibility.from_result(tender_id, result, fingerprint=fingerprint)

        stored = await self._results.upsert(record)
        await self._audit(actor_id, tender_id, record)
        _log.info("eligibility.screened", tender_id=str(tender_id), status=record.status.value)
        return stored

    async def get(self, tender_id: UUID) -> TenderEligibility:
        record = await self._results.get(tender_id)
        if record is None:
            raise EntityNotFoundError("TenderEligibility", tender_id)
        return record

    async def compute(self, tender_id: UUID) -> EligibilityResult:
        """Evaluate without persisting, for the decision path."""
        tender = await self._require_screenable(tender_id)
        metadata = await self._metadata_repo.get_for_tender(tender_id)
        data, _ = await self._gather(tender, metadata)
        return self._engine.evaluate(data)

    async def is_stale(self, tender_id: UUID) -> bool:
        """True when a stored result no longer describes the current inputs."""
        record = await self._results.get(tender_id)
        if record is None:
            return False
        tender = await self._tenders.get(tender_id)
        if tender is None:
            return False
        metadata = await self._metadata_repo.get_for_tender(tender_id)
        _, fingerprint = await self._gather(tender, metadata)
        return is_stale(record.inputs_fingerprint, fingerprint)

    # ------------------------------------------------------------------ #
    # Input gathering
    # ------------------------------------------------------------------ #
    async def _gather(
        self, tender: Tender, metadata: TenderMetadata | None
    ) -> tuple[EligibilityInput, str]:
        value = self._tender_value(tender, metadata)
        years = self._completion_years(metadata)
        closing = self._closing_date(tender, metadata)

        turnover_years = await self._turnover_window(closing)
        matches, candidates, taxonomy_size = await self._technical_inputs(tender, metadata)

        fingerprint = compute_fingerprint(
            tender_value=value,
            completion_years=years,
            closing_date=closing,
            turnover_years=[(t.year.label, t.amount) for t in turnover_years],
            portfolio_counter=await self._versions.current(),
        )
        data = EligibilityInput(
            tender_value=value,
            completion_years=years,
            closing_date=closing,
            turnover_years=turnover_years,
            matches=matches,
            candidates=candidates,
            taxonomy_size=taxonomy_size,
        )
        return data, fingerprint

    async def _turnover_window(self, closing: date | None) -> list[TurnoverYear]:
        """Certified turnover for the averaging window, oldest first.

        Returns fewer rows than the window when a year has no certificate. The
        engine reads that shortfall as indeterminate rather than averaging over
        whatever happens to exist.
        """
        if closing is None:
            return []
        window = completed_years_before(closing, th.TURNOVER_AVERAGING_YEARS)
        records = await self._turnover.list_for_years([y.label for y in window])
        by_label = {r.financial_year: r for r in records}
        return [
            TurnoverYear(year, by_label[year.label].contractual_turnover)
            for year in window
            if year.label in by_label
        ]

    async def _technical_inputs(
        self, tender: Tender, metadata: TenderMetadata | None
    ) -> tuple[list[WorkTypeMatch], list[CandidateProject], int]:
        active = await self._work_types.list_active()
        if not active:
            return [], [], 0

        tags = await self._work_types.list_tags()
        page = await self._projects.list(PageRequest(limit=MAX_LIMIT))
        projects = {p.id: p for p in page.items}

        types_by_project: dict[UUID, set[UUID]] = {}
        projects_by_type: dict[UUID, set[UUID]] = {}
        for tag in tags:
            types_by_project.setdefault(tag.project_id, set()).add(tag.work_type_id)
            projects_by_type.setdefault(tag.work_type_id, set()).add(tag.project_id)

        scope = self._scope_text(tender, metadata)
        semantic = await self._semantic_scores(scope, projects_by_type, projects)
        aliases = await self._work_types.list_aliases([wt.id for wt in active])

        candidates = [
            self._candidate(
                work_type,
                [a for a in aliases if a.work_type_id == work_type.id],
                projects_by_type.get(work_type.id, set()),
                projects,
                semantic.get(work_type.id),
            )
            for work_type in active
        ]
        matches = match_work_types(scope, candidates)

        pool = [
            CandidateProject(
                project_id=p.id,
                name=p.name,
                work_value=p.work_value,
                completion_certificate_date=p.completion_certificate_date,
                work_type_ids=frozenset(types_by_project.get(p.id, set())),
            )
            for p in projects.values()
            if types_by_project.get(p.id)
        ]
        return matches, pool, len(active)

    @staticmethod
    def _candidate(
        work_type: WorkType,
        aliases: list[WorkTypeAlias],
        project_ids: set[UUID],
        projects: dict[UUID, PastProject],
        semantic: Decimal | None,
    ) -> WorkTypeCandidate:
        bags = [frozenset(tokenise(a.alias)) for a in aliases]
        bags.append(tokenise(work_type.embedding_text()))
        for project_id in project_ids:
            project = projects.get(project_id)
            if project is not None and project.description:
                bags.append(tokenise(project.description))
        return WorkTypeCandidate(
            work_type_id=work_type.id,
            code=work_type.code,
            aliases=frozenset(a.normalised for a in aliases),
            token_bags=tuple(bag for bag in bags if bag),
            semantic_score=semantic,
        )

    async def _semantic_scores(
        self,
        scope: str,
        projects_by_type: dict[UUID, set[UUID]],
        projects: dict[UUID, PastProject],
    ) -> dict[UUID, Decimal]:
        """Best cosine between the tender scope and each type's tagged projects.

        Failures here degrade the stage rather than the screen: without a vector
        store the cascade simply stops after its two deterministic stages.
        """
        if not scope.strip() or not projects_by_type:
            return {}
        try:
            query = (await self._embeddings.embed([scope]))[0]
            records = await self._vectors.retrieve(self._collection, list(projects.keys()))
        except Exception as exc:  # pragma: no cover - defensive
            _log.warning("eligibility.semantic_unavailable", error=str(exc))
            return {}

        by_project = {r.id: r.vector for r in records}
        scores: dict[UUID, Decimal] = {}
        for type_id, project_ids in projects_by_type.items():
            best = max(
                (cosine(query, by_project[pid]) for pid in project_ids if pid in by_project),
                default=None,
            )
            if best is not None and best > 0:
                # Converted at the boundary, the same way DecisionService already
                # handles a match similarity.
                scores[type_id] = Decimal(str(round(best, 3)))
        return scores

    # ------------------------------------------------------------------ #
    # Field resolution — metadata is preferred, the tender record is fallback
    # ------------------------------------------------------------------ #
    @staticmethod
    def _tender_value(tender: Tender, metadata: TenderMetadata | None) -> Decimal | None:
        if metadata is not None and is_known(metadata.estimated_value.value):
            value = metadata.estimated_value.value
            if isinstance(value, Decimal):
                return value
        return tender.estimated_value

    @staticmethod
    def _completion_years(metadata: TenderMetadata | None) -> Decimal | None:
        if metadata is None or not metadata.completion_period.is_known:
            return None
        return parse_years(str(metadata.completion_period.value))

    @staticmethod
    def _closing_date(tender: Tender, metadata: TenderMetadata | None) -> date | None:
        if metadata is not None and is_known(metadata.closing_date.value):
            value = metadata.closing_date.value
            if isinstance(value, date):
                return value
        return tender.closing_date

    @staticmethod
    def _scope_text(tender: Tender, metadata: TenderMetadata | None) -> str:
        parts = [tender.title]
        if metadata is not None:
            for name in ("work_name", "scope_of_work", "eligibility_criteria", "department"):
                field = getattr(metadata, name)
                if field.is_known:
                    parts.append(str(field.value))
        return " \n".join(p for p in parts if p)

    # ------------------------------------------------------------------ #
    async def _require_screenable(self, tender_id: UUID) -> Tender:
        tender = await self._tenders.get(tender_id)
        if tender is None:
            raise EntityNotFoundError("Tender", tender_id)
        if tender.status not in _SCREENABLE:
            raise DomainValidationError(
                "tender must be extracted (PARSED) before it can be screened"
            )
        return tender

    async def _audit(
        self, actor_id: UUID | None, tender_id: UUID, record: TenderEligibility
    ) -> None:
        await self._audits.add(
            AuditLog(
                action="tender.eligibility_screen",
                entity_type="Tender",
                entity_id=str(tender_id),
                actor_id=actor_id,
                diff=record.snapshot(),
            )
        )
