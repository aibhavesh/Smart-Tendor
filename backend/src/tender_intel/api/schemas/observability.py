"""Frontend log-ingestion schemas (FR-706).

Every field here is bounded. This endpoint accepts anonymous input and writes it
straight into the log pipeline, so an unbounded field is a write amplifier:
one request could otherwise put megabytes of attacker-chosen JSON into the logs,
where it costs storage, drowns real signal, and is read by whatever ingests it.

``context`` is truncated rather than rejected. The client swallows failures and
would drop a whole batch of fifty entries over one oversized one, so silently
losing good diagnostics is the worse outcome — but the truncation is always
marked, never quiet.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

LogLevel = Literal["debug", "info", "warning", "error"]

#: Per-entry limits on the free-form context bag.
MAX_CONTEXT_KEYS = 25
MAX_CONTEXT_VALUE_CHARS = 1000
_TRUNCATION_MARKER = "…[truncated]"
_DROPPED_KEY = "_dropped_keys"


def _bound_context(context: dict[str, Any]) -> dict[str, Any]:
    """Flatten to strings, cap the value length, and cap the key count."""
    bounded: dict[str, Any] = {}
    for key in list(context)[:MAX_CONTEXT_KEYS]:
        value = context[key]
        if isinstance(value, bool | int | float) or value is None:
            bounded[str(key)[:200]] = value
            continue
        text = value if isinstance(value, str) else repr(value)
        if len(text) > MAX_CONTEXT_VALUE_CHARS:
            text = text[: MAX_CONTEXT_VALUE_CHARS - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
        bounded[str(key)[:200]] = text

    dropped = len(context) - MAX_CONTEXT_KEYS
    if dropped > 0:
        bounded[_DROPPED_KEY] = dropped
    return bounded


class FrontendLogEntry(BaseModel):
    level: LogLevel = "info"
    message: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] | None = None
    url: str | None = Field(default=None, max_length=2000)
    timestamp: str | None = Field(default=None, max_length=64)

    @field_validator("context")
    @classmethod
    def _bound(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _bound_context(v) if v else v


class FrontendLogBatch(BaseModel):
    logs: list[FrontendLogEntry] = Field(min_length=1, max_length=100)


class LogIngestResponse(BaseModel):
    received: int
