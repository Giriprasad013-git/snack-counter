"""In-memory storage for refills.

It provides the two guarantees we would get from a database:
- only one active refill per office (a partial unique index in SQL)
- saves fail if the refill changed since it was read
  (UPDATE ... WHERE id = ? AND version = ?)

Callers always get copies, so a failed save leaves nothing half-changed.
"""
from __future__ import annotations

import copy
import itertools
import threading
from typing import Callable

from .models import Refill


class ConcurrentModification(Exception):
    pass


class RefillRepository:
    def __init__(self):
        self._lock = threading.Lock()
        self._refills: dict[str, Refill] = {}
        self._next_id = itertools.count(1)

    def create_if_no_active(self, office_id: str, new_refill: Callable[[str], Refill]) -> tuple[Refill, bool]:
        """Return the office's active refill, or create one. The bool says whether it was created."""
        with self._lock:
            for refill in self._refills.values():
                if refill.office_id == office_id and refill.is_active:
                    return copy.deepcopy(refill), False
            refill = new_refill(f"R{next(self._next_id):04d}")
            refill.version = 1
            self._refills[refill.id] = copy.deepcopy(refill)
            return refill, True

    def get(self, refill_id: str) -> Refill:
        with self._lock:
            return copy.deepcopy(self._refills[refill_id])

    def save(self, refill: Refill) -> Refill:
        with self._lock:
            stored = self._refills[refill.id]
            if stored.version != refill.version:
                raise ConcurrentModification(f"Refill {refill.id} was changed by someone else")
            refill.version += 1
            self._refills[refill.id] = copy.deepcopy(refill)
            return refill

    def all(self) -> list[Refill]:
        with self._lock:
            return [copy.deepcopy(r) for r in self._refills.values()]

    def for_office(self, office_id: str) -> list[Refill]:
        return [r for r in self.all() if r.office_id == office_id]
