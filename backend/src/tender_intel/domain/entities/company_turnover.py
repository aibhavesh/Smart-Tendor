"""CA-certified contractual turnover, one record per financial year (spec §2).

These are *contractual* turnover figures taken from a Chartered Accountant's
certificate. They are not derived from balance sheets by automated extraction,
and they are not the same figure as Revenue from Operations — recording the wrong
one would understate or overstate the company against every tender at once.

An administrator maintains them, one row per year, with the certificate attached
and the change audited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from tender_intel.domain.exceptions import DomainValidationError
from tender_intel.domain.services.financial_year import FinancialYear, parse_label


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class CompanyTurnover:
    #: Financial-year label, e.g. ``2025-26``. Validated on construction so a
    #: malformed label can never reach the averaging window.
    financial_year: str
    contractual_turnover: Decimal
    #: The CA certificate backing this figure. Nullable: no store exists for
    #: non-tender documents yet, so the reference dangles until one does.
    certificate_document_id: UUID | None = None
    recorded_by: UUID | None = None
    recorded_at: datetime = field(default_factory=_now)
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        # Raises on a malformed label; the return is discarded because the label
        # string is what gets stored.
        parse_label(self.financial_year)
        if self.contractual_turnover < 0:
            raise DomainValidationError("contractual turnover cannot be negative")

    @property
    def year(self) -> FinancialYear:
        return parse_label(self.financial_year)
