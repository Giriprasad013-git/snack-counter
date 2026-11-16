import pytest

from snack_counter.money import Currency, CurrencyMismatch, MissingRate, Money, MonthlyRates

NOK, INR = Currency.NOK, Currency.INR


def test_money_is_exact():
    assert Money.of("0.1", NOK) + Money.of("0.2", NOK) == Money.of("0.3", NOK)


def test_currencies_cannot_be_mixed():
    with pytest.raises(CurrencyMismatch):
        Money.of(100, NOK) + Money.of(100, INR)


def test_conversion_uses_the_rate_for_the_month():
    rates = MonthlyRates({("2026-11", INR): "0.125"})
    assert rates.to_nok(Money.of(2000, INR), "2026-11") == Money.of(250, NOK)
    with pytest.raises(MissingRate):
        rates.to_nok(Money.of(2000, INR), "2026-12")
