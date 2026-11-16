"""A refill goes from empty to reimbursed, and an office has only one refill at a time."""
import pytest
from conftest import MONDAY, inr, nok

from snack_counter import NotAllowed, RefillState as S
from snack_counter.models import InvalidTransition, Refill


def test_refill_goes_from_empty_to_reimbursed(world):
    r = world.svc.report_empty("oslo", "someone")
    assert r.state == S.OFFERED and r.offered_to == "kari"
    assert any("Can you refill it?" in m for m in world.chat.dms_to("kari"))

    r = world.svc.commit(r.id, "kari")
    assert r.state == S.COMMITTED
    assert "Kari is refilling the snack box." in world.chat.channel("oslo")

    r = world.svc.upload_receipt(r.id, "kari", nok(850), b"receipt.jpg")
    assert r.state == S.CLAIM_SUBMITTED
    claim = world.hr.claims[r.claim_id]
    assert (claim.employee_id, claim.amount, claim.receipt) == ("kari", nok(850), b"receipt.jpg")

    world.clock.advance(days=3)
    world.svc.tick()
    assert world.svc.repo.get(r.id).state == S.CLAIM_SUBMITTED  # HR hasn't approved yet

    world.hr.approve(r.claim_id)
    world.svc.tick()
    assert world.svc.repo.get(r.id).state == S.REIMBURSED
    assert any("HR approved" in m for m in world.chat.dms_to("kari"))


def test_second_empty_report_joins_the_open_refill(world):
    first = world.svc.report_empty("oslo", "alice")
    second = world.svc.report_empty("oslo", "bob")
    assert second.id == first.id
    assert world.svc.repo.get(first.id).reported_by == ["alice", "bob"]
    assert len(world.svc.repo.for_office("oslo")) == 1


def test_report_while_someone_is_buying_does_not_start_a_second_refill(world):
    r = world.svc.report_empty("oslo", "alice")
    world.svc.commit(r.id, "kari")
    again = world.svc.report_empty("oslo", "bob")
    assert again.id == r.id and again.state == S.COMMITTED


def test_new_refill_can_start_once_the_box_is_full_again(world):
    first = world.refill("oslo", nok(500))
    second = world.svc.report_empty("oslo", "someone")
    assert second.id != first.id and second.state == S.OFFERED


def test_offices_are_independent(world):
    oslo = world.svc.report_empty("oslo", "x")
    blr = world.svc.report_empty("blr", "y")
    assert oslo.id != blr.id
    assert blr.offered_to == "kiran"


def test_only_the_buyer_can_upload_the_receipt(world):
    r = world.svc.report_empty("oslo", "x")
    world.svc.commit(r.id, "kari")
    with pytest.raises(NotAllowed):
        world.svc.upload_receipt(r.id, "nora", nok(500), b"r")


def test_receipt_must_be_in_the_office_currency(world):
    r = world.svc.report_empty("oslo", "x")
    world.svc.commit(r.id, "kari")
    with pytest.raises(NotAllowed):
        world.svc.upload_receipt(r.id, "kari", inr(500), b"r")


def test_states_cannot_be_skipped():
    r = Refill(id="R1", office_id="oslo", reported_at=MONDAY, reported_by=["x"])
    with pytest.raises(InvalidTransition):
        r.move_to(S.REIMBURSED, MONDAY)
