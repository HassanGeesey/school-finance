"""Money as integer cents.

The single source of truth for handling amounts: never floats. Inputs come in as
decimal strings/numbers and are converted to integer cents; display is formatted
from cents.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Union

Money = int

AmountInput = Union[str, Decimal, int]


def cents_from_decimal(value: Decimal) -> Money:
    """Convert a Decimal dollar amount to integer cents (half-up rounding)."""
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents_from_string(value: str) -> Money:
    """Parse a dollar string like ``"$1,234.56"`` or ``"12.5"`` into cents."""
    cleaned = value.strip().lstrip("$").replace(",", "").strip()
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Not a valid amount: {value!r}") from None
    return cents_from_decimal(amount)


def to_cents(value: AmountInput) -> Money:
    """Coerce common amount inputs (decimal string, Decimal, int cents) to cents."""
    if isinstance(value, str):
        return cents_from_string(value)
    if isinstance(value, Decimal):
        return cents_from_decimal(value)
    return int(value)


def format_cents(cents: Money) -> str:
    """Format integer cents as a USD amount, e.g. 1250 -> ``$12.50``."""
    sign = "-" if cents < 0 else ""
    amount = Decimal(abs(int(cents))) / Decimal(100)
    return f"{sign}${amount:,.2f}"
