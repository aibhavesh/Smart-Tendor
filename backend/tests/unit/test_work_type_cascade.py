"""Stage A cascade — exact, then lexical, then semantic. First hit wins.

Feature spec §3. Marked ``regression``: the 0.70 and 0.50 band edges are spec §6
thresholds.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from tender_intel.domain.decision.normalise import normalise_alias, tokenise
from tender_intel.domain.decision.work_type_match import (
    WorkTypeCandidate,
    coverage,
    grade_for,
    match_work_types,
)
from tender_intel.domain.enums.eligibility import MatchGrade, MatchMethod

pytestmark = pytest.mark.regression


def candidate(
    *,
    aliases: tuple[str, ...] = (),
    bags: tuple[tuple[str, ...], ...] = (),
    semantic: Decimal | None = None,
    code: str = "OFC_CABLE_SUPPLY",
) -> WorkTypeCandidate:
    return WorkTypeCandidate(
        work_type_id=uuid4(),
        code=code,
        aliases=frozenset(normalise_alias(a) for a in aliases),
        token_bags=tuple(frozenset(b) for b in bags),
        semantic_score=semantic,
    )


# --------------------------------------------------------------------------- #
# Band edges
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (Decimal("1.0"), MatchGrade.MATCHED),
        (Decimal("0.70"), MatchGrade.MATCHED),
        (Decimal("0.699"), MatchGrade.REVIEW),
        (Decimal("0.50"), MatchGrade.REVIEW),
        (Decimal("0.499"), MatchGrade.NO_MATCH),
        (Decimal("0"), MatchGrade.NO_MATCH),
    ],
)
def test_grade_bands(score, expected):
    assert grade_for(score) is expected


# --------------------------------------------------------------------------- #
# Stage order
# --------------------------------------------------------------------------- #
def test_an_exact_hit_scores_one_and_short_circuits():
    c = candidate(aliases=("OFC",), bags=(("nothing",),), semantic=Decimal("0.99"))
    [result] = match_work_types("Supply of OFC cable along the route", [c])
    assert result.method is MatchMethod.EXACT
    assert result.score == Decimal("1.0")


def test_lexical_runs_only_when_exact_misses():
    c = candidate(aliases=("quad cable",), bags=(("quad", "cable"),), semantic=Decimal("0.99"))
    [result] = match_work_types("laying of quad and cable works", [c])
    # "quad cable" is not a substring, but both its tokens are present.
    assert result.method is MatchMethod.LEXICAL
    assert result.score == Decimal("1.000")


def test_semantic_runs_only_when_both_cheaper_stages_miss():
    c = candidate(aliases=("railnet",), bags=(("railnet", "extension"),), semantic=Decimal("0.88"))
    [result] = match_work_types("provision of fibre distribution", [c])
    assert result.method is MatchMethod.SEMANTIC
    assert result.score == Decimal("0.88")


def test_a_candidate_below_every_band_is_dropped():
    c = candidate(aliases=("msdac",), bags=(("axle", "counter"),), semantic=Decimal("0.1"))
    assert match_work_types("audio video conference system", [c]) == []


def test_no_semantic_vector_is_not_an_error():
    c = candidate(aliases=("msdac",), bags=(("axle", "counter"),), semantic=None)
    assert match_work_types("audio video conference system", [c]) == []


# --------------------------------------------------------------------------- #
# Normalisation — the pairs the pinned normaliser must keep apart
# --------------------------------------------------------------------------- #
def test_hyphenated_and_unhyphenated_aliases_stay_distinct():
    # Both belong to one work type. A normaliser that stripped the hyphen would
    # collapse them and violate the global unique constraint.
    assert normalise_alias("Wi-Fi") == "wi-fi"
    assert normalise_alias("WiFi") == "wifi"
    assert normalise_alias("Wi-Fi") != normalise_alias("WiFi")


def test_spaced_and_unspaced_aliases_stay_distinct():
    assert normalise_alias("rail net") != normalise_alias("railnet")


def test_case_and_whitespace_normalise():
    assert normalise_alias("  Performance   Bank  Guarantee ") == "performance bank guarantee"


def test_both_wifi_forms_resolve_to_the_same_work_type():
    hyphen = candidate(aliases=("wi-fi",), code="WIFI_PROVISION")
    plain = candidate(aliases=("wifi",), code="WIFI_PROVISION")
    assert match_work_types("provision of Wi-Fi at the shed", [hyphen])[0].code == "WIFI_PROVISION"
    assert match_work_types("provision of WiFi at the shed", [plain])[0].code == "WIFI_PROVISION"


def test_tokenise_keeps_a_hyphenated_term_whole():
    assert "wi-fi" in tokenise("provision of Wi-Fi")


# --------------------------------------------------------------------------- #
# Coverage
# --------------------------------------------------------------------------- #
def test_coverage_is_bounded_and_exact():
    scope = tokenise("laying and jointing of underground cable")
    assert coverage(frozenset({"laying", "jointing"}), scope) == Decimal("1.000")
    assert coverage(frozenset({"laying", "blowing"}), scope) == Decimal("0.500")
    assert coverage(frozenset({"blowing"}), scope) == Decimal("0.000")


def test_coverage_of_an_empty_bag_is_zero_not_an_error():
    assert coverage(frozenset(), tokenise("anything")) == Decimal("0")


def test_a_long_scope_does_not_dilute_the_score():
    # This is why coverage replaces symmetric Dice: a two-token alias fully
    # present must score 1.0 however long the surrounding document is.
    scope = tokenise(" ".join(["filler"] * 500) + " quad cable")
    assert coverage(frozenset({"quad", "cable"}), scope) == Decimal("1.000")


def test_results_are_ordered_by_descending_score():
    strong = candidate(aliases=("quad cable",), code="QUAD")
    weak = candidate(aliases=("nothing",), bags=(("quad", "absent"),), code="WEAK")
    results = match_work_types("supply of quad cable", [weak, strong])
    assert [r.code for r in results] == ["QUAD", "WEAK"]
