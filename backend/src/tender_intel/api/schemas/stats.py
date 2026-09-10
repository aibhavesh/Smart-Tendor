"""Response schema for the operational statistics surface."""

from __future__ import annotations

from pydantic import BaseModel

from tender_intel.application.dto.stats import OperationalStats


class OperationalStatsResponse(BaseModel):
    tenders_total: int
    tenders_by_status: dict[str, int]
    past_projects_total: int
    reviews_pending: int

    @classmethod
    def from_dto(cls, s: OperationalStats) -> OperationalStatsResponse:
        return cls(
            tenders_total=s.tenders_total,
            tenders_by_status=s.tenders_by_status,
            past_projects_total=s.past_projects_total,
            reviews_pending=s.reviews_pending,
        )
