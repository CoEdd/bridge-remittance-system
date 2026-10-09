from decimal import Decimal

import pytest

from app.money import CURRENCIES, MINOR_UNITS, convert, format_amount, from_minor, to_minor


def test_to_minor_and_back() -> None:
    assert to_minor("12000.00", "CNY") == 1_200_000
    assert to_minor(Decimal("0.01"), "MYR") == 1
    assert to_minor(180, "USD") == 18_000
    assert from_minor(1_200_000, "CNY") == Decimal("12000.00")
    assert from_minor(-5, "MYR") == Decimal("-0.05")
    for amount in (0, 1, 99, 100, 342_000, 985_000, -290_000):
        assert to_minor(from_minor(amount, "CNY"), "CNY") == amount


def test_to_minor_refuses_floats_and_fractions_of_a_minor_unit() -> None:
    with pytest.raises(TypeError):
        to_minor(12.5, "CNY")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        to_minor("12.345", "CNY")


def test_from_minor_refuses_non_integers() -> None:
    with pytest.raises(TypeError):
        from_minor(12.0, "CNY")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        from_minor(True, "CNY")


def test_format_amount_always_shows_the_currency_code() -> None:
    assert format_amount(1_200_000, "CNY") == "CNY 12,000.00"
    assert format_amount(985_000, "MYR") == "MYR 9,850.00"
    assert format_amount(0, "USD") == "USD 0.00"
    assert format_amount(-290_000, "CNY") == "CNY -2,900.00"
    assert format_amount(123_456_789_012, "MYR") == "MYR 1,234,567,890.12"


def test_convert_rounds_down_what_the_user_receives() -> None:
    assert convert(100_000, Decimal("1.62")) == 162_000
    # 333.33 * 1.6381 = 546.027873 -> 546.02, never 546.03
    assert convert(33_333, Decimal("1.6381")) == 54_602
    # 0.01 * 0.23 = 0.0023 -> nothing
    assert convert(1, Decimal("0.23")) == 0
    # 1.99 * 0.999 = 1.98801 -> 1.98
    assert convert(199, Decimal("0.999")) == 198


def test_convert_never_returns_more_than_the_exact_product() -> None:
    rate = Decimal("1.6381")
    for amount in range(0, 5_000, 7):
        assert convert(amount, rate) <= Decimal(amount) * rate < convert(amount, rate) + 1


def test_convert_refuses_floats_and_bad_input() -> None:
    with pytest.raises(TypeError):
        convert(100, 1.62)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        convert(1.5, Decimal("1.62"))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        convert(-100, Decimal("1.62"))
    with pytest.raises(ValueError):
        convert(100, Decimal("0"))


def test_every_supported_currency_has_two_minor_digits() -> None:
    # convert() relies on this; a currency with a different minor unit needs a new design.
    assert set(MINOR_UNITS) == set(CURRENCIES) == {"MYR", "CNY", "USD"}
    assert set(MINOR_UNITS.values()) == {2}
