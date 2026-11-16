"""A refill nobody completes is handed to someone else."""
from datetime import datetime, timezone

import pytest
from conftest import World, nok

from snack_counter import NotAllowed, RefillState as S


def test_unanswered_offer_goes_to_the_next_volunteer(world):
    r = world.svc.report_empty("oslo", "x")
    assert r.offered_to == "kari"

    world.clock.advance(hours=1, minutes=59)
    world.svc.tick()
    assert world.svc.repo.get(r.id).offered_to == "kari"

    world.clock.advance(minutes=1)
    world.svc.tick()
    assert world.svc.repo.get(r.id).offered_to == "nora"
    assert any("asked someone else" in m for m in world.chat.dms_to("kari"))


def test_declined_offer_goes_to_the_next_volunteer(world):
    r = world.svc.report_empty("oslo", "x")
    r = world.svc.decline(r.id, "kari")
    assert r.offered_to == "nora"
    with pytest.raises(NotAllowed):
        world.svc.decline(r.id, "kari")


def test_buyer_who_misses_the_deadline_is_replaced(world):
    r = world.svc.report_empty("oslo", "x")
    world.svc.commit(r.id, "kari")
    assert world.svc.budget.reserved("oslo", "2026-11") == nok(1200)

    world.clock.advance(hours=24)
    world.svc.tick()

    r = world.svc.repo.get(r.id)
    assert r.state == S.OFFERED and r.offered_to == "nora" and r.buyer_id is None
    assert world.svc.budget.reserved("oslo", "2026-11") == nok(0)
    assert any("passed its deadline" in m for m in world.chat.dms_to("kari"))
    with pytest.raises(NotAllowed):
        world.svc.upload_receipt(r.id, "kari", nok(500), b"late")


def test_when_everyone_declines_the_channel_is_told_and_it_is_retried_next_day(world):
    r = world.svc.report_empty("oslo", "x")
    for person in ("kari", "nora", "ola"):
        r = world.svc.decline(r.id, person)
    assert r.state == S.OPEN
    assert any("Anyone can take it" in m for m in world.chat.channel("oslo"))

    world.clock.set(datetime(2026, 11, 17, 7, 0, tzinfo=timezone.utc))  # Tuesday 08:00 in Oslo
    world.svc.tick()
    assert world.svc.repo.get(r.id).offered_to == "kari"


def test_anyone_can_take_an_open_refill(world):
    r = world.svc.report_empty("oslo", "x")
    for person in ("kari", "nora", "ola"):
        r = world.svc.decline(r.id, person)
    r = world.svc.commit(r.id, "nora")
    assert r.state == S.COMMITTED and r.buyer_id == "nora"


def test_weekend_report_is_offered_on_monday():
    world = World(start=datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc))  # Saturday
    r = world.svc.report_empty("oslo", "x")
    assert r.state == S.OPEN

    world.clock.set(datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc))  # Monday
    world.svc.tick()
    assert world.svc.repo.get(r.id).offered_to == "kari"
