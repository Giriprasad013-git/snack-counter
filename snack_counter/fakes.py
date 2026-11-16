"""Simulated chat tool, HR system and clock, used by the tests."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .money import Money


class FakeClock:
    def __init__(self, start: datetime):
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)

    def set(self, when: datetime) -> None:
        self._now = when


@dataclass(frozen=True)
class ChatMessage:
    kind: str  # "dm" or "channel"
    to: str  # user ID or office ID
    text: str


class FakeChat:
    """Records every message so tests can check what people were told."""

    def __init__(self):
        self.messages: list[ChatMessage] = []

    def send_dm(self, user_id: str, text: str) -> None:
        self.messages.append(ChatMessage("dm", user_id, text))

    def post_to_channel(self, office_id: str, text: str) -> None:
        self.messages.append(ChatMessage("channel", office_id, text))

    def dms_to(self, user_id: str) -> list[str]:
        return [m.text for m in self.messages if m.kind == "dm" and m.to == user_id]

    def channel(self, office_id: str) -> list[str]:
        return [m.text for m in self.messages if m.kind == "channel" and m.to == office_id]


@dataclass
class FakeClaim:
    employee_id: str
    amount: Money
    description: str
    receipt: bytes
    approved: bool = False


class FakeHr:
    """Stores claims in memory. Tests call approve() to simulate HR approving a claim."""

    def __init__(self):
        self.claims: dict[str, FakeClaim] = {}

    def create_claim(self, *, employee_id: str, amount: Money, description: str, receipt: bytes) -> str:
        claim_id = f"HR-{len(self.claims) + 1:04d}"
        self.claims[claim_id] = FakeClaim(employee_id, amount, description, receipt)
        return claim_id

    def is_approved(self, claim_id: str) -> bool:
        return self.claims[claim_id].approved

    def approve(self, claim_id: str) -> None:
        self.claims[claim_id].approved = True
