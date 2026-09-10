"""Stage A work-type cascade (feature spec §3) — pure, no I/O.

Three stages per work type, evaluated in order, first hit wins. A type that
resolves on an exact alias never reaches the lexical or semantic stage, so the
cheap deterministic answer always beats the expensive approximate one.

The caller supplies everything: the normalised alias forms, the token bags to
score lexically, and a pre-computed cosine per type. That keeps embedding and
database work in the application layer and leaves the banding decision here.

A note on the lexical measure. Symmetric Dice is the wrong statistic for matching
a two-word alias against a multi-paragraph scope: the denominator is dominated by
the scope's own length, and the score could never reach 0.50 however well the
alias matched. This uses *coverage* instead — what fraction of a bag's tokens the
scope contains — which is bounded 0 to 1, reaches 1.0 on a fully present alias,
and is exact in rational arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from tender_intel.domain.decision import thresholds as th
from tender_intel.domain.decision.eligibility import WorkTypeMatch
from tender_intel.domain.decision.normalise import normalise_alias, tokenise
from tender_intel.domain.enums.eligibility import MatchGrade, MatchMethod

_ZERO = Decimal("0")
_SCORE_QUANTUM = Decimal("0.001")


@dataclass(frozen=True, slots=True)
class WorkTypeCandidate:
    """One work type, with every surface the cascade may score it on."""

    work_type_id: UUID
    code: str
    #: Normalised alias forms, for the exact stage.
    aliases: frozenset[str]
    #: Token bags for the lexical stage: one per alias, plus the type's own name
    #: and description, plus the descriptions of the projects tagged with it.
    token_bags: tuple[frozenset[str], ...]
    #: Cosine against the tender scope over past-project description embeddings,
    #: already converted out of float by the caller. ``None`` when the type has
    #: no indexed vector.
    semantic_score: Decimal | None = None


def grade_for(score: Decimal) -> MatchGrade:
    """Band a score. At or above 0.70 is MATCHED; 0.50 up to 0.70 is REVIEW."""
    if score >= th.WORK_TYPE_MATCHED_MIN_INCLUSIVE:
        return MatchGrade.MATCHED
    if score >= th.WORK_TYPE_REVIEW_MIN_INCLUSIVE:
        return MatchGrade.REVIEW
    return MatchGrade.NO_MATCH


def coverage(bag: frozenset[str], scope_tokens: frozenset[str]) -> Decimal:
    """Fraction of ``bag`` present in the scope, exact in rational arithmetic."""
    if not bag:
        return _ZERO
    hits = len(bag & scope_tokens)
    return (Decimal(hits) / Decimal(len(bag))).quantize(_SCORE_QUANTUM)


def match_work_types(scope_text: str, candidates: list[WorkTypeCandidate]) -> list[WorkTypeMatch]:
    """Score every candidate, returning only those that graded above NO_MATCH.

    Ordered by descending score so the strongest evidence reads first.
    """
    normalised_scope = normalise_alias(scope_text)
    scope_tokens = tokenise(scope_text)

    results: list[WorkTypeMatch] = []
    for candidate in candidates:
        scored = _score(candidate, normalised_scope, scope_tokens)
        if scored is not None:
            results.append(scored)
    results.sort(key=lambda m: m.score, reverse=True)
    return results


def _score(
    candidate: WorkTypeCandidate, normalised_scope: str, scope_tokens: frozenset[str]
) -> WorkTypeMatch | None:
    # --- Stage 1: exact alias hit, fixed score, short-circuits the rest ---
    if any(alias and alias in normalised_scope for alias in candidate.aliases):
        return _match(candidate, MatchMethod.EXACT, th.EXACT_MATCH_SCORE)

    # --- Stage 2: best token coverage across the candidate's bags ---
    lexical = max((coverage(bag, scope_tokens) for bag in candidate.token_bags), default=_ZERO)
    if grade_for(lexical) is not MatchGrade.NO_MATCH:
        return _match(candidate, MatchMethod.LEXICAL, lexical)

    # --- Stage 3: semantic, only once both cheaper stages have missed ---
    semantic = candidate.semantic_score
    if semantic is not None and grade_for(semantic) is not MatchGrade.NO_MATCH:
        return _match(candidate, MatchMethod.SEMANTIC, semantic)

    return None


def _match(candidate: WorkTypeCandidate, method: MatchMethod, score: Decimal) -> WorkTypeMatch:
    return WorkTypeMatch(
        work_type_id=candidate.work_type_id,
        code=candidate.code,
        method=method,
        score=score,
        grade=grade_for(score),
    )
