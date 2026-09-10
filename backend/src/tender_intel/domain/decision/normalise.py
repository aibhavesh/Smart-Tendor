"""The pinned alias normaliser (feature spec §3).

One function, fixed by the spec, because the global uniqueness of
``alias_normalised`` depends on it and a change would silently redraw which
aliases collide.

    casefold -> NFKC -> collapse runs of whitespace to a single space -> strip

Hyphens and ampersands are deliberately **preserved**. Any normaliser that strips
them collapses ``wi-fi`` onto ``wifi`` and ``rail net`` onto ``railnet`` — each
pair belonging to a single work type — and each collision would violate the
global unique constraint at migration time rather than at review time.

Kept in the domain because it is decision logic: it decides what counts as the
same alias, and stage 1 of the match cascade is a lookup against its output.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalise_alias(text: str) -> str:
    """Return the canonical form used for alias equality and uniqueness."""
    folded = unicodedata.normalize("NFKC", text.casefold())
    return _WHITESPACE.sub(" ", folded).strip()


def tokenise(text: str) -> frozenset[str]:
    """Split normalised text into a token set for the lexical stage.

    Splitting on whitespace only, so a hyphenated term stays one token. That is
    the same choice the normaliser makes, and keeping the two consistent is what
    stops ``wi-fi`` matching ``fi`` on its own.
    """
    return frozenset(t for t in normalise_alias(text).split(" ") if t)
