"""Semantic-matching response schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from tender_intel.application.dto.matching import MatchResult


class MatchCandidateResponse(BaseModel):
    project_id: UUID
    name: str
    similarity: float
    eligible: bool
    work_value: str | None
    category: str | None
    location: str | None
    reasons: list[str]


class MatchResponse(BaseModel):
    query: str
    min_required_value: str | None
    candidates: list[MatchCandidateResponse]

    @classmethod
    def from_dto(cls, result: MatchResult) -> MatchResponse:
        return cls(
            query=result.query,
            min_required_value=(
                str(result.min_required_value) if result.min_required_value is not None else None
            ),
            candidates=[
                MatchCandidateResponse(
                    project_id=c.project_id,
                    name=c.name,
                    similarity=c.similarity,
                    eligible=c.eligible,
                    work_value=str(c.work_value) if c.work_value is not None else None,
                    category=c.category,
                    location=c.location,
                    reasons=c.reasons,
                )
                for c in result.candidates
            ],
        )
