"""Offices, volunteers and refills."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from .money import Currency, Money

WEEKDAYS = frozenset({0, 1, 2, 3, 4})  # Monday to Friday


@dataclass(frozen=True)
class Office:
    id: str
    name: str
    currency: Currency
    tz: ZoneInfo
    monthly_budget: Money
    min_purchase: Money
    max_purchase: Money
    manager_id: str


@dataclass(frozen=True)
class Visit:
    office_id: str
    start: date
    end: date  # inclusive


@dataclass
class Volunteer:
    id: str  # employee ID in the HR system
    name: str
    home_office: str
    office_days: frozenset[int] = WEEKDAYS
    holidays: list[tuple[date, date]] = field(default_factory=list)  # inclusive date ranges
    visits: list[Visit] = field(default_factory=list)

    def location_on(self, day: date) -> str | None:
        """The office this volunteer is at on the given day, or None."""
        if any(start <= day <= end for start, end in self.holidays):
            return None
        for visit in self.visits:
            if visit.start <= day <= visit.end:
                return visit.office_id if day.weekday() in WEEKDAYS else None
        return self.home_office if day.weekday() in self.office_days else None


@dataclass(frozen=True)
class Policy:
    offer_timeout: timedelta = timedelta(hours=2)
    commit_timeout: timedelta = timedelta(hours=24)
    fairness_window: timedelta = timedelta(days=60)


class RefillState(str, Enum):
    BLOCKED_BUDGET = "blocked_budget"  # box is empty but this month's budget is used up
    OPEN = "open"  # nobody available to ask; anyone can accept
    OFFERED = "offered"  # waiting for one volunteer to accept or decline
    COMMITTED = "committed"  # a buyer has accepted
    AWAITING_APPROVAL = "awaiting_approval"  # receipt is over the limit
    CLAIM_SUBMITTED = "claim_submitted"  # waiting for HR
    REIMBURSED = "reimbursed"


State = RefillState

# The box is still empty. An office can have only one refill in these states.
ACTIVE_STATES = frozenset({State.BLOCKED_BUDGET, State.OPEN, State.OFFERED, State.COMMITTED})

# Money has been spent and counts against the budget.
SPENT_STATES = frozenset({State.AWAITING_APPROVAL, State.CLAIM_SUBMITTED, State.REIMBURSED})

ALLOWED_TRANSITIONS: dict[RefillState, set[RefillState]] = {
    State.BLOCKED_BUDGET: {State.OPEN, State.OFFERED},
    State.OPEN: {State.OFFERED, State.COMMITTED, State.BLOCKED_BUDGET},
    State.OFFERED: {State.OFFERED, State.OPEN, State.COMMITTED, State.BLOCKED_BUDGET},
    State.COMMITTED: {State.OFFERED, State.OPEN, State.BLOCKED_BUDGET,
                      State.AWAITING_APPROVAL, State.CLAIM_SUBMITTED},
    State.AWAITING_APPROVAL: {State.CLAIM_SUBMITTED},
    State.CLAIM_SUBMITTED: {State.REIMBURSED},
    State.REIMBURSED: set(),
}


class InvalidTransition(Exception):
    pass


@dataclass
class Refill:
    id: str
    office_id: str
    reported_at: datetime
    reported_by: list[str]
    state: RefillState = State.OPEN
    version: int = 0

    # Offer
    offered_to: str | None = None
    offer_expires_at: datetime | None = None
    skipped: dict[str, date] = field(default_factory=dict)  # volunteer -> day they declined or didn't reply
    announced_on: date | None = None  # last day the channel was told nobody is available

    # Buyer
    buyer_id: str | None = None
    committed_at: datetime | None = None
    commit_deadline: datetime | None = None
    limit: Money | None = None

    # Purchase and claim
    amount: Money | None = None
    purchased_at: datetime | None = None
    items: tuple[str, ...] = ()
    receipt: bytes | None = None
    claim_id: str | None = None

    history: list[tuple[datetime, str]] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    def move_to(self, new_state: RefillState, now: datetime, note: str = "") -> None:
        if new_state not in ALLOWED_TRANSITIONS[self.state]:
            raise InvalidTransition(f"Refill {self.id}: can't go from {self.state.value} to {new_state.value}")
        self.history.append((now, f"{self.state.value} -> {new_state.value}" + (f": {note}" if note else "")))
        self.state = new_state

    def clear_offer(self) -> None:
        self.offered_to = None
        self.offer_expires_at = None

    def clear_buyer(self) -> None:
        self.buyer_id = None
        self.committed_at = None
        self.commit_deadline = None
        self.limit = None
