"""Money in whole minor units (øre, paise) so totals are exact, and monthly exchange rates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from functools import total_ordering
from zoneinfo import ZoneInfo


class Currency(str, Enum):
    NOK = "NOK"
    INR = "INR"


class CurrencyMismatch(ValueError):
    pass


class MissingRate(LookupError):
    pass


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


@total_ordering
@dataclass(frozen=True)
class Money:
    minor: int
    currency: Currency

    @classmethod
    def of(cls, amount: str | int | Decimal, currency: Currency) -> Money:
        return cls(_round(Decimal(str(amount)) * 100), currency)

    @classmethod
    def zero(cls, currency: Currency) -> Money:
        return cls(0, currency)

    def _same_currency(self, other: Money) -> None:
        if other.currency != self.currency:
            raise CurrencyMismatch(f"Can't combine {self.currency.value} and {other.currency.value}")

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.minor - other.minor, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.minor < other.minor

    def __str__(self) -> str:
        return f"{Decimal(self.minor) / 100:,.2f} {self.currency.value}"


def month_key(ts: datetime, tz: ZoneInfo) -> str:
    """The month of a timestamp in the given time zone, e.g. "2026-11"."""
    return ts.astimezone(tz).strftime("%Y-%m")


class MonthlyRates:
    """One fixed rate to NOK per currency and month, e.g. {("2026-11", Currency.INR): "0.125"}."""

    def __init__(self, rates: dict[tuple[str, Currency], Decimal | str]):
        self._rates = {key: Decimal(str(rate)) for key, rate in rates.items()}

    def rate_to_nok(self, currency: Currency, month: str) -> Decimal:
        if currency == Currency.NOK:
            return Decimal(1)
        if (month, currency) not in self._rates:
            raise MissingRate(f"No {currency.value} to NOK rate for {month}")
        return self._rates[(month, currency)]

    def to_nok(self, money: Money, month: str) -> Money:
        return Money(_round(money.minor * self.rate_to_nok(money.currency, month)), Currency.NOK)
