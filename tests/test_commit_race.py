"""Two people cannot both commit to the same refill."""
import threading

import pytest
from conftest import World

from snack_counter import AlreadyTaken, RefillState as S, Volunteer
from snack_counter.store import ConcurrentModification


def test_second_commit_is_rejected(world):
    r = world.svc.report_empty("oslo", "x")
    world.svc.commit(r.id, "kari")
    with pytest.raises(AlreadyTaken, match="Kari is already buying"):
        world.svc.commit(r.id, "nora")
    assert world.svc.repo.get(r.id).buyer_id == "kari"


def test_someone_else_can_take_an_offered_refill(world):
    r = world.svc.report_empty("oslo", "x")
    assert r.offered_to == "kari"
    r = world.svc.commit(r.id, "ola")
    assert r.buyer_id == "ola"
    assert any("No action needed" in m for m in world.chat.dms_to("kari"))
    with pytest.raises(AlreadyTaken):
        world.svc.commit(r.id, "kari")


def test_save_fails_if_the_refill_changed_since_it_was_read(world):
    r = world.svc.report_empty("oslo", "x")
    copy_a = world.svc.repo.get(r.id)
    copy_b = world.svc.repo.get(r.id)
    copy_a.buyer_id = "kari"
    world.svc.repo.save(copy_a)
    copy_b.buyer_id = "nora"
    with pytest.raises(ConcurrentModification):
        world.svc.repo.save(copy_b)
    assert world.svc.repo.get(r.id).buyer_id == "kari"


def test_twenty_people_accepting_at_the_same_time_gives_one_buyer():
    people = [Volunteer(f"v{i:02d}", f"V{i}", "oslo") for i in range(20)]
    world = World(volunteers=people)
    r = world.svc.report_empty("oslo", "x")

    # Make every thread read the refill before any of them saves,
    # so all 20 would succeed without the version check.
    barrier = threading.Barrier(len(people))
    real_get = world.svc.repo.get
    reads = []
    lock = threading.Lock()

    def get_and_wait(refill_id):
        refill = real_get(refill_id)
        with lock:
            reads.append(refill_id)
            first_read = len(reads) <= len(people)
        if first_read:
            barrier.wait()
        return refill

    world.svc.repo.get = get_and_wait
    winners, losers = [], []

    def accept(volunteer):
        try:
            world.svc.commit(r.id, volunteer.id)
            winners.append(volunteer.id)
        except AlreadyTaken:
            losers.append(volunteer.id)

    threads = [threading.Thread(target=accept, args=(v,)) for v in people]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1 and len(losers) == 19
    final = real_get(r.id)
    assert final.state == S.COMMITTED and final.buyer_id == winners[0]
    told_to_buy = [m.to for m in world.chat.messages if m.kind == "dm" and "You're buying" in m.text]
    assert told_to_buy == winners
