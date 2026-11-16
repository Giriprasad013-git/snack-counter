"""Interfaces to the chat tool, the HR system and the clock.

The real implementations would call the chat and HR APIs. The tests use the
simulated versions in fakes.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .money import Money


class ChatPort(Protocol):
    def send_dm(self, user_id: str, text: str) -> None: ...

    def post_to_channel(self, office_id: str, text: str) -> None: ...


class HrPort(Protocol):
    def create_claim(self, *, employee_id: str, amount: Money, description: str, receipt: bytes) -> str:
        """Create a reimbursement claim and return its ID."""
        ...

    def is_approved(self, claim_id: str) -> bool: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
