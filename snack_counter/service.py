"""Refill lifecycle: the commands people send through chat, plus the scheduler tick.

Every command reads the refill, checks the rules, saves it with a version check,
and only sends chat messages after the save has succeeded.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from .assignment import choose_buyer
from .budget import Budget
from .models import Office, Policy, Refill, RefillState, Volunteer
from .money import Money, MonthlyRates
from .ports import ChatPort, Clock, HrPort
from .report import MonthlyReport, build_monthly_report
from .store import ConcurrentModification, RefillRepository

State = RefillState


class NotAllowed(Exception):
    pass


class AlreadyTaken(NotAllowed):
    pass


class BudgetExhausted(NotAllowed):
    pass


class Messages:
    """Chat messages collected during a command, sent after the refill is saved."""

    def __init__(self):
        self.items: list[tuple[str, str, str]] = []

    def dm(self, user_id: str, text: str) -> None:
        self.items.append(("dm", user_id, text))

    def channel(self, office_id: str, text: str) -> None:
        self.items.append(("channel", office_id, text))

    def send(self, chat: ChatPort) -> None:
        for kind, to, text in self.items:
            if kind == "dm":
                chat.send_dm(to, text)
            else:
                chat.post_to_channel(to, text)


class SnackCounterService:
    def __init__(self, offices: Iterable[Office], volunteers: Iterable[Volunteer], *,
                 chat: ChatPort, hr: HrPort, clock: Clock, rates: MonthlyRates,
                 policy: Policy | None = None):
        self.offices = {o.id: o for o in offices}
        self.volunteers = {v.id: v for v in volunteers}
        self.chat = chat
        self.hr = hr
        self.clock = clock
        self.rates = rates
        self.policy = policy or Policy()
        self.repo = RefillRepository()
        self.budget = Budget(self.repo, self.offices)

    # ---- commands -------------------------------------------------------

    def report_empty(self, office_id: str, reporter_id: str) -> Refill:
        """Start a refill, or join the one already open for this office."""
        now = self.clock.now()
        refill, created = self.repo.create_if_no_active(
            office_id, lambda refill_id: Refill(refill_id, office_id, now, [reporter_id]))
        msgs = Messages()

        if not created:
            if reporter_id not in refill.reported_by:
                refill.reported_by.append(reporter_id)
                try:
                    refill = self.repo.save(refill)
                except ConcurrentModification:
                    refill = self.repo.get(refill.id)
            msgs.dm(reporter_id, "Thanks. A refill is already in progress.")
            msgs.send(self.chat)
            return refill

        self._offer_to_next_volunteer(refill, now, msgs)
        try:
            return self._save(refill, msgs)
        except ConcurrentModification:
            return self.repo.get(refill.id)

    def commit(self, refill_id: str, volunteer_id: str) -> Refill:
        """A volunteer agrees to buy. Only the first one succeeds."""
        now = self.clock.now()
        if volunteer_id not in self.volunteers:
            raise NotAllowed(f"{volunteer_id} is not a registered volunteer")
        volunteer = self.volunteers[volunteer_id]
        refill = self.repo.get(refill_id)
        office = self.offices[refill.office_id]

        if refill.state == State.COMMITTED:
            raise AlreadyTaken(f"{self._name(refill.buyer_id)} is already buying for this refill")
        if refill.state == State.BLOCKED_BUDGET:
            raise BudgetExhausted(f"The {office.name} budget is used up this month")
        if refill.state not in (State.OPEN, State.OFFERED):
            raise NotAllowed(f"Refill {refill.id} is {refill.state.value}")

        limit = self.budget.spending_limit(office.id, now, exclude_refill=refill.id)
        if limit is None:
            raise BudgetExhausted(f"The {office.name} budget is used up this month")

        asked = refill.offered_to
        refill.move_to(State.COMMITTED, now, f"{volunteer.id} will buy, limit {limit}")
        refill.clear_offer()
        refill.buyer_id = volunteer.id
        refill.committed_at = now
        refill.commit_deadline = now + self.policy.commit_timeout
        refill.limit = limit

        msgs = Messages()
        msgs.dm(volunteer.id, f"You're buying snacks for {office.name}. Spend up to {limit} and upload "
                              f"the receipt by {self._local_time(office, refill.commit_deadline)}.")
        msgs.channel(office.id, f"{volunteer.name} is refilling the snack box.")
        if asked and asked != volunteer.id:
            msgs.dm(asked, f"{volunteer.name} has taken refill {refill.id}. No action needed.")
        try:
            return self._save(refill, msgs)
        except ConcurrentModification:
            latest = self.repo.get(refill_id)
            if latest.state == State.COMMITTED:
                raise AlreadyTaken(f"{self._name(latest.buyer_id)} is already buying for this refill") from None
            raise

    def decline(self, refill_id: str, volunteer_id: str) -> Refill:
        now = self.clock.now()
        refill = self.repo.get(refill_id)
        if refill.state != State.OFFERED or refill.offered_to != volunteer_id:
            raise NotAllowed(f"Refill {refill_id} is not offered to {volunteer_id}")
        refill.skipped[volunteer_id] = self._today(refill, now)
        msgs = Messages()
        self._offer_to_next_volunteer(refill, now, msgs)
        return self._save(refill, msgs)

    def upload_receipt(self, refill_id: str, volunteer_id: str, amount: Money, receipt: bytes,
                       items: Iterable[str] = ()) -> Refill:
        """Record the purchase and send the claim to HR."""
        now = self.clock.now()
        refill = self.repo.get(refill_id)
        if refill.state != State.COMMITTED or refill.buyer_id != volunteer_id:
            raise NotAllowed(f"{volunteer_id} is not the buyer of refill {refill_id}")
        office = self.offices[refill.office_id]
        if amount.currency != office.currency:
            raise NotAllowed(f"{office.name} purchases must be in {office.currency.value}")

        refill.amount = amount
        refill.purchased_at = now
        refill.receipt = receipt
        refill.items = tuple(item.strip().lower() for item in items if item.strip())

        msgs = Messages()
        if amount > refill.limit:
            refill.move_to(State.AWAITING_APPROVAL, now, f"{amount} is over the limit of {refill.limit}")
            msgs.dm(office.manager_id, f"{self._name(volunteer_id)} spent {amount} on refill {refill.id}, "
                                       f"over the limit of {refill.limit}. Reply 'approve {refill.id}' to send the claim.")
        else:
            self._submit_claim(refill, now, msgs)
        msgs.channel(office.id, f"Snack box refilled by {self._name(volunteer_id)}.")
        return self._save(refill, msgs)

    def approve_overrun(self, refill_id: str, approver_id: str) -> Refill:
        now = self.clock.now()
        refill = self.repo.get(refill_id)
        if approver_id != self.offices[refill.office_id].manager_id:
            raise NotAllowed("Only the office manager can approve this")
        if refill.state != State.AWAITING_APPROVAL:
            raise NotAllowed(f"Refill {refill.id} is {refill.state.value}")
        msgs = Messages()
        self._submit_claim(refill, now, msgs)
        return self._save(refill, msgs)

    # ---- scheduler ------------------------------------------------------

    def tick(self) -> None:
        """Called every few minutes: handles expired offers, missed deadlines and HR approvals."""
        now = self.clock.now()
        for refill in self.repo.all():
            try:
                self._tick_refill(refill, now)
            except ConcurrentModification:
                pass  # changed by someone else in the meantime; check again next tick

    def _tick_refill(self, refill: Refill, now: datetime) -> None:
        msgs = Messages()

        if refill.state == State.OFFERED and now >= refill.offer_expires_at:
            msgs.dm(refill.offered_to, f"No reply on refill {refill.id}, so I've asked someone else.")
            refill.skipped[refill.offered_to] = self._today(refill, now)
            self._offer_to_next_volunteer(refill, now, msgs)

        elif refill.state == State.COMMITTED and now >= refill.commit_deadline:
            msgs.dm(refill.buyer_id, f"Refill {refill.id} passed its deadline and was given to someone else.")
            refill.skipped[refill.buyer_id] = self._today(refill, now)
            refill.clear_buyer()
            self._offer_to_next_volunteer(refill, now, msgs)

        elif refill.state == State.OPEN and refill.announced_on != self._today(refill, now):
            self._offer_to_next_volunteer(refill, now, msgs)  # new day, new people in the office

        elif refill.state == State.BLOCKED_BUDGET:
            if self.budget.spending_limit(refill.office_id, now, refill.id) is None:
                return
            self._offer_to_next_volunteer(refill, now, msgs)  # new month

        elif refill.state == State.CLAIM_SUBMITTED and self.hr.is_approved(refill.claim_id):
            refill.move_to(State.REIMBURSED, now, f"HR approved {refill.claim_id}")
            msgs.dm(refill.buyer_id, f"HR approved claim {refill.claim_id} ({refill.amount}).")

        else:
            return
        self._save(refill, msgs)

    # ---- queries --------------------------------------------------------

    def monthly_report(self, month: str) -> MonthlyReport:
        return build_monthly_report(self.repo.all(), self.offices, self.rates, month)

    # ---- helpers --------------------------------------------------------

    def _offer_to_next_volunteer(self, refill: Refill, now: datetime, msgs: Messages) -> None:
        """Offer the refill to the best available volunteer. If there is none, open it to everyone."""
        office = self.offices[refill.office_id]
        refill.clear_offer()

        limit = self.budget.spending_limit(office.id, now, exclude_refill=refill.id)
        if limit is None:
            if refill.state != State.BLOCKED_BUDGET:
                refill.move_to(State.BLOCKED_BUDGET, now, "monthly budget used up")
                msgs.channel(office.id, "The snack box is empty, but this month's budget is used up. "
                                        "It will be refilled next month.")
            return

        volunteer = choose_buyer(list(self.volunteers.values()), office, refill, self.repo.all(), now, self.policy)
        if volunteer:
            refill.move_to(State.OFFERED, now, f"offered to {volunteer.id}")
            refill.offered_to = volunteer.id
            refill.offer_expires_at = now + self.policy.offer_timeout
            msgs.dm(volunteer.id, f"The {office.name} snack box is empty. Can you refill it? Budget: up to {limit}. "
                                  f"Reply 'accept {refill.id}' or 'decline {refill.id}' by "
                                  f"{self._local_time(office, refill.offer_expires_at)}.")
            return

        if refill.state != State.OPEN:
            refill.move_to(State.OPEN, now, "no volunteer available")
        today = self._today(refill, now)
        if refill.announced_on != today:
            refill.announced_on = today
            msgs.channel(office.id, f"The snack box is empty and no volunteer is available today. "
                                    f"Anyone can take it: reply 'accept {refill.id}'.")

    def _submit_claim(self, refill: Refill, now: datetime, msgs: Messages) -> None:
        office = self.offices[refill.office_id]
        refill.claim_id = self.hr.create_claim(
            employee_id=refill.buyer_id,
            amount=refill.amount,
            description=f"Snacks for the {office.name} office snack counter (refill {refill.id})",
            receipt=refill.receipt,
        )
        refill.move_to(State.CLAIM_SUBMITTED, now, f"HR claim {refill.claim_id}")
        msgs.dm(refill.buyer_id, f"Claim {refill.claim_id} for {refill.amount} sent to HR.")

    def _save(self, refill: Refill, msgs: Messages) -> Refill:
        saved = self.repo.save(refill)
        msgs.send(self.chat)
        return saved

    def _today(self, refill: Refill, now: datetime) -> date:
        return now.astimezone(self.offices[refill.office_id].tz).date()

    def _name(self, user_id: str | None) -> str:
        volunteer = self.volunteers.get(user_id or "")
        return volunteer.name if volunteer else str(user_id)

    @staticmethod
    def _local_time(office: Office, ts: datetime) -> str:
        return ts.astimezone(office.tz).strftime("%a %d %b %H:%M %Z")
