"""The fixed-window limiter behind anonymous log ingestion."""

from __future__ import annotations

from tender_intel.api.schemas.observability import (
    MAX_CONTEXT_KEYS,
    MAX_CONTEXT_VALUE_CHARS,
    FrontendLogEntry,
)
from tender_intel.infrastructure.observability.rate_limit import FixedWindowRateLimiter


def test_allows_up_to_the_limit():
    limiter = FixedWindowRateLimiter(limit=3)
    assert [limiter.check("a")[0] for _ in range(3)] == [True, True, True]
    assert limiter.check("a")[0] is False


def test_keys_are_independent():
    limiter = FixedWindowRateLimiter(limit=1)
    assert limiter.check("a")[0] is True
    assert limiter.check("b")[0] is True
    assert limiter.check("a")[0] is False


def test_cost_is_charged_in_units():
    limiter = FixedWindowRateLimiter(limit=10)
    assert limiter.check("a", cost=7)[0] is True
    assert limiter.check("a", cost=4)[0] is False  # would total 11
    assert limiter.check("a", cost=3)[0] is True  # exactly 10


def test_a_batch_larger_than_the_whole_budget_is_refused_on_a_fresh_window():
    """Otherwise one oversized batch slips through unmetered at every rollover."""
    limiter = FixedWindowRateLimiter(limit=5)
    allowed, retry_after = limiter.check("a", cost=6)
    assert allowed is False
    assert retry_after > 0
    assert "a" not in limiter._windows  # nothing was opened for it


def test_a_refusal_does_not_charge():
    """Otherwise a caller already over the limit would extend its own lockout."""
    limiter = FixedWindowRateLimiter(limit=5)
    assert limiter.check("a", cost=5)[0] is True
    for _ in range(10):
        assert limiter.check("a", cost=1)[0] is False
    # The window still holds exactly the 5 that were allowed, nothing more.
    assert limiter._windows["a"].count == 5


def test_refusal_reports_a_positive_retry_after():
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60.0)
    limiter.check("a")
    allowed, retry_after = limiter.check("a")
    assert allowed is False
    assert 0 < retry_after <= 61


def test_window_expiry_resets_the_count():
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=0.0)
    assert limiter.check("a")[0] is True
    assert limiter.check("a")[0] is True  # window already elapsed


def test_zero_limit_disables_the_limiter():
    limiter = FixedWindowRateLimiter(limit=0)
    assert all(limiter.check("a", cost=10_000)[0] for _ in range(5))


def test_key_table_is_capped():
    """A flood of forged keys must not grow the table without bound — that would
    move the very exhaustion the limiter exists to prevent into memory."""
    limiter = FixedWindowRateLimiter(limit=5, max_tracked_keys=100)
    for i in range(1_000):
        limiter.check(f"ip:{i}")
    assert len(limiter._windows) <= 100


# --- Payload bounding --- #
def test_long_context_values_are_truncated():
    entry = FrontendLogEntry(message="x", context={"stack": "y" * 50_000})
    assert entry.context is not None
    assert len(entry.context["stack"]) <= MAX_CONTEXT_VALUE_CHARS
    assert entry.context["stack"].endswith("[truncated]")


def test_context_key_count_is_capped_and_the_loss_is_recorded():
    entry = FrontendLogEntry(message="x", context={f"k{i}": i for i in range(100)})
    assert entry.context is not None
    assert len(entry.context) == MAX_CONTEXT_KEYS + 1  # + the dropped-key marker
    assert entry.context["_dropped_keys"] == 100 - MAX_CONTEXT_KEYS


def test_scalars_survive_unchanged():
    entry = FrontendLogEntry(message="x", context={"n": 42, "ok": True, "nil": None})
    assert entry.context == {"n": 42, "ok": True, "nil": None}


def test_nested_structures_are_flattened_to_bounded_text():
    entry = FrontendLogEntry(message="x", context={"deep": {"a": ["b"] * 10_000}})
    assert entry.context is not None
    assert isinstance(entry.context["deep"], str)
    assert len(entry.context["deep"]) <= MAX_CONTEXT_VALUE_CHARS


def test_empty_context_is_left_alone():
    assert FrontendLogEntry(message="x", context=None).context is None
    assert FrontendLogEntry(message="x", context={}).context == {}
