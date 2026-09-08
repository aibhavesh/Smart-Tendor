"""Semantic matching of the portfolio against a tender (FR-220..FR-235).

Retrieves the most similar past projects via the vector store, evaluates each
against the tender's numeric value constraint (crore/lakh aware) with explicit
reasons, and ranks eligible candidates first, then by descending similarity.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from tender_intel.application.dto.matching import MatchCandidate, MatchResult
from tender_intel.domain.entities import PastProject, TenderMetadata
from tender_intel.domain.exceptions import EntityNotFoundError
from tender_intel.domain.interfaces.providers import EmbeddingProvider, VectorStore
from tender_intel.domain.interfaces.repositories import (
    PastProjectRepository,
    TenderMetadataRepository,
    TenderRepository,
)
from tender_intel.infrastructure.extraction.constraints import parse_min_value


class MatchingService:
    def __init__(
        self,
        *,
        tenders: TenderRepository,
        metadata_repo: TenderMetadataRepository,
        projects: PastProjectRepository,
        embeddings: EmbeddingProvider,
        vectors: VectorStore,
        collection: str,
    ) -> None:
        self._tenders = tenders
        self._metadata_repo = metadata_repo
        self._projects = projects
        self._embeddings = embeddings
        self._vectors = vectors
        self._collection = collection

    async def match(self, tender_id: UUID, *, top_k: int = 10) -> MatchResult:
        tender = await self._tenders.get(tender_id)
        if tender is None:
            raise EntityNotFoundError("Tender", tender_id)
        metadata = await self._metadata_repo.get_for_tender(tender_id)

        query = self._build_query(tender.title, metadata)
        min_required = self._required_value(metadata)

        vectors = await self._embeddings.embed([query])
        await self._vectors.ensure_collection(self._collection, self._embeddings.dimension)
        matches = await self._vectors.search(self._collection, vectors[0], top_k)

        scores: dict[UUID, float] = {m.id: m.score for m in matches}
        projects = await self._projects.get_many(list(scores.keys()))

        candidates = [
            self._evaluate(project, scores.get(project.id, 0.0), min_required)
            for project in projects
        ]
        # Eligible first, then descending similarity.
        candidates.sort(key=lambda c: (not c.eligible, -c.similarity))
        return MatchResult(query=query, min_required_value=min_required, candidates=candidates)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_query(title: str, metadata: TenderMetadata | None) -> str:
        parts = [title]
        if metadata is not None:
            for name in ("work_name", "scope_of_work", "eligibility_criteria", "department"):
                field = getattr(metadata, name)
                if field.is_known:
                    parts.append(str(field.value))
        return " \n".join(p for p in parts if p)

    @staticmethod
    def _required_value(metadata: TenderMetadata | None) -> Decimal | None:
        if metadata is None:
            return None
        if metadata.eligibility_criteria.is_known:
            return parse_min_value(str(metadata.eligibility_criteria.value))
        return None

    @staticmethod
    def _evaluate(
        project: PastProject, similarity: float, min_required: Decimal | None
    ) -> MatchCandidate:
        reasons: list[str] = []
        eligible = True
        work_value = project.work_value

        if min_required is None:
            reasons.append("No explicit value criterion; matched by similarity.")
        elif work_value is None:
            eligible = False
            reasons.append(f"Work value unknown; cannot verify ≥ {min_required}.")
        elif work_value < min_required:
            eligible = False
            reasons.append(f"Work value {work_value} is below the required {min_required}.")
        else:
            reasons.append(f"Work value {work_value} meets the required minimum {min_required}.")

        return MatchCandidate(
            project_id=project.id,
            name=project.name,
            similarity=similarity,
            eligible=eligible,
            work_value=work_value,
            category=project.category,
            location=project.location,
            reasons=reasons,
        )
