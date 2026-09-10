"""Pagination primitives. All list endpoints are paginated (cross-cutting)."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass(frozen=True, slots=True)
class PageRequest:
    limit: int = DEFAULT_LIMIT
    offset: int = 0

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > MAX_LIMIT:
            raise ValueError(f"limit must be in [1, {MAX_LIMIT}]")
        if self.offset < 0:
            raise ValueError("offset must be >= 0")


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total
