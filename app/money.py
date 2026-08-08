"""Money as integer cents.

The single source of truth for handling amounts: stored as integer cents.
Inputs come in as decimal strings, Decimals, or floats and are converted to
integer cents (half-up rounding); display is formatted from cents.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Union

Money = int

AmountInput = Union[str, Decimal, int, float]


class AmountError(ValueError):
    """An incoming amount was rejected: unparsable, or not strictly positive."""


class InvalidAmount(AmountError):
    """The input could not be parsed as a dollar amount."""


class NonPositiveAmount(AmountError):
    """The input parsed to zero or fewer cents; only positive amounts are allowed."""


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
    """Coerce common amount inputs (decimal string, Decimal, float) to cents.

    Floats are converted via their string representation so binary float
    artifacts (e.g. 12.99 -> 12.9899999...) round correctly, half-up.
    """
    if isinstance(value, str):
        return cents_from_string(value)
    if isinstance(value, Decimal):
        return cents_from_decimal(value)
    if isinstance(value, float):
        return cents_from_decimal(Decimal(repr(value)))
    return int(value)


def parse_positive_cents(value: AmountInput) -> Money:
    """Coerce an amount to positive integer cents, or reject it.

    The single validation rule for incoming amounts: the value must parse as a
    dollar amount (decimal string, Decimal, float, or int) and round to a
    strictly positive number of cents (half-up). Unparsable input raises
    :class:`InvalidAmount`; zero or negative amounts raise
    :class:`NonPositiveAmount`. Services translate these into their own domain
    errors, so no feature re-implements the positivity check.
    """
    try:
        if isinstance(value, bool):
            raise InvalidAmount(f"Not a valid amount: {value!r}")
        cents = to_cents(value)
    except (ArithmeticError, TypeError, ValueError):
        raise InvalidAmount(f"Not a valid amount: {value!r}") from None
    if cents <= 0:
        raise NonPositiveAmount("Amount must be greater than zero.")
    return cents


def format_cents(cents: Money) -> str:
    """Format integer cents as a USD amount, e.g. 1250 -> ``$12.50``."""
    sign = "-" if cents < 0 else ""
    amount = Decimal(abs(int(cents))) / Decimal(100)
    return f"{sign}${amount:,.2f}"


def format_input_cents(cents: Money) -> str:
    """Format integer cents as a bare USD number for form inputs, e.g. 1250 -> ``12.50``."""
    return f"{Decimal(int(cents)) / 100:.2f}"
