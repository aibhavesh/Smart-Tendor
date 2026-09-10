"""Portfolio workbook coercion — the known dirty data in the real workbook.

Each case here is a shape the 7-year portfolio workbook actually contains. They
pin the reuse of the existing parsers rather than the parsers themselves: the
point is that the importer routes each hazard to the helper that already handles
it, and that money stays exact.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tender_intel.infrastructure.project_workbook import (
    PROJECT_HEADER_ALIASES,
    coerce_amount,
    coerce_date,
    coerce_text,
    collapse_whitespace,
    reference_key,
    split_certificate,
)

pytestmark = pytest.mark.regression


# --- LOA references: embedded newlines and trailing whitespace ---


def test_an_embedded_newline_collapses_to_one_space():
    assert collapse_whitespace("NTPC\nVindhyachal ") == "NTPC Vindhyachal"


def test_collapsing_preserves_case_because_the_reference_is_shown_to_people():
    assert collapse_whitespace("  ADI_Tele-07_1.13CR  ") == "ADI_Tele-07_1.13CR"


def test_the_two_ntpc_spellings_share_one_matching_key():
    # The exact pair that blocks the work-type seed loader. Both must reconcile
    # to the same key, or an imported project cannot match the seed reference.
    assert reference_key("NTPC\nVindhyachal ") == reference_key("NTPC Vindhyachal")


def test_the_matching_key_is_casefolded_but_the_stored_form_is_not():
    assert reference_key("TELE 22") == "tele 22"
    assert collapse_whitespace("TELE 22") == "TELE 22"


# --- Amounts: commas, currency, multipliers, trailing junk ---


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,23,45,678", Decimal("12345678")),
        ("Rs. 1,37,00,000", Decimal("13700000")),
        ("1.37 Cr.", Decimal("13700000")),
        ("94 Lakh", Decimal("9400000")),
        ("2.91CR", Decimal("29100000")),  # multiplier flush against the digits
        ("1.13CR", Decimal("11300000")),
    ],
)
def test_amount_shapes(raw, expected):
    assert coerce_amount(raw) == expected


@pytest.mark.parametrize("raw", ["61LC", "61 LC", "76LC"])
def test_an_unrecognised_unit_suffix_is_absent_not_a_bare_number(raw):
    """``LC`` is probably lakh — but probably is a factor of 100,000.

    Returning the bare 61 would record sixty-one rupees as evidence of a
    sixty-one lakh capability. Absence is reported by the importer and skipped
    by stage B; a silently wrong magnitude is neither.
    """
    assert coerce_amount(raw) is None


def test_trailing_junk_after_a_newline_is_ignored():
    assert coerce_amount("1,79,00,000\napprox as per LOA") == Decimal("17900000")


def test_an_amount_is_always_an_exact_decimal_never_a_float():
    parsed = coerce_amount("1,13,00,000")
    assert isinstance(parsed, Decimal)
    assert parsed == Decimal("11300000")


def test_a_numeric_cell_from_openpyxl_round_trips_through_its_shown_digits():
    # openpyxl hands back a float for a numeric cell. Building the Decimal from
    # the binary expansion would leak 0.1-style error into a money column.
    assert coerce_amount(11300000.0) == Decimal("11300000")
    assert isinstance(coerce_amount(11300000.0), Decimal)


def test_a_blank_amount_is_none_not_zero():
    # Zero would be a claim the company did work worth nothing; None is absence.
    assert coerce_amount(None) is None
    assert coerce_amount("") is None


def test_a_negative_amount_is_rejected():
    assert coerce_amount("-5000") is None


# --- Dates: real datetimes and text in several formats ---


@pytest.mark.parametrize(
    "raw",
    ["2024-03-31", "31/03/2024", "31-03-2024"],
)
def test_text_dates_parse(raw):
    assert coerce_date(raw) == date(2024, 3, 31)


def test_a_real_date_object_passes_through():
    assert coerce_date(date(2024, 3, 31)) == date(2024, 3, 31)


def test_unparseable_date_text_is_none_rather_than_a_guess():
    assert coerce_date("sometime in March") is None


# --- The completion-certificate column ---


def test_a_certificate_date_parses_and_carries_no_note():
    parsed, note = split_certificate("2024-03-31")
    assert parsed == date(2024, 3, 31)
    assert note is None


def test_running_is_kept_verbatim_with_no_date():
    # "Running" means the work is ongoing. Stage B reads a missing certificate
    # date as "not yet evidence", which is correct — but the reason must survive.
    parsed, note = split_certificate("Running")
    assert parsed is None
    assert note == "Running"


def test_a_blank_certificate_cell_yields_neither_date_nor_note():
    parsed, note = split_certificate(None)
    assert parsed is None
    assert note is None


def test_a_long_note_is_capped_to_the_column_width():
    parsed, note = split_certificate("x" * 200)
    assert parsed is None
    assert note is not None
    assert len(note) == 64


# --- Headings ---


def test_the_heading_map_covers_the_fields_stage_b_depends_on():
    targets = set(PROJECT_HEADER_ALIASES.values())
    assert {"name", "work_value", "completion_certificate_date", "loa_reference"} <= targets


def test_text_coercion_collapses_and_blanks_to_none():
    assert coerce_text("  Mumbai\nGPON ") == "Mumbai GPON"
    assert coerce_text("   ") is None
    assert coerce_text(None) is None
