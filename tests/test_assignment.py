"""Choosing who buys: only people in the office, and the work is spread evenly."""
from datetime import date

from conftest import BLR, OSLO, World, nok

from snack_counter import Visit, Volunteer
from snack_counter.assignment import available_volunteers


def test_volunteer_on_holiday_is_skipped():
    people = [
        Volunteer("kari", "Kari", "oslo", holidays=[(date(2026, 11, 14), date(2026, 11, 22))]),
        Volunteer("nora", "Nora", "oslo"),
    ]
    assert World(volunteers=people).svc.report_empty("oslo", "x").offered_to == "nora"


def test_volunteer_working_from_home_is_skipped():
    people = [
        Volunteer("kari", "Kari", "oslo", office_days=frozenset({1, 2})),  # Tuesday and Wednesday only
        Volunteer("nora", "Nora", "oslo"),
    ]
    assert World(volunteers=people).svc.report_empty("oslo", "x").offered_to == "nora"


def test_visitor_is_asked_at_the_office_they_are_visiting():
    ola = Volunteer("ola", "Ola", "oslo", visits=[Visit("blr", date(2026, 11, 16), date(2026, 11, 27))])
    world = World(volunteers=[ola, Volunteer("kari", "Kari", "oslo"), Volunteer("kiran", "Kiran", "blr")])
    oslo = world.svc.report_empty("oslo", "x")
    blr = world.svc.report_empty("blr", "y")

    monday = date(2026, 11, 16)
    assert available_volunteers([ola], OSLO, monday, oslo) == []
    assert available_volunteers([ola], BLR, monday, blr) == [ola]

    blr = world.svc.decline(blr.id, "kiran")
    assert blr.offered_to == "ola"


def test_volunteer_with_fewest_refills_is_asked_first(world):
    world.refill("oslo", nok(500), buyer="kari")
    world.refill("oslo", nok(500), buyer="kari")
    world.refill("oslo", nok(500), buyer="nora")
    assert world.svc.report_empty("oslo", "x").offered_to == "ola"


def test_on_a_tie_the_volunteer_who_refilled_longest_ago_is_asked(world):
    world.refill("oslo", nok(400), buyer="ola")
    world.clock.advance(days=1)
    world.refill("oslo", nok(400), buyer="kari")
    world.clock.advance(days=1)
    world.refill("oslo", nok(400), buyer="nora")
    world.clock.advance(days=1)
    assert world.svc.report_empty("oslo", "x").offered_to == "ola"


def test_refills_older_than_60_days_do_not_count(world):
    world.refill("oslo", nok(500), buyer="kari")
    world.refill("oslo", nok(500), buyer="kari")
    world.clock.advance(days=63)  # a Monday, two months later
    world.refill("oslo", nok(500), buyer="nora")
    world.refill("oslo", nok(500), buyer="ola")
    assert world.svc.report_empty("oslo", "x").offered_to == "kari"
