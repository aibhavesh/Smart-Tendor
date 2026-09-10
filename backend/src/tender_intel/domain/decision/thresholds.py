"""Decision-engine thresholds — the regression contract.

Every constant here is product policy, not incidental implementation detail. Any
change to one of them changes the product's behaviour and must be treated as a
product decision.

Two documents govern this module. ``docs/eligibility-screening-spec.md`` §6 fixes the
constant *set* — what is present, and what has been retired. For the values
themselves, the PRD governs the Section 13 constants and the feature spec governs the
eligibility constants. The provenance of each value is tagged:

* ``# PRD §13.x — specified``   the PRD fixes this value; use it exactly.
* ``# Spec §x — specified``     the eligibility feature spec fixes this value.
* ``# INFERRED — see C<n>``     a documented reading of an ambiguous PRD point.

The engines reference this module — they never inline a numeric literal
(FR-305 / NFR-402: exact ``Decimal`` throughout, constructed from strings). This
module is structured so it can later be swapped for an administrator-managed
config provider (§17.3, High roadmap) without hunting constants through the
engines.

Native units are preserved to avoid translation error:
* risk severity scores: Decimal on a 0-10 scale
* win probability: Decimal percentage points, clamped 10-95 (0 for NO_BID)
* confidence and work-type match scores: Decimal 0.0-1.0
* percentages of tender value: stored as the percentage number (e.g. ``10``),
  never as a fraction — the module never mixes ``10`` and ``0.10``.
* whole counts of days or financial years: ``int``
"""

from __future__ import annotations

from decimal import Decimal

from tender_intel.domain.enums.risk import RiskLevel

# 50 lakh, used by the short-completion HIGH rule. (1 lakh = 100_000.)
FIFTY_LAKH = Decimal("5000000")  # PRD §13.1 — specified

# ===========================================================================
# §13.1 — Risk engine
# ===========================================================================
# Severity → score on a 0-10 scale (FR-312 — specified).
RISK_HIGH_SCORE = Decimal("8.5")  # PRD §13.1 FR-312 — specified
RISK_MEDIUM_SCORE = Decimal("5.0")  # PRD §13.1 FR-312 — specified
RISK_LOW_SCORE = Decimal("2.0")  # PRD §13.1 FR-312 — specified
RISK_NONE_SCORE = Decimal("0.0")  # PRD §13.1 FR-312 — specified
RISK_SCALE_MAX = Decimal("10")  # PRD §13.1 — specified

SEVERITY_SCORES: dict[RiskLevel, Decimal] = {
    RiskLevel.HIGH: RISK_HIGH_SCORE,
    RiskLevel.MEDIUM: RISK_MEDIUM_SCORE,
    RiskLevel.LOW: RISK_LOW_SCORE,
    RiskLevel.NONE: RISK_NONE_SCORE,
}

# FR-315: a risk keyword detected but its numeric magnitude unparseable defaults
# to MEDIUM. (The High-EMD row of §13.1 is the one explicit exception — it places
# its own unparseable case in LOW; see EMD section below.)
FR315_UNPARSEABLE_SEVERITY = RiskLevel.MEDIUM  # PRD §13.1 FR-315 — specified

# --- Percentage bands shared by Performance Guarantee and Liquidated Damages ---
# x > 10% -> HIGH · 5% <= x <= 10% -> MEDIUM · x < 5% -> LOW (C4 boundaries).
PCT_HIGH_MIN_EXCLUSIVE = Decimal("10")  # PRD §13.1 — specified
PCT_MEDIUM_MIN_INCLUSIVE = Decimal("5")  # PRD §13.1 — specified

# --- High EMD bands: EMD as a percentage of tender value ---
# x > 5% -> HIGH · 2% <= x <= 5% -> MEDIUM · x < 2% (or unparseable) -> LOW.
EMD_HIGH_MIN_EXCLUSIVE = Decimal("5")  # PRD §13.1 — specified
EMD_MEDIUM_MIN_INCLUSIVE = Decimal("2")  # PRD §13.1 — specified
# Per the §13.1 table, an EMD clause present without parseable values is LOW
# (this is the one category whose table cell overrides the FR-315 default).
EMD_UNPARSEABLE_SEVERITY = RiskLevel.LOW  # PRD §13.1 — specified (High-EMD row)

