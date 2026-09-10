"""Outcome precedence — a definite failure beats an unknown input.

Feature spec §4. Marked ``regression``: this is what keeps an undecidable tender
out of NOT_ELIGIBLE and a decidable failure out of INDETERMINATE.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from tender_intel.domain.decision.eligibility import (
    CandidateProject,
    EligibilityEngine,
    EligibilityInput,
    TurnoverYear,
    WorkTypeMatch,
)
from tender_intel.domain.enums.eligibility import EligibilityStatus, MatchGrade, MatchMethod
from tender_intel.domain.services.financial_year import FinancialYear

pytestmark = pytest.mark.regression

CRORE = Decimal("10000000")
CLOSING = date(2026, 4, 1)
TYPE_A = uuid4()


def match(grade: MatchGrade) -> list[WorkTypeMatch]:
    return [WorkTypeMatch(TYPE_A, "OFC_CABLE_SUPPLY", MatchMethod.EXACT, Decimal("1.0"), grade)]


def good_project() -> CandidateProject:
    return CandidateProject(
        project_id=uuid4(),
        name="Qualifying work",
        work_value=CRORE,
        completion_certificate_date=date(2024, 6, 1),
        work_type_ids=frozenset({TYPE_A}),
    )


def build(
    *,
    value=CRORE,
    years=Decimal("2"),
    closing=CLOSING,
    turnover="99999999",
    rows=3,
    grade=MatchGrade.MATCHED,
    candidates=None,
    taxonomy_size=5,
) -> EligibilityInput:
    return EligibilityInput(
        tender_value=value,
        completion_years=years,
        closing_date=closing,
        turnover_years=[
            TurnoverYear(FinancialYear(2022 + i), Decimal(turnover)) for i in range(rows)
        ],
        matches=match(grade),
        candidates=[good_project()] if candidates is None else candidates,
        taxonomy_size=taxonomy_size,
    )


def status(**kwargs) -> EligibilityStatus:
    return EligibilityEngine().evaluate(build(**kwargs)).status


def test_everything_clear_is_eligible():
    assert status() is EligibilityStatus.ELIGIBLE


def test_a_financial_failure_is_not_eligible():
    assert status(turnover="1") is EligibilityStatus.NOT_ELIGIBLE


def test_a_technical_failure_is_not_eligible():
    assert status(candidates=[]) is EligibilityStatus.NOT_ELIGIBLE


def test_an_unknown_input_alone_is_indeterminate():
    assert status(years=None) is EligibilityStatus.INDETERMINATE


def _with(data: EligibilityInput, **overrides) -> EligibilityInput:
    fields = {
        "tender_value": data.tender_value,
        "completion_years": data.completion_years,
        "closing_date": data.closing_date,
        "turnover_years": data.turnover_years,
        "matches": data.matches,
        "candidates": data.candidates,
        "taxonomy_size": data.taxonomy_size,
    }
    return EligibilityInput(**{**fields, **overrides})


def test_a_populated_taxonomy_that_matches_nothing_is_not_eligible():
    result = EligibilityEngine().evaluate(_with(build(), matches=[]))
    assert result.status is EligibilityStatus.NOT_ELIGIBLE


def test_an_unconfigured_taxonomy_is_indeterminate_not_a_refusal():
    # Nothing to match against is an unknown, not a failure. Treating it as a
    # failure would return NO_BID for every tender until an administrator has
    # populated the taxonomy — the same silent refusal rule 1b exists to stop.
    result = EligibilityEngine().evaluate(_with(build(), matches=[], taxonomy_size=0))
    assert result.status is EligibilityStatus.INDETERMINATE
    assert any("No work types are configured" in r for r in result.reasons)


def test_a_definite_failure_beats_an_unknown_value():
    # Stage A needs no tender value to fail outright, so an unknown value does
    # not rescue a tender the taxonomy cannot match at all.
    result = EligibilityEngine().evaluate(_with(build(value=None), matches=[]))
    assert result.status is EligibilityStatus.NOT_ELIGIBLE


def test_a_definite_financial_failure_beats_an_unknown_closing_date():
    assert status(turnover="1", closing=None) is EligibilityStatus.NOT_ELIGIBLE


def test_a_review_band_match_forces_indeterminate():
    # Stage A passes on a review-band hit, but the doubt propagates.
    assert status(grade=MatchGrade.REVIEW) is EligibilityStatus.INDETERMINATE


def test_a_review_band_match_still_builds_the_pool():
    result = EligibilityEngine().evaluate(build(grade=MatchGrade.REVIEW))
    assert result.technical_value.passed is True
    assert result.matched_work_types


def test_too_few_turnover_years_is_indeterminate_not_a_refusal():
    # This is the failure mode rule 1b exists to keep visible: an empty turnover
    # table must reach a person, not return NO_BID for every tender.
    assert status(rows=0) is EligibilityStatus.INDETERMINATE


def test_reasons_carry_every_rule_that_did_not_pass():
    result = EligibilityEngine().evaluate(build(years=None))
    assert result.reasons
    assert any("Completion period is UNKNOWN" in r for r in result.reasons)


def test_an_eligible_result_carries_no_reasons():
    assert EligibilityEngine().evaluate(build()).reasons == []
