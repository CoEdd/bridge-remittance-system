"""Money helpers. Amounts are integers in minor units; rates are Decimal. No floats."""

from decimal import ROUND_DOWN, Decimal
from typing import Literal, get_args

Currency = Literal["MYR", "CNY", "USD"]
CURRENCIES: tuple[Currency, ...] = get_args(Currency)

# Decimal places of each currency's minor unit (sen, fen, cents).
MINOR_UNITS: dict[str, int] = {"MYR": 2, "CNY": 2, "USD": 2}


def _require_int(amount_minor: int) -> None:
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise TypeError("An amount in minor units must be an int.")


def to_minor(amount: Decimal | str | int, currency: str) -> int:
    """Major units to minor units: ("12000.00", "CNY") -> 1200000."""
    if isinstance(amount, (bool, float)):
        raise TypeError("Money must be given as Decimal, str or int, never float.")
    scaled = Decimal(amount).scaleb(MINOR_UNITS[currency])
    if scaled != scaled.to_integral_value():
        raise ValueError(f"{amount} is finer than the minor unit of {currency}.")
    return int(scaled)


def from_minor(amount_minor: int, currency: str) -> Decimal:
    """Minor units to major units: (1200000, "CNY") -> Decimal("12000.00")."""
    _require_int(amount_minor)
    return Decimal(amount_minor).scaleb(-MINOR_UNITS[currency])


def format_amount(amount_minor: int, currency: str) -> str:
    """Human-readable amount with its currency code: "CNY 12,000.00"."""
    sign = "-" if amount_minor < 0 else ""
    digits = MINOR_UNITS[currency]
    return f"{currency} {sign}{from_minor(abs(amount_minor), currency):,.{digits}f}"


def convert(amount_minor: int, rate: Decimal) -> int:
    """
    What the user receives for `amount_minor` at `rate` (target units per source unit).

    Rounded down to a whole minor unit, so rounding never invents money. Both
    currencies must have the same number of minor digits, which holds for every
    supported currency (see MINOR_UNITS).
    """
    _require_int(amount_minor)
    if not isinstance(rate, Decimal):
        raise TypeError("A rate must be a Decimal.")
    if amount_minor < 0 or rate <= 0:
        raise ValueError("convert() needs a non-negative amount and a positive rate.")
    return int((Decimal(amount_minor) * rate).to_integral_value(rounding=ROUND_DOWN))
