"""The UNKNOWN convention.

Extraction must never guess. When a value is absent or unreadable, the field
holds :data:`UNKNOWN` rather than ``None`` (which is ambiguous with "not yet
populated") or a fabricated default. Modelled as a single-member enum so it is a
distinct, typeable, JSON-stable sentinel.
"""

from __future__ import annotations

from enum import Enum
from typing import TypeGuard


class UnknownType(Enum):
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "UNKNOWN"


UNKNOWN = UnknownType.UNKNOWN

# A value that may be genuinely absent.
type Maybe[T] = T | UnknownType


def is_unknown(value: object) -> TypeGuard[UnknownType]:
    return value is UNKNOWN


def is_known[T](value: Maybe[T]) -> TypeGuard[T]:
    return value is not UNKNOWN
