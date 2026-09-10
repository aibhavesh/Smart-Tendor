"""Input fingerprint and derived staleness (feature spec §7)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tender_intel.domain.decision.fingerprint import compute_fingerprint, is_stale

BASE = {
    "tender_value": Decimal("10000000"),
    "completion_years": Decimal("2"),
    "closing_date": date(2026, 4, 1),
    "turnover_years": [("2023-24", Decimal("1000")), ("2024-25", Decimal("2000"))],
    "portfolio_counter": 7,
}


def fp(**overrides) -> str:
    return compute_fingerprint(**{**BASE, **overrides})


def test_identical_inputs_hash_identically():
    assert fp() == fp()


def test_it_is_a_sha256_hex_digest():
    value = fp()
    assert len(value) == 64
    assert set(value) <= set("0123456789abcdef")


def test_tender_value_moves_it():
    assert fp(tender_value=Decimal("10000001")) != fp()


def test_completion_years_moves_it():
    assert fp(completion_years=Decimal("3")) != fp()


def test_closing_date_moves_it():
    assert fp(closing_date=date(2026, 4, 2)) != fp()


def test_a_turnover_figure_moves_it():
    changed = [("2023-24", Decimal("1001")), ("2024-25", Decimal("2000"))]
    assert fp(turnover_years=changed) != fp()


def test_adding_a_turnover_year_moves_it():
    added = [*BASE["turnover_years"], ("2025-26", Decimal("3000"))]
    assert fp(turnover_years=added) != fp()


def test_the_portfolio_counter_moves_it():
    # This is what makes every new mutation path invalidate for free.
    assert fp(portfolio_counter=8) != fp()


def test_turnover_order_does_not_matter():
    reversed_rows = list(reversed(BASE["turnover_years"]))
    assert fp(turnover_years=reversed_rows) == fp()


def test_unknowns_are_a_sentinel_not_an_empty_string():
    # An absent value and a blank one must not collide.
    assert fp(tender_value=None) != fp(tender_value=Decimal("0"))


def test_distinct_unknown_fields_do_not_collide():
    assert fp(tender_value=None) != fp(completion_years=None)


def test_decimal_precision_is_preserved():
    # 2 and 2.00 are equal as Decimals but are different recorded figures.
    assert fp(completion_years=Decimal("2.00")) != fp(completion_years=Decimal("2"))


def test_staleness_is_a_mismatch():
    current = fp()
    assert is_stale(current, current) is False
    assert is_stale(fp(portfolio_counter=8), current) is True


def test_a_result_with_no_fingerprint_reads_as_stale():
    assert is_stale(None, fp()) is True
