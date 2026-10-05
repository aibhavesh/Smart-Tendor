"""Schemas for browser-side diagnostic ingestion.

The browser ships batches of its own errors to ``POST /observability/logs`` so
client and server problems land in one log pipeline. Everything here is sized
defensively: the endpoint is unauthenticated by necessity (landing-page and
sign-in errors happen before anyone holds a token), so a hostile caller must not
be able to make the server do unbounded work.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

#: Distinct context keys retained per entry. Excess keys are dropped and counted
#: rather than rejected, because a truncated log is more useful than a 422.
MAX_CONTEXT_KEYS = 20
#: Per-value character ceiling for a context entry, *including* the truncation
#: marker. A test asserts the rendered value never exceeds this, so appending
#: "[truncated]" must be paid for out of the budget rather than added to it.
MAX_CONTEXT_VALUE_CHARS = 2_000
_TRUNCATION_MARKER = "[truncated]"
#: Upper bound on entries in one batch, enforced by the caller via the rate limiter.
MAX_BATCH_ENTRIES = 100

Level = Literal["debug", "info", "warning", "error"]


def _bound_value(value: Any) -> Any:
    """Render any value into something bounded and JSON-serialisable.

    Non-scalars are JSON-encoded then truncated. A DOM node or a circular
    structure arrives here as something ``json.dumps`` refuses; that must not
    become a 500 on an error-reporting path, so unencodable values degrade to
    their ``repr``.
    """
    if value is None or isinstance(value, bool | int | float):
        return value

    text = value if isinstance(value, str) else None
    if text is None:
        try:
            text = json.dumps(value, default=str)
        except (TypeError, ValueError):
            text = repr(value)

    if len(text) > MAX_CONTEXT_VALUE_CHARS:
        keep = MAX_CONTEXT_VALUE_CHARS - len(_TRUNCATION_MARKER)
        return text[:keep] + _TRUNCATION_MARKER
    return text


class FrontendLogEntry(BaseModel):
    message: str = Field(max_length=MAX_CONTEXT_VALUE_CHARS)
    level: Level = "error"
    context: dict[str, Any] | None = None
    url: str | None = Field(default=None, max_length=2_000)
    timestamp: str | None = Field(default=None, max_length=100)

    @field_validator("context")
    @classmethod
    def _bound_context(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Cap the key count, cap each value, and record what was dropped.

        Dropping silently would make a truncated log indistinguishable from a
        complete one, so the loss is written into the entry under
        ``_dropped_keys``.
        """
        if value is None:
            return None
        if not value:
            return {}

        bounded = {k: _bound_value(v) for k, v in list(value.items())[:MAX_CONTEXT_KEYS]}
        dropped = len(value) - MAX_CONTEXT_KEYS
        if dropped > 0:
            bounded["_dropped_keys"] = dropped
        return bounded


class FrontendLogBatch(BaseModel):
    """One batch from the browser.

    The field is named ``logs``, not ``entries``, to match the wire format
    ``lib/telemetry.ts`` has always sent. Renaming it would silently 422 every
    deployed browser, since that client is compiled into the shipped bundle and
    cannot be updated in step with the API.
    """

    logs: list[FrontendLogEntry] = Field(min_length=1, max_length=MAX_BATCH_ENTRIES)


class LogIngestResponse(BaseModel):
    #: Named ``received``, not ``accepted``, to match the deployed client and the
    #: integration tests that pin this contract.
    received: int
