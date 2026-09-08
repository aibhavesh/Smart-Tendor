"""The organisation-domain admission gate."""

from __future__ import annotations

import pytest

from tender_intel.core.config import Environment, Settings
from tender_intel.domain.exceptions import ForbiddenDomainError
from tender_intel.domain.services.email_domain import (
    assert_org_email,
    is_excepted,
    normalize_email,
)

ORG = "maheshwaricomputers.com"
SECOND = "maheshwari-labs.com"
DOMAINS = [ORG, SECOND]


# --- Admission ---
def test_org_email_is_admitted():
    assert assert_org_email(f"asha@{ORG}", DOMAINS) == f"asha@{ORG}"


def test_second_configured_domain_is_admitted():
    assert assert_org_email(f"ravi@{SECOND}", DOMAINS) == f"ravi@{SECOND}"


@pytest.mark.parametrize(
    "address",
    [
        "someone@gmail.com",
        "someone@notorg.com",
        f"someone@{ORG}.evil.com",
        f"someone@not{ORG}",
    ],
)
def test_non_org_email_is_rejected(address: str):
    with pytest.raises(ForbiddenDomainError):
        assert_org_email(address, DOMAINS)


def test_subdomain_is_rejected():
    """Exact match only — no wildcarding, deliberately.

    ``sub.org.com`` is a domain the organisation may not control, and treating
    it as equivalent would let anyone who owns a subdomain mint accounts.
    """
    with pytest.raises(ForbiddenDomainError):
        assert_org_email(f"someone@sub.{ORG}", DOMAINS)


def test_empty_allowlist_rejects_everything():
    with pytest.raises(ForbiddenDomainError):
        assert_org_email(f"asha@{ORG}", [])


# --- Normalisation ---
@pytest.mark.parametrize(
    "raw",
    [
        f"ASHA@{ORG}",
        f"Asha@{ORG.upper()}",
        f"  asha@{ORG}  ",
        f"\tAsHa@{ORG}\n",
    ],
)
def test_case_and_whitespace_normalise(raw: str):
    assert assert_org_email(raw, DOMAINS) == f"asha@{ORG}"


def test_normalize_email_does_not_validate():
    assert normalize_email("  MiXeD@Example.COM ") == "mixed@example.com"


# --- Parsing edge cases ---
def test_split_is_on_the_last_at_sign():
    """``user@evil.com@notorg.com`` routes on ``notorg.com``, so that is what is judged."""
    with pytest.raises(ForbiddenDomainError):
        assert_org_email("user@evil.com@notorg.com", DOMAINS)

    # The same shape on the real domain is admitted, and keeps its odd local part.
    crafted = f"user@evil.com@{ORG}"
    assert assert_org_email(crafted, DOMAINS) == crafted


@pytest.mark.parametrize("address", ["", "   ", "no-at-sign", f"@{ORG}", "asha@", "@"])
def test_unroutable_addresses_are_rejected(address: str):
    with pytest.raises(ForbiddenDomainError):
        assert_org_email(address, DOMAINS)


# --- Config plumbing ---
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f"{ORG}", [ORG]),
        (f"{ORG},{SECOND}", [ORG, SECOND]),
        (f" {ORG.upper()} , {SECOND} ", [ORG, SECOND]),
        (f"@{ORG}", [ORG]),
        ("", []),
    ],
)
def test_allowed_domains_parse_from_a_comma_separated_string(raw: str, expected: list[str]):
    settings = Settings(
        environment=Environment.CI,
        jwt_secret="test-secret-value-that-is-long-enough-1234",
        allowed_email_domains=raw,
    )
    assert settings.allowed_email_domains == expected


# --- Individually named exceptions ---
EXCEPTION = "consultant@elsewhere.com"


def test_excepted_address_is_admitted_despite_its_domain():
    assert assert_org_email(EXCEPTION, DOMAINS, [EXCEPTION]) == EXCEPTION


def test_exception_is_per_address_not_per_domain():
    """Admitting one outsider must not admit everyone at their provider."""
    with pytest.raises(ForbiddenDomainError):
        assert_org_email("someone.else@elsewhere.com", DOMAINS, [EXCEPTION])


def test_exception_matching_normalises():
    assert assert_org_email(f"  {EXCEPTION.upper()}  ", DOMAINS, [EXCEPTION]) == EXCEPTION


def test_exceptions_do_not_bypass_the_routability_check():
    with pytest.raises(ForbiddenDomainError):
        assert_org_email("not-an-address", DOMAINS, ["not-an-address"])


def test_no_exceptions_by_default():
    with pytest.raises(ForbiddenDomainError):
        assert_org_email(EXCEPTION, DOMAINS)


def test_is_excepted_is_exact():
    assert is_excepted(EXCEPTION, [EXCEPTION]) is True
    assert is_excepted("other@elsewhere.com", [EXCEPTION]) is False
    assert is_excepted(EXCEPTION, []) is False


def test_exceptions_parse_from_a_comma_separated_string():
    settings = Settings(
        environment=Environment.CI,
        jwt_secret="test-secret-value-that-is-long-enough-1234",
        allowed_email_exceptions=f" {EXCEPTION.upper()} , second@other.com ",
    )
    assert settings.allowed_email_exceptions == [EXCEPTION, "second@other.com"]


def test_production_refuses_to_start_without_an_allowlist():
    from tender_intel.core.config import enforce_release_gates

    settings = Settings(
        environment=Environment.PRODUCTION,
        jwt_secret="a" * 40,
        cors_allow_origins=["https://app.example.com"],
        allowed_email_domains=[],
    )
    with pytest.raises(RuntimeError, match="ALLOWED_EMAIL_DOMAINS"):
        enforce_release_gates(settings)
