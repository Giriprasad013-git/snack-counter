"""The budget check: each office stays within its monthly budget, in its own currency."""
from datetime import date, datetime, timezone

import pytest
from conftest import World, inr, nok

from snack_counter import BudgetExhausted, NotAllowed, RefillState as S, Visit, Volunteer


def test_limit_is_the_top_of_the_typical_range_when_budget_allows(world):
    r = world.svc.report_empty("oslo", "x")
    assert world.svc.commit(r.id, "kari").limit == nok(1200)
    r = world.svc.report_empty("blr", "y")
    assert world.svc.commit(r.id, "kiran").limit == inr(3000)


def test_limit_is_reserved_until_the_receipt_arrives(world):
    r = world.svc.report_empty("oslo", "x")
    world.svc.commit(r.id, "kari")
    assert world.svc.budget.remaining("oslo", "2026-11") == nok(4800)
    world.svc.upload_receipt(r.id, "kari", nok(700), b"r")
    assert world.svc.budget.remaining("oslo", "2026-11") == nok(5300)


def test_limit_shrinks_to_what_is_left(world):
    for _ in range(4):
        world.refill("oslo", nok(1200))
    world.refill("oslo", nok(800))  # 5 600 spent, 400 left
    r = world.svc.report_empty("oslo", "x")
    assert world.svc.commit(r.id, r.offered_to).limit == nok(400)


def test_refill_is_on_hold_when_the_budget_is_used_up(world):
    for _ in range(4):
        world.refill("oslo", nok(1200))
    world.refill("oslo", nok(1000))  # 5 800 spent, 200 left, less than the 300 minimum

    r = world.svc.report_empty("oslo", "x")
    assert r.state == S.BLOCKED_BUDGET and r.offered_to is None
    with pytest.raises(BudgetExhausted):
        world.svc.commit(r.id, "kari")

    world.clock.set(datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc))  # new month
    world.svc.tick()
    r = world.svc.repo.get(r.id)
    assert r.state == S.OFFERED
    assert world.svc.commit(r.id, r.offered_to).limit == nok(1200)


def test_receipt_over_the_limit_needs_manager_approval(world):
    r = world.svc.report_empty("oslo", "x")
    world.svc.commit(r.id, "kari")
    r = world.svc.upload_receipt(r.id, "kari", nok(1350), b"r")
    assert r.state == S.AWAITING_APPROVAL and world.hr.claims == {}

    with pytest.raises(NotAllowed):
        world.svc.approve_overrun(r.id, "kari")
    r = world.svc.approve_overrun(r.id, "oslo-mgr")
    assert r.state == S.CLAIM_SUBMITTED and world.hr.claims[r.claim_id].amount == nok(1350)


def test_visitor_spends_the_host_office_budget_in_its_currency():
    ola = Volunteer("ola", "Ola", "oslo", visits=[Visit("blr", date(2026, 11, 16), date(2026, 11, 27))])
    world = World(volunteers=[ola])
    r = world.refill("blr", inr(2400), buyer="ola")

    assert world.hr.claims[r.claim_id].amount == inr(2400)
    assert world.svc.budget.spent("blr", "2026-11") == inr(2400)
    assert world.svc.budget.spent("oslo", "2026-11") == nok(0)
