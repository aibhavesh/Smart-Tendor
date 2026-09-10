"""Phase 1 domain-logic tests: enums, transitions, value objects."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tender_intel.domain.entities.tender import Tender
from tender_intel.domain.enums.roles import UserRole
from tender_intel.domain.enums.tender_status import TenderStatus
from tender_intel.domain.exceptions import InvalidStatusTransitionError
from tender_intel.domain.value_objects.extracted_field import ExtractedField
from tender_intel.domain.value_objects.money import CRORE, LAKH, to_decimal
from tender_intel.domain.value_objects.pagination import Page, PageRequest
from tender_intel.domain.value_objects.unknown import UNKNOWN, is_known, is_unknown


# --- Role hierarchy ---
def test_role_hierarchy_ordering():
    assert UserRole.SUPER_ADMIN.can_act_as(UserRole.EMPLOYEE)
    assert UserRole.ADMIN.can_act_as(UserRole.MANAGER)
    assert UserRole.EMPLOYEE.can_act_as(UserRole.EMPLOYEE)
    assert not UserRole.EMPLOYEE.can_act_as(UserRole.ADMIN)
    assert not UserRole.MANAGER.can_act_as(UserRole.SUPER_ADMIN)


# --- Tender lifecycle transitions ---
@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (TenderStatus.REGISTERED, TenderStatus.DOWNLOADED, True),
        (TenderStatus.DOWNLOADED, TenderStatus.PARSED, True),
        (TenderStatus.PARSED, TenderStatus.ANALYZED, True),
        (TenderStatus.ANALYZED, TenderStatus.REVIEWED, True),
        (TenderStatus.REVIEWED, TenderStatus.ANALYZED, True),  # re-analysis after correction
        (TenderStatus.REGISTERED, TenderStatus.PARSED, False),  # cannot skip download
        (TenderStatus.REGISTERED, TenderStatus.ANALYZED, False),
        (TenderStatus.ARCHIVED, TenderStatus.REGISTERED, False),  # terminal
    ],
)
def test_tender_transition_rules(current, target, allowed):
    assert current.can_transition_to(target) is allowed


def test_tender_transition_to_enforced():
    t = Tender(tender_number="T-1", title="Road work")
    t.transition_to(TenderStatus.DOWNLOADED)
    assert t.status is TenderStatus.DOWNLOADED
    with pytest.raises(InvalidStatusTransitionError):
        t.transition_to(TenderStatus.REVIEWED)


# --- UNKNOWN convention ---
def test_unknown_guards():
    assert is_unknown(UNKNOWN)
    assert not is_known(UNKNOWN)
    assert is_known("value")
    assert not is_unknown("value")


# --- ExtractedField ---
def test_extracted_field_known_and_unknown():
    known = ExtractedField.known(Decimal("100"), 0.9, source="rule")
    assert known.is_known
    assert known.value == Decimal("100")
    unknown = ExtractedField.unknown(source="rule")
    assert not unknown.is_known
    assert unknown.confidence == 0.0


def test_extracted_field_rejects_bad_confidence():
    with pytest.raises(ValueError, match="confidence"):
        ExtractedField(value="x", confidence=1.5)


def test_extracted_field_unknown_must_have_zero_confidence():
    with pytest.raises(ValueError, match="UNKNOWN"):
        ExtractedField(value=UNKNOWN, confidence=0.5)


# --- Money ---
def test_to_decimal_avoids_float_artifacts():
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal("15000000") == Decimal("15000000")
    assert Decimal("100000") == LAKH
    assert Decimal("10000000") == CRORE


# --- Pagination ---
def test_page_request_validation():
    with pytest.raises(ValueError):
        PageRequest(limit=0)
    with pytest.raises(ValueError):
        PageRequest(offset=-1)


def test_page_has_more():
    page = Page(items=[1, 2], total=5, limit=2, offset=0)
    assert page.has_more
    last = Page(items=[5], total=5, limit=2, offset=4)
    assert not last.has_more
