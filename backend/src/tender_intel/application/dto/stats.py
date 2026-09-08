"""Operational statistics available to any authenticated user.

Distinct from ``PlatformStats`` in :mod:`tender_intel.application.dto.admin`, which
carries user and account figures and stays ADMIN-only. Everything here is an aggregate
over data the caller can already page through via ``GET /tenders`` and ``GET /projects``,
so exposing it at the lowest role level discloses nothing new — it only saves the client from
issuing one request per status to count them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OperationalStats:
    tenders_total: int
    tenders_by_status: dict[str, int]
    past_projects_total: int
    #: Tenders analysed but not yet reviewed — the same definition the pending
    #: review queue uses (``ReviewService.pending``), kept in one place so the
    #: dashboard count and the queue can never disagree.
    reviews_pending: int