# --- Short completion time (in DAYS, not months) ---
# HIGH iff days < 90 AND tender value > 50 lakh (a strict AND, never an OR).
# Otherwise days < 180 -> MEDIUM. Otherwise (urgency wording, standard days) LOW.
COMPLETION_HIGH_MAX_DAYS_EXCLUSIVE = 90  # PRD §13.1 — specified
COMPLETION_HIGH_VALUE_MIN_EXCLUSIVE = FIFTY_LAKH  # PRD §13.1 — specified
COMPLETION_MEDIUM_MAX_DAYS_EXCLUSIVE = 180  # PRD §13.1 — specified

# --- Per-category detection vocabularies (kept separate, never pooled) ---
PERFORMANCE_GUARANTEE_KEYWORDS: tuple[str, ...] = (
    "performance guarantee",
    "performance security",
    "performance bank guarantee",
    "pbg",
)  # PRD §13.1 FR-311 — specified category
LIQUIDATED_DAMAGES_KEYWORDS: tuple[str, ...] = (
    "liquidated damages",
    "ld clause",
)  # PRD §13.1 FR-311 — specified category
OEM_DEPENDENCY_KEYWORDS: tuple[str, ...] = (
    "oem",
    "manufacturer authorisation",
    "manufacturer authorization",
    "manufacturer's authorisation",
    "manufacturer's authorization",
    "authorisation form",
    "authorization form",
    "maf",
)  # PRD §13.1 FR-311 — specified category
SHORT_COMPLETION_URGENCY_KEYWORDS: tuple[str, ...] = (
    "urgent",
    "immediate",
    "on priority",
    "time is the essence",
    "fast track",
    "expedite",
)  # PRD §13.1 FR-311 — specified category
HIGH_EMD_KEYWORDS: tuple[str, ...] = (
    "emd",
    "earnest money",
    "bid security",
)  # PRD §13.1 FR-311 — specified category
SPECIAL_CLAUSE_JV_BARRED_KEYWORDS: tuple[str, ...] = (
    "joint venture not allowed",
    "jv not allowed",
    "jv not permitted",
    "consortium not allowed",
    "no joint venture",
)  # PRD §13.1 FR-311 — specified category (HIGH trigger)
SPECIAL_CLAUSE_SOLE_DISCRETION_KEYWORDS: tuple[str, ...] = (
    "sole discretion",
    "absolute discretion",
    "at its own discretion",
)  # PRD §13.1 FR-311 — specified category (HIGH trigger)
SPECIAL_CLAUSE_ARBITRATION_KEYWORDS: tuple[str, ...] = (
    "arbitration",
    "dispute resolution",
)  # PRD §13.1 FR-311 — specified category (MEDIUM trigger)

# INFERRED — see C1. Overall risk aggregation is `max`, not sum/mean: §13.3 rule
# 2 ("> 8.0 out of 10") shares the 0-10 finding scale (FR-312), so a single HIGH
# (8.5) routes to REVIEW. The overall category is the category of the highest-
# scoring finding (FR-316). Tradeoff (C4/D4): pure max is lossy — one HIGH with
# five NONE scores identically to one HIGH with five MEDIUM. Acceptable for v1.
RISK_AGGREGATION = "max"  # INFERRED — see C1

# ===========================================================================
# §13.3 — Recommendation decision rules (strict order; first match wins)
# ===========================================================================
RISK_REVIEW_SCORE_MIN_EXCLUSIVE = Decimal("8.0")  # rule 2: score > 8.0 -> REVIEW — specified
SIMILARITY_GO_MIN_EXCLUSIVE = Decimal("0.85")  # rule 3: sim > 0.85 -> GO — specified
SIMILARITY_REVIEW_MIN_INCLUSIVE = Decimal("0.40")  # rule 4a lower bound (incl.) — specified
# rule 4a: 0.40 <= sim <= 0.85 -> REVIEW · rule 4b: sim < 0.40 -> NO_BID (C4).

