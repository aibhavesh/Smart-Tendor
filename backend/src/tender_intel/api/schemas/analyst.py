"""AI Analyst report schema."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from tender_intel.application.dto.analyst import AnalystReport


class AnalystReportResponse(BaseModel):
    tender_id: UUID
    verdict: str
    win_probability: float
    confidence: float
    generated_by: str
    sections: dict[str, str]
    #: True when the tender's most recent recorded verdict predates a metadata
    #: correction. The prose below is regenerated per request from current data,
    #: so it is not itself stale — the recorded decision is.
    verdict_is_stale: bool = False

    @classmethod
    def from_report(
        cls, report: AnalystReport, *, verdict_is_stale: bool = False
    ) -> AnalystReportResponse:
        return cls(
            tender_id=report.tender_id,
            verdict=report.verdict.value,
            win_probability=float(report.win_probability),
            confidence=float(report.confidence),
            generated_by=report.generated_by,
            sections=report.sections,
            verdict_is_stale=verdict_is_stale,
        )
