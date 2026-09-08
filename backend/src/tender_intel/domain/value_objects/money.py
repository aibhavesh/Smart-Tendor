"""Exact-decimal helpers for monetary and quantity values.

Money and quantities are :class:`~decimal.Decimal` end to end — never ``float``.
Indian tender values are large (lakh/crore), so precision is stored generously
and only quantised for display/persistence.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

CURRENCY = "INR"
LAKH = Decimal(10) ** 5
CRORE = Decimal(10) ** 7

_MONEY_QUANTUM = Decimal("0.01")


def to_decimal(value: str | int | float | Decimal) -> Decimal:
    """Coerce to Decimal without float rounding artefacts.

    Floats are routed through ``str`` so ``0.1`` does not become
    ``0.1000000000000000055…``.
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError(f"cannot interpret {value!r} as a decimal") from exc


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM)
