"""AuditLog — immutable record of every state-changing action.

Written with a before/after diff on every significant action (cross-cutting
requirement). Never updated or deleted once created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class AuditLog:
    action: str  # e.g. "tender.create", "review.approve", "user.role_change"
    entity_type: str
    entity_id: str | None = None
    actor_id: UUID | None = None  # None for system-originated actions
    diff: dict[str, Any] = field(default_factory=dict)  # {"field": {"before": .., "after": ..}}
    ip_address: str | None = None
    user_agent: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
