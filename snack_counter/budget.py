"""Monthly budget per office, in the office's currency.

Nothing is stored here. Spent and reserved amounts are calculated from the
refills each time, so they always match.
"""
from __future__ import annotations

from datetime import datetime

from .models import Office, RefillState, SPENT_STATES
from .money import Money, month_key
from .store import RefillRepository


class Budget:
    def __init__(self, repo: RefillRepository, offices: dict[str, Office]):
        self.repo = repo
        self.offices = offices

    def spent(self, office_id: str, month: str) -> Money:
        """Purchases in this month, by receipt date in the office's time zone."""
        office = self.offices[office_id]
        total = Money.zero(office.currency)
        for refill in self.repo.for_office(office_id):
            if refill.state in SPENT_STATES and month_key(refill.purchased_at, office.tz) == month:
                total += refill.amount
        return total

    def reserved(self, office_id: str, month: str, exclude_refill: str | None = None) -> Money:
        """Spending limit held for a buyer who hasn't uploaded a receipt yet."""
        office = self.offices[office_id]
        total = Money.zero(office.currency)
        for refill in self.repo.for_office(office_id):
            if (refill.state == RefillState.COMMITTED and refill.id != exclude_refill
                    and month_key(refill.committed_at, office.tz) == month):
                total += refill.limit
        return total

    def remaining(self, office_id: str, month: str, exclude_refill: str | None = None) -> Money:
        budget = self.offices[office_id].monthly_budget
        return budget - self.spent(office_id, month) - self.reserved(office_id, month, exclude_refill)

    def spending_limit(self, office_id: str, now: datetime, exclude_refill: str | None = None) -> Money | None:
        """What the next buyer may spend, or None if not even a small purchase fits."""
        office = self.offices[office_id]
        remaining = self.remaining(office_id, month_key(now, office.tz), exclude_refill)
        if remaining < office.min_purchase:
            return None
        return min(remaining, office.max_purchase)
