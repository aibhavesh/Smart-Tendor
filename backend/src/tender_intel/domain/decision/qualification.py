"""Qualification engine (PRD §13.2) — pure, exact-decimal.

Three rules, naming the qualifying project:
* work value — the highest-value single past project meets the required value
  (FR-232 parsed requirement wins; otherwise a configurable % of tender value),
* average annual turnover >= 150% of tender value,
* net worth non-negative (or >= a supplied required %).

Unknown inputs fail toward caution (the rule does not pass and states why).
"""

from __future__ import annotations

from decimal import Decimal

from tender_intel.domain.decision import thresholds as th
from tender_intel.domain.decision.models import (
    QualificationInput,
    QualificationResult,
    QualificationRuleResult,
)

_HUNDRED = Decimal("100")


class QualificationEngine:
    def evaluate(self, data: QualificationInput) -> QualificationResult:
        rules = [
            self._work_value_rule(data),
            self._turnover_rule(data),
            self._net_worth_rule(data),
        ]
        return QualificationResult(qualified=all(r.passed for r in rules), rules=rules)

    # ------------------------------------------------------------------ #
    def _work_value_rule(self, data: QualificationInput) -> QualificationRuleResult:
        name = "work_value"
        required = self._required_work_value(data)
        if required is None:
            return QualificationRuleResult(
                name, False, "Required work value could not be determined."
            )
        if not data.similar_works:
            return QualificationRuleResult(
                name, False, "No past projects with a recorded value.", required=required
            )
        best = max(data.similar_works, key=lambda w: w.value)
        passed = best.value >= required
        return QualificationRuleResult(
            name,
            passed,
            (
                f"Highest past project {best.value} "
                f"{'meets' if passed else 'is below'} the required {required}."
            ),
            required=required,
            actual=best.value,
            qualifying_project_id=best.project_id if passed else None,
            qualifying_project_name=best.name if passed else None,
        )

    @staticmethod
    def _required_work_value(data: QualificationInput) -> Decimal | None:
        if data.required_work_value is not None:
            return data.required_work_value  # FR-232 parsed requirement wins (D1)
        ev = data.estimated_value
        if ev is not None and ev > 0 and data.work_value_required_pct is not None:
            return data.work_value_required_pct / _HUNDRED * ev
        return None

    def _turnover_rule(self, data: QualificationInput) -> QualificationRuleResult:
        name = "average_annual_turnover"
        ev, turnover = data.estimated_value, data.financials.turnover
        if ev is None or ev <= 0:
            return QualificationRuleResult(name, False, "Estimated value unknown.")
        if turnover is None:
            return QualificationRuleResult(name, False, "Company turnover not provided.")
        required = ev * th.TURNOVER_MULTIPLIER
        passed = turnover >= required
        return QualificationRuleResult(
            name,
            passed,
            f"Turnover {turnover} {'meets' if passed else 'is below'} the required {required}.",
            required=required,
            actual=turnover,
        )

    def _net_worth_rule(self, data: QualificationInput) -> QualificationRuleResult:
        name = "net_worth"
        net_worth = data.financials.net_worth
        if net_worth is None:
            return QualificationRuleResult(name, False, "Company net worth not provided.")
        required = th.NET_WORTH_MINIMUM
        if data.net_worth_required_pct is not None and data.estimated_value:
            required = data.net_worth_required_pct / _HUNDRED * data.estimated_value
        passed = net_worth >= required
        if required == th.NET_WORTH_MINIMUM:
            detail = f"Net worth {net_worth} is {'non-negative' if passed else 'negative'}."
        else:
            verb = "meets" if passed else "is below"
            detail = f"Net worth {net_worth} {verb} the required {required}."
        return QualificationRuleResult(name, passed, detail, required=required, actual=net_worth)
