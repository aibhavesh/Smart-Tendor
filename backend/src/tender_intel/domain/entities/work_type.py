"""Work-type taxonomy entities (feature spec §3, §7).

A work type is a capability the company can evidence. Aliases are the surface
forms a tender might use for it; project tags are the evidence that the company
has done it before.

Work types are **deactivated, never deleted**. A tag on a past project is
historical evidence, and deleting the type it points at would erase why a tender
matched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from tender_intel.domain.decision.normalise import normalise_alias
from tender_intel.domain.enums.work_type import AliasKind, WorkTypeCategory, WorkTypeLinkSource
from tender_intel.domain.exceptions import DomainValidationError


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class WorkType:
    code: str
    name: str
    category: WorkTypeCategory
    description: str | None = None
    is_active: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise DomainValidationError("work type code cannot be blank")
        if not self.name.strip():
            raise DomainValidationError("work type name cannot be blank")

    def deactivate(self) -> None:
        """Retire the type from matching without losing its history."""
        self.is_active = False
        self.updated_at = _now()

    def embedding_text(self) -> str:
        """Text a semantic stage would embed for this type.

        Present for completeness only. Stage 3 embeds *project descriptions*, not
        this, because a two or three word tag embeds poorly. Tags are the exact
        and lexical surface (feature spec §3).
        """
        return " \n".join(p for p in (self.name, self.description) if p)


@dataclass(slots=True)
class WorkTypeAlias:
    """One surface form for a work type.

    ``normalised`` is derived, never supplied. Computing it here rather than at
    the call site is what guarantees the stored value and the lookup key can
    never drift apart.
    """

    work_type_id: UUID
    alias: str
    kind: AliasKind
    id: UUID = field(default_factory=uuid4)
    normalised: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self.normalised = normalise_alias(self.alias)
        if not self.normalised:
            raise DomainValidationError("alias cannot be blank once normalised")


@dataclass(slots=True)
class PastProjectWorkType:
    """Evidence that a past project demonstrates a work type."""

    project_id: UUID
    work_type_id: UUID
    source: WorkTypeLinkSource
    #: Confidence in the tag itself, not in any match. Exact decimal, and only
    #: meaningful for an INFERRED tag — a curated one is simply true.
    confidence: Decimal | None = None
    #: The description substring that justifies the tag, so a reviewer can see
    #: the evidence without re-reading the source document.
    evidence: str | None = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not (Decimal("0") <= self.confidence <= Decimal("1")):
            raise DomainValidationError("tag confidence must be in [0, 1]")
