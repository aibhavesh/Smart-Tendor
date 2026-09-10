"""Eligibility screen (feature spec §2-§4) — pure and deterministic.

Inputs and results live here rather than in ``decision/models.py`` because that
module is the shared vocabulary of the PRD §13 engines, and the eligibility types
answer to the feature spec instead. Keeping them apart keeps the authority
boundary visible.

The engine decides three things and nothing else: whether the financial criterion
clears, whether the technical criterion clears, and how an unknown input differs
from a definite failure. It never guesses a missing value and never reaches a
database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal
from uuid import UUID

from tender_intel.domain.decision import thresholds as th
from tender_intel.domain.enums.eligibility import (
    EligibilityStatus,
    MatchGrade,
    MatchMethod,
    SimilarWorkRule,
)
from tender_intel.domain.services.financial_year import FinancialYear, completed_years_before

_PAISA = Decimal("0.01")
_HUNDRED = Decimal("100")


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class TurnoverYear:
    year: FinancialYear
    amount: Decimal


@dataclass(frozen=True, slots=True)
class WorkTypeMatch:
    """One work type scored against the tender scope by the stage A cascade."""

    work_type_id: UUID
    code: str
    method: MatchMethod
    score: Decimal
    grade: MatchGrade


@dataclass(frozen=True, slots=True)
class CandidateProject:
    """A past project, with everything stage B needs to judge it."""

    project_id: UUID
    name: str
    work_value: Decimal | None
    #: Present only when a real completion certificate date is recorded. A blank
    #: date, or a non-date value such as "Running", leaves this None.
    completion_certificate_date: date | None
    work_type_ids: frozenset[UUID]


@dataclass(frozen=True, slots=True)
class EligibilityInput:
    tender_value: Decimal | None  # V
    completion_years: Decimal | None  # N, exact years
    closing_date: date | None
    #: Certified turnover for the averaging window. Short of the window length
    #: means indeterminate — the engine never averages over fewer years.
    turnover_years: list[TurnoverYear]
    #: Every work type the cascade scored, at any grade.
    matches: list[WorkTypeMatch]
    #: Past projects carrying at least one of the matched types.
    candidates: list[CandidateProject]
    #: How many active work types existed to score against. Zero means the
    #: taxonomy is unconfigured, which is an unknown rather than a failure —
    #: the same reasoning that keeps an empty turnover table out of NO_BID.
    taxonomy_size: int = 0


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class EligibilityRuleResult:
    """FR-304 / FR-356: name, outcome, actual, required and a reason.

    ``passed`` is tri-state. ``None`` means the rule could not be evaluated, which
    is different from failing it, and the difference is what routes a tender to a
    person instead of to NO_BID.
    """

    name: str
    passed: bool | None
    detail: str
    required: Decimal | None = None
    actual: Decimal | None = None

    @property
    def is_indeterminate(self) -> bool:
        return self.passed is None


@dataclass(frozen=True, slots=True)
class QualifyingProject:
    project_id: UUID
    name: str
    rank: int  # 1, 2 or 3
    work_value: Decimal


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    status: EligibilityStatus
    financial: EligibilityRuleResult
    technical_match: EligibilityRuleResult
    technical_value: EligibilityRuleResult
    matched_work_types: list[WorkTypeMatch] = field(default_factory=list)
    qualifying_projects: list[QualifyingProject] = field(default_factory=list)
    rule_satisfied: SimilarWorkRule | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def rules(self) -> list[EligibilityRuleResult]:
        return [self.financial, self.technical_match, self.technical_value]


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class EligibilityEngine:
    def evaluate(self, data: EligibilityInput) -> EligibilityResult:
        financial = self._financial(data)
        match_rule, pooled_type_ids, matched = self._stage_a(data)
        value_rule, qualifying, satisfied = self._stage_b(data, pooled_type_ids)

        rules = [financial, match_rule, value_rule]
        status = self._status(rules)

        return EligibilityResult(
            status=status,
            financial=financial,
            technical_match=match_rule,
            technical_value=value_rule,
            matched_work_types=matched,
            qualifying_projects=qualifying,
            rule_satisfied=satisfied,
            reasons=[r.detail for r in rules if r.passed is not True],
        )

    # ------------------------------------------------------------------ #
    # §4 — a definite failure always beats an unknown input
    # ------------------------------------------------------------------ #
    @staticmethod
    def _status(rules: list[EligibilityRuleResult]) -> EligibilityStatus:
        if any(r.passed is False for r in rules):
            return EligibilityStatus.NOT_ELIGIBLE
        if any(r.passed is None for r in rules):
            return EligibilityStatus.INDETERMINATE
        return EligibilityStatus.ELIGIBLE

    # ------------------------------------------------------------------ #
    # §2 — financial criterion
    # ------------------------------------------------------------------ #
    def _financial(self, data: EligibilityInput) -> EligibilityRuleResult:
        name = "financial_turnover"
        value, years = data.tender_value, data.completion_years

        if value is None:
            return EligibilityRuleResult(name, None, "Tender value is UNKNOWN.")
        if years is None:
            return EligibilityRuleResult(name, None, "Completion period is UNKNOWN.")
        if years <= 0:
            return EligibilityRuleResult(
                name, None, "Completion period is not a positive duration."
            )
        if len(data.turnover_years) < th.TURNOVER_AVERAGING_YEARS:
            return EligibilityRuleResult(
                name,
                None,
                f"Certified turnover is recorded for {len(data.turnover_years)} of the "
                f"{th.TURNOVER_AVERAGING_YEARS} completed financial years required.",
            )

        required = self._required_turnover(value, years)
        actual = self._average_turnover(data.turnover_years)
        passed = actual >= required
        window = f"{data.turnover_years[0].year.label} to {data.turnover_years[-1].year.label}"
        verb = "meets" if passed else "is below"
        return EligibilityRuleResult(
            name,
            passed,
            f"Average contractual turnover {actual} over {window} {verb} the required {required}.",
            required=required,
            actual=actual,
        )

    @staticmethod
    def _required_turnover(value: Decimal, years: Decimal) -> Decimal:
        """``min(V / N, V)``, rounded up to the paisa.

        The cap is load-bearing: where N is under a year, ``V / N`` exceeds V and
        the requirement is held at the full tender value. Rounding up rather than
        to nearest keeps the requirement from being understated by a fraction.
        """
        return min(value / years, value).quantize(_PAISA, rounding=ROUND_CEILING)

    @staticmethod
    def _average_turnover(years: list[TurnoverYear]) -> Decimal:
        total = sum((y.amount for y in years), Decimal("0"))
        return (total / Decimal(len(years))).quantize(_PAISA)

    # ------------------------------------------------------------------ #
    # §3 stage A — work-type match
    # ------------------------------------------------------------------ #
    @staticmethod
    def _stage_a(
        data: EligibilityInput,
    ) -> tuple[EligibilityRuleResult, frozenset[UUID], list[WorkTypeMatch]]:
        name = "technical_work_type"
        matched = [m for m in data.matches if m.grade is MatchGrade.MATCHED]
        review = [m for m in data.matches if m.grade is MatchGrade.REVIEW]
        pooled = matched + review
        pooled_ids = frozenset(m.work_type_id for m in pooled)

        if not pooled:
            if data.taxonomy_size == 0:
                return (
                    EligibilityRuleResult(
                        name,
                        None,
                        "No work types are configured, so the tender scope could not "
                        "be matched against anything.",
                    ),
                    pooled_ids,
                    [],
                )
            return (
                EligibilityRuleResult(
                    name,
                    False,
                    f"Tender scope matches none of the {data.taxonomy_size} work types "
                    "in the taxonomy.",
                ),
                pooled_ids,
                [],
            )
        if not matched:
            codes = ", ".join(m.code for m in review)
            return (
                EligibilityRuleResult(
                    name,
                    None,
                    f"Tender scope matches only in the review band ({codes}); "
                    "no work type reached a confident match.",
                ),
                pooled_ids,
                pooled,
            )
        codes = ", ".join(m.code for m in matched)
        return (
            EligibilityRuleResult(name, True, f"Tender scope matches {codes}."),
            pooled_ids,
            pooled,
        )

    # ------------------------------------------------------------------ #
    # §3 stage B — the 3/2/1 value test
    # ------------------------------------------------------------------ #
    def _stage_b(
        self, data: EligibilityInput, pooled_ids: frozenset[UUID]
    ) -> tuple[EligibilityRuleResult, list[QualifyingProject], SimilarWorkRule | None]:
        name = "technical_similar_works"

        if not pooled_ids:
            # Mirrors stage A: an unconfigured taxonomy is unknown, a populated
            # one that matched nothing is a genuine failure.
            passed = None if data.taxonomy_size == 0 else False
            return (
                EligibilityRuleResult(
                    name, passed, "No matched work type, so no candidate projects to test."
                ),
                [],
                None,
            )
        if data.tender_value is None:
            return EligibilityRuleResult(name, None, "Tender value is UNKNOWN."), [], None
        if data.closing_date is None:
            return (
                EligibilityRuleResult(
                    name, None, "Closing date is UNKNOWN, so the lookback window has no anchor."
                ),
                [],
                None,
            )

        window = completed_years_before(data.closing_date, th.SIMILAR_WORK_LOOKBACK_YEARS)
        opens, closes = window[0].start_date, window[-1].end_date

        eligible = [
            c
            for c in data.candidates
            if c.work_type_ids & pooled_ids
            and c.work_value is not None
            and c.completion_certificate_date is not None
            and opens <= c.completion_certificate_date <= closes
        ]
        ranked = sorted(eligible, key=lambda c: c.work_value or Decimal("0"), reverse=True)

        satisfied, needed = self._first_satisfied(ranked, data.tender_value)
        span = f"{window[0].label} to {window[-1].label}"

        if satisfied is None:
            return (
                EligibilityRuleResult(
                    name,
                    False,
                    f"{len(ranked)} certificated project(s) inside {span} do not meet any of "
                    f"the {th.SIMILAR_WORK_1_PCT}% / {th.SIMILAR_WORK_2_PCT}% / "
                    f"{th.SIMILAR_WORK_3_PCT}% similar-work rules.",
                    required=needed,
                ),
                [],
                None,
            )

        depth = int(satisfied.value[0])
        qualifying = [
            QualifyingProject(
                project_id=c.project_id,
                name=c.name,
                rank=index,
                work_value=c.work_value or Decimal("0"),
            )
            for index, c in enumerate(ranked[:depth], start=1)
        ]
        named = "; ".join(q.name for q in qualifying)
        return (
            EligibilityRuleResult(
                name,
                True,
                f"Rule {satisfied.value} satisfied inside {span} by: {named}.",
                required=needed,
                actual=qualifying[-1].work_value,
            ),
            qualifying,
            satisfied,
        )

    @staticmethod
    def _first_satisfied(
        ranked: list[CandidateProject], value: Decimal
    ) -> tuple[SimilarWorkRule | None, Decimal | None]:
        """First of the three nested rules that holds, with its threshold.

        Nested by construction — a project clearing 60% also clears 40% and 30% —
        so the first hit is the whole answer and the rules are never counted
        separately.
        """
        tiers = (
            (SimilarWorkRule.ONE_AT_60, 1, th.SIMILAR_WORK_1_PCT),
            (SimilarWorkRule.TWO_AT_40, 2, th.SIMILAR_WORK_2_PCT),
            (SimilarWorkRule.THREE_AT_30, 3, th.SIMILAR_WORK_3_PCT),
        )
        weakest: Decimal | None = None
        for rule, depth, percent in tiers:
            needed = (percent / _HUNDRED * value).quantize(_PAISA, rounding=ROUND_CEILING)
            weakest = needed
            if len(ranked) >= depth and (ranked[depth - 1].work_value or Decimal("0")) >= needed:
                return rule, needed
        return None, weakest
