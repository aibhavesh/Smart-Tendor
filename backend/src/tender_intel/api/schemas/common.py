"""Shared API schemas."""

from __future__ import annotations

from pydantic import BaseModel

from tender_intel.domain.value_objects.pagination import Page


class PageResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def of[Item, Domain](cls, page: Page[Domain], items: list[Item]) -> PageResponse[Item]:
        return PageResponse[Item](
            items=items,
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            has_more=page.has_more,
        )
