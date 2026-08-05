"""Money-as-integer-cents helpers (the no-floats rule)."""

from decimal import Decimal

import pytest

from app.money import cents_from_decimal, cents_from_string, format_cents, to_cents


def test_cents_from_string_parses_plain_amounts():
    assert cents_from_string("12.50") == 1250
    assert cents_from_string("12.5") == 1250
    assert cents_from_string("0.99") == 99
    assert cents_from_string("0") == 0


def test_cents_from_string_accepts_dollar_sign_and_commas():
    assert cents_from_string("$1,234.56") == 123456
    assert cents_from_string("$100") == 10000


def test_cents_from_string_rejects_garbage():
    with pytest.raises(ValueError):
        cents_from_string("not-a-number")


def test_cents_from_decimal_rounds_half_up():
    assert cents_from_decimal(Decimal("12.345")) == 1235
    assert cents_from_decimal(Decimal("12.344")) == 1234


def test_to_cents_accepts_common_inputs():
    assert to_cents("5.00") == 500
    assert to_cents(Decimal("5.00")) == 500
    assert to_cents(500) == 500


def test_format_cents_formats_usd():
    assert format_cents(1250) == "$12.50"
    assert format_cents(10000) == "$100.00"
    assert format_cents(0) == "$0.00"
    assert format_cents(-1250) == "-$12.50"
