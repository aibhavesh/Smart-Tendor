"""The organisation-domain admission gate.

Sign-in is restricted to email addresses on a configured organisation domain,
plus a short list of individually named exceptions for people who must have
access without being on one. This is the *admission* half of account creation:
it decides whether an account may exist at all, and it runs before any User row
is written. The *elevation* half — which role the account is born with — is the
RoleAssignment lookup, and it only runs once admission has passed.

One function, called by every account-creation path. The normalised string it
returns is the one used for both the RoleAssignment lookup and the User row, so
the two can never diverge.
"""

from __future__ import annotations

from collections.abc import Sequence

from tender_intel.domain.exceptions import ForbiddenDomainError


def normalize_email(raw_email: str) -> str:
    """Trim and lowercase an address. No validation — see :func:`assert_org_email`."""
    return raw_email.strip().lower()


def is_excepted(normalized_email: str, allowed_exceptions: Sequence[str]) -> bool:
    """True when this exact address is individually admitted.

    Separate from the domain rule on purpose. Admitting one outsider by adding
    their provider to the domain list would admit everybody who shares it, so a
    named person gets a named exception.
    """
    return normalized_email in set(allowed_exceptions)


def assert_org_email(
    raw_email: str,
    allowed_domains: Sequence[str],
    allowed_exceptions: Sequence[str] = (),
) -> str:
    """Return the normalised address, or raise if it is not admitted.

    An address is admitted when it is listed individually in
    ``allowed_exceptions``, or when its domain is in ``allowed_domains``.

    The domain is taken from the **last** ``@`` so that a crafted local part
    such as ``user@evil.com@notorg.com`` is judged on ``notorg.com`` — the part
    a mail system would actually route on — rather than on ``evil.com``.

    Matching is exact in both lists. Subdomains are deliberately *not*
    wildcarded: with ``org.com`` configured, ``sub.org.com`` is rejected. Empty
    lists reject everything (fail-closed).
    """
    normalized = normalize_email(raw_email)
    local, separator, domain = normalized.rpartition("@")
    if not separator or not local or not domain:
        raise ForbiddenDomainError(f"not a routable email address: {raw_email!r}")
    if is_excepted(normalized, allowed_exceptions):
        return normalized
    if domain not in set(allowed_domains):
        raise ForbiddenDomainError(f"domain {domain!r} is not an allowed organisation domain")
    return normalized
