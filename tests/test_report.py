"""Monthly totals are correct across both currencies."""
from datetime import datetime, timezone

from conftest import World, inr, nok


def test_monthly_total_converts_each_office_to_nok(world):
    world.refill("oslo", nok(600), items=["Chips", "fruit"])
    world.refill("oslo", nok("400.50"), items=["chips"])
    world.refill("blr", inr(2000))
    world.refill("blr", inr("1333.33"))

    report = world.svc.monthly_report("2026-11")
    oslo, blr = report.offices
    assert oslo.spent == nok("1000.50") and oslo.remaining == nok("4999.50") and oslo.refill_count == 2
    assert oslo.top_items[0] == ("chips", 2)
    assert blr.spent == inr("3333.33")
    assert blr.spent_nok == nok("416.67")  # 3 333.33 x 0.125 = 416.66625, rounded once
    assert report.total_nok == nok("1417.17")


def test_purchase_counts_in_the_month_of_the_office_local_date():
    # 30 Nov 22:30 UTC is still November in Oslo but already 1 December in Bengaluru.
    world = World(start=datetime(2026, 11, 30, 22, 30, tzinfo=timezone.utc))
    world.refill("oslo", nok(500), buyer="kari")
    world.refill("blr", inr(1000), buyer="kiran")

    november = world.svc.monthly_report("2026-11")
    december = world.svc.monthly_report("2026-12")
    assert november.total_nok == nok(500)
    assert december.total_nok == nok(120)  # 1 000 INR at the December rate of 0.120
