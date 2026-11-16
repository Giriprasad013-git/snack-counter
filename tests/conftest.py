from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from snack_counter import Currency, Money, MonthlyRates, Office, SnackCounterService, Volunteer
from snack_counter.fakes import FakeChat, FakeClock, FakeHr

NOK, INR = Currency.NOK, Currency.INR

OSLO = Office(
    id="oslo", name="Oslo", currency=NOK, tz=ZoneInfo("Europe/Oslo"),
    monthly_budget=Money.of(6000, NOK), min_purchase=Money.of(300, NOK), max_purchase=Money.of(1200, NOK),
    manager_id="oslo-mgr",
)
BLR = Office(
    id="blr", name="Bengaluru", currency=INR, tz=ZoneInfo("Asia/Kolkata"),
    monthly_budget=Money.of(15000, INR), min_purchase=Money.of(500, INR), max_purchase=Money.of(3000, INR),
    manager_id="blr-mgr",
)

# Monday 16 Nov 2026, 08:00 UTC = 09:00 in Oslo, 13:30 in Bengaluru.
MONDAY = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)


def nok(x) -> Money:
    return Money.of(x, NOK)


def inr(x) -> Money:
    return Money.of(x, INR)


def default_volunteers() -> list[Volunteer]:
    return [
        Volunteer("kari", "Kari", "oslo"),
        Volunteer("nora", "Nora", "oslo"),
        Volunteer("ola", "Ola", "oslo"),
        Volunteer("kiran", "Kiran", "blr"),
        Volunteer("meera", "Meera", "blr"),
        Volunteer("ravi", "Ravi", "blr"),
    ]


class World:
    """The service wired to the fake chat, HR and clock, starting on a Monday morning."""

    def __init__(self, volunteers: list[Volunteer] | None = None, start: datetime = MONDAY):
        self.clock = FakeClock(start)
        self.chat = FakeChat()
        self.hr = FakeHr()
        rates = MonthlyRates({("2026-11", INR): "0.125", ("2026-12", INR): "0.120"})
        self.svc = SnackCounterService(
            [OSLO, BLR], volunteers or default_volunteers(),
            chat=self.chat, hr=self.hr, clock=self.clock, rates=rates,
        )

    def refill(self, office_id: str, amount: Money, buyer: str | None = None, items=()):
        """Report empty, commit and upload the receipt."""
        r = self.svc.report_empty(office_id, "someone")
        r = self.svc.commit(r.id, buyer or r.offered_to)
        return self.svc.upload_receipt(r.id, r.buyer_id, amount, b"receipt.jpg", items)


@pytest.fixture
def world() -> World:
    return World()
