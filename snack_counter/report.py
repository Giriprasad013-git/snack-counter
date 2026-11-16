"""Monthly spending report for both offices.

Each office is totalled in its own currency, then converted to NOK once using
the month's rate. A purchase belongs to the month of its date in that office's
time zone.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .models import Office, Refill, SPENT_STATES
from .money import Currency, Money, MonthlyRates, month_key


@dataclass(frozen=True)
class OfficeTotal:
    office_name: str
    budget: Money
    spent: Money
    remaining: Money
    refill_count: int
    spent_nok: Money
    top_items: list[tuple[str, int]]


@dataclass(frozen=True)
class MonthlyReport:
    month: str
    offices: list[OfficeTotal]
    total_nok: Money

    def render(self) -> str:
        lines = [f"Snack spending {self.month}"]
        for o in self.offices:
            lines.append(f"{o.office_name}: {o.spent} of {o.budget} ({o.spent_nok}), "
                         f"{o.refill_count} refills, {o.remaining} left")
            if o.top_items:
                lines.append("  most bought: " + ", ".join(f"{item} ({n})" for item, n in o.top_items))
        lines.append(f"Total: {self.total_nok}")
        return "\n".join(lines)


def build_monthly_report(refills: list[Refill], offices: dict[str, Office],
                         rates: MonthlyRates, month: str) -> MonthlyReport:
    rows = []
    total = Money.zero(Currency.NOK)
    for office in offices.values():
        bought = [r for r in refills
                  if r.office_id == office.id and r.state in SPENT_STATES
                  and month_key(r.purchased_at, office.tz) == month]
        spent = sum((r.amount for r in bought), Money.zero(office.currency))
        spent_nok = rates.to_nok(spent, month)
        rows.append(OfficeTotal(
            office_name=office.name,
            budget=office.monthly_budget,
            spent=spent,
            remaining=office.monthly_budget - spent,
            refill_count=len(bought),
            spent_nok=spent_nok,
            top_items=Counter(item for r in bought for item in r.items).most_common(3),
        ))
        total += spent_nok
    return MonthlyReport(month, rows, total)
