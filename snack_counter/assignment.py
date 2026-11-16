"""Choosing who to ask to buy.

Only volunteers who are at the office today, and haven't already declined this
refill today, are asked. They are ranked by:
  1. fewest refills in the last 60 days
  2. longest since their last refill
  3. volunteer ID, so the result is always the same
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from .models import Office, Policy, Refill, SPENT_STATES, Volunteer

NEVER = datetime.min.replace(tzinfo=timezone.utc)


def available_volunteers(volunteers: list[Volunteer], office: Office, today: date, refill: Refill) -> list[Volunteer]:
    return [v for v in volunteers
            if v.location_on(today) == office.id and refill.skipped.get(v.id) != today]


def ranking(volunteer: Volunteer, refills: list[Refill], now: datetime, policy: Policy) -> tuple:
    bought = [r.purchased_at for r in refills if r.buyer_id == volunteer.id and r.state in SPENT_STATES]
    recent_count = sum(1 for when in bought if now - when <= policy.fairness_window)
    last_refill = max(bought, default=NEVER)
    return (recent_count, last_refill, volunteer.id)


def choose_buyer(volunteers: list[Volunteer], office: Office, refill: Refill,
                 refills: list[Refill], now: datetime, policy: Policy) -> Volunteer | None:
    today = now.astimezone(office.tz).date()
    candidates = available_volunteers(volunteers, office, today, refill)
    if not candidates:
        return None
    return min(candidates, key=lambda v: ranking(v, refills, now, policy))
