"""Eligibility-screening thresholds — the regression contract.

Every constant here is product policy, not incidental implementation detail. Any
change to one of them changes the product's behaviour and must be treated as a
product decision.

``docs/eligibility-screening-spec.md`` §6 fixes the constant *set* — what is
present, and what has been retired. Provenance of each value is tagged:

* ``# Spec §x — specified``     the eligibility feature spec fixes this value.

The engine references this module — it never inlines a numeric literal (NFR-402:
exact ``Decimal`` throughout, constructed from strings). This module is structured
so it can later be swapped for an administrator-managed config provider (§17.3,
High roadmap) without hunting constants through the engine.

Native units are preserved to avoid translation error:
* confidence and work-type match scores: Decimal 0.0-1.0
* similar-work percentages: stored as the percentage number (e.g. ``60``),
  never as a fraction — the module never mixes ``60`` and ``0.60``.
* whole counts of days or financial years: ``int``
"""

from __future__ import annotations

from decimal import Decimal

# ===========================================================================
# Work-type match scoring (spec §3)
# ===========================================================================
#: Coverage at or above this grades the stage-A match MATCHED.
WORK_TYPE_MATCHED_MIN_INCLUSIVE = Decimal("0.70")  # Spec §3 — specified
#: Coverage at or above this (but below MATCHED) grades REVIEW.
WORK_TYPE_REVIEW_MIN_INCLUSIVE = Decimal("0.50")  # Spec §3 — specified
#: An exact code or alias hit scores full marks.
EXACT_MATCH_SCORE = Decimal("1.0")  # Spec §3 — specified

# ===========================================================================
# Similar-work value test (spec §3)
# ===========================================================================
#: How far back a past project may have been completed and still count.
SIMILAR_WORK_LOOKBACK_YEARS = 7  # Spec §3 — specified
SIMILAR_WORK_1_PCT = Decimal("60")  # 1 project worth 60% of tender value
SIMILAR_WORK_2_PCT = Decimal("40")  # 2 projects worth 40% each
SIMILAR_WORK_3_PCT = Decimal("30")  # 3 projects worth 30% each

# ===========================================================================
# Financial capacity (spec §2)
# ===========================================================================
#: Average turnover is taken over this many completed financial years. Fewer
#: recorded years is INDETERMINATE, never a pass and never a fail.
TURNOVER_AVERAGING_YEARS = 3  # Spec §2 — specified

# ===========================================================================
# Confidence (spec §7)
# ===========================================================================
#: Floor applied to the reported confidence, whatever the inputs say.
CONFIDENCE_MIN = Decimal("0.1")  # Spec §7 — specified (inclusive bound)
CONFIDENCE_MAX = Decimal("1.0")  # Spec §7 — specified (inclusive bound)

# ===========================================================================
# Parsing
# ===========================================================================
DAYS_PER_YEAR = 365  # Spec §1 — specified
