"""Work-type taxonomy enums (feature spec §3, §7).

The category enum is deliberately flat. A self-referential parent/child hierarchy
was considered and rejected: it introduces cycle and orphan handling for no
current benefit, and three categories describe the portfolio adequately.
"""

from __future__ import annotations

from enum import StrEnum


class WorkTypeCategory(StrEnum):
    TELECOM_NETWORKING = "TELECOM_NETWORKING"
    SIGNALLING = "SIGNALLING"
    AUDIO_VISUAL = "AUDIO_VISUAL"


class AliasKind(StrEnum):
    """What kind of surface form an alias is.

    Recorded for auditability rather than behaviour: every alias is matched the
    same way regardless of kind. Knowing that ``MAF`` is an ABBREVIATION and
    ``manufacturer authorisation`` its EXPANSION is what lets a reviewer see why
    a tender matched.
    """

    ABBREVIATION = "ABBREVIATION"
    EXPANSION = "EXPANSION"
    SYNONYM = "SYNONYM"
    VARIANT = "VARIANT"


class WorkTypeLinkSource(StrEnum):
    """How a past project came to carry a work-type tag.

    ``SEED`` rows come from the portfolio workbook, ``MANUAL`` from an
    administrator, ``INFERRED`` from automated tagging. Kept explicit so a
    later reviewer can tell curated evidence from derived evidence.
    """

    SEED = "SEED"
    MANUAL = "MANUAL"
    INFERRED = "INFERRED"