# ===========================================================================
# §13.4 — Win probability (Decimal percentage points; NO_BID -> 0)
# ===========================================================================
NO_BID_WIN_PROBABILITY = Decimal("0")  # PRD §13.4 FR-322 — specified
WIN_BASE = Decimal("70.0")  # PRD §13.4 — specified
WIN_STRONG_MATCH_MIN_EXCLUSIVE = Decimal("0.75")  # sim > 0.75 -> +bonus — specified
WIN_STRONG_MATCH_BONUS = Decimal("15.0")  # PRD §13.4 — specified
WIN_WEAK_MATCH_MAX_EXCLUSIVE = Decimal("0.55")  # sim < 0.55 -> -penalty — specified
WIN_WEAK_MATCH_PENALTY = Decimal("20.0")  # PRD §13.4 — specified (subtracted)
# INFERRED — see C2: intermediate band (0.55 <= sim <= 0.75) is linear between
# the anchors (-20 at 0.55, +15 at 0.75); slope = 35 / 0.20 = 175. Chosen for
# continuity (no discontinuity at a band edge in explainable output).
WIN_INTERMEDIATE_SLOPE = Decimal("175.0")  # INFERRED — see C2
WIN_RISK_PENALTY_PER_POINT = Decimal("3.0")  # PRD §13.4 — specified (x risk score)
# The multiplicand is the TENDER VALUE, never the turnover requirement. At N = 3
# the requirement is V/3, so 3x it equals V and the bonus would fire on nearly
# every tender (Spec §5).
WIN_TURNOVER_BUFFER_MULTIPLE = Decimal("3")  # avg turnover > 3x value -> +bonus — specified
WIN_TURNOVER_BUFFER_BONUS = Decimal("10.0")  # PRD §13.4 — specified
WIN_MIN = Decimal("10.0")  # PRD §13.4 — specified (inclusive clamp)
WIN_MAX = Decimal("95.0")  # PRD §13.4 — specified (inclusive clamp)

# ===========================================================================
# §13.5 — Confidence (Decimal 0.0-1.0)
# ===========================================================================
CONFIDENCE_BASE = Decimal("1.0")  # PRD §13.5 — specified
# Subtract this for EACH of exactly three missing fields: completion period,
# EMD, tender value. Then cap by the mean of those three extraction confidences.
CONFIDENCE_PENALTY_PER_MISSING_FIELD = Decimal("0.1")  # PRD §13.5 — specified
CONFIDENCE_MIN = Decimal("0.1")  # PRD §13.5 — specified (inclusive bound)
CONFIDENCE_MAX = Decimal("1.0")  # PRD §13.5 — specified (inclusive bound)

# ===========================================================================
# Eligibility screening (feature spec §1-§3)
# ===========================================================================
# --- Stage A: work-type match grades ---
# score >= 0.70 -> MATCHED · 0.50 <= score < 0.70 -> REVIEW · < 0.50 -> NO_MATCH.
WORK_TYPE_MATCHED_MIN_INCLUSIVE = Decimal("0.70")  # Spec §3 — specified
WORK_TYPE_REVIEW_MIN_INCLUSIVE = Decimal("0.50")  # Spec §3 — specified
# Stage A1 assigns a fixed score on a normalised alias hit; it never computes one.
EXACT_MATCH_SCORE = Decimal("1.0")  # Spec §3 — specified

# --- Stage B: the 3/2/1 similar-work value test ---
# Nested by construction: a project clearing 60% also clears 40% and 30%, so the
# three comparisons are complete and are never counted separately.
SIMILAR_WORK_1_PCT = Decimal("60")  # Spec §3 — specified
SIMILAR_WORK_2_PCT = Decimal("40")  # Spec §3 — specified
SIMILAR_WORK_3_PCT = Decimal("30")  # Spec §3 — specified
# Completed Indian financial years of lookback, anchored to the tender closing
# date and never to the current date.
SIMILAR_WORK_LOOKBACK_YEARS = 7  # Spec §3 — specified

# --- Financial criterion ---
# Completed Indian financial years averaged. Fewer recorded years than this is
# INDETERMINATE; the engine never averages over a shorter window.
TURNOVER_AVERAGING_YEARS = 3  # Spec §2 — specified

# --- Shared unit conversion ---
# A day-denominated completion period converts to exact Decimal years at this
# rate, so N stays exact throughout the min(V/N, V) arithmetic.
DAYS_PER_YEAR = 365  # Spec §1 — specified

# ===========================================================================
# Shared
# ===========================================================================
TOTAL_METADATA_FIELDS = 10  # PRD FR-201 — specified
