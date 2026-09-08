"""Phase 4 rule-based metadata extraction tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tender_intel.infrastructure.extraction.rule_metadata import RuleBasedMetadataExtractor

SAMPLE = """
Name of Work: Construction of RCC Road in Ward 12
Estimated Cost: Rs. 1.5 Crore
EMD: Rs. 1,50,000
Tender Fee: Rs 5000
Last Date of Submission: 15/09/2026
Completion Period: 12 months
Location: Indore
Department: Public Works Department
"""


def test_extracts_known_fields_with_confidence():
    fields = RuleBasedMetadataExtractor().extract(SAMPLE)

    assert fields["work_name"].value == "Construction of RCC Road in Ward 12"
    assert fields["work_name"].confidence == 0.7
    assert fields["estimated_value"].value == Decimal("15000000")
    assert fields["emd_amount"].value == Decimal("150000")
    assert fields["tender_fee"].value == Decimal("5000")
    assert fields["closing_date"].value == date(2026, 9, 15)
    assert fields["completion_period"].value == "12 months"
    assert fields["location"].value == "Indore"
    assert "Public Works" in fields["department"].value


def test_absent_fields_are_unknown_not_guessed():
    fields = RuleBasedMetadataExtractor().extract("Name of Work: X")
    assert fields["work_name"].is_known
    assert not fields["eligibility_criteria"].is_known
    assert not fields["scope_of_work"].is_known
    assert fields["estimated_value"].confidence == 0.0


def test_empty_text_yields_all_unknown():
    fields = RuleBasedMetadataExtractor().extract("")
    assert all(not f.is_known for f in fields.values())


def test_unparseable_amount_stays_unknown():
    fields = RuleBasedMetadataExtractor().extract("Estimated Cost: to be decided")
    assert not fields["estimated_value"].is_known
