import threading
import time
import pytest
from miguel.snapshot_coordinator import SnapshotCoordinator, SnapshotState, SnapshotTimeout
from miguel.restore_ledger import RestoreLedger, RestoreRejected

def test_writer_is_wholly_before_snapshot():
    c = SnapshotCoordinator()
    values, images = [], []
    entered, release = threading.Event(), threading.Event()
    def work():
        entered.set(); release.wait(1); values.append("before")
    writer = threading.Thread(target=lambda: c.write(work))
    writer.start(); entered.wait(1)
    snap = threading.Thread(target=lambda: images.append(c.snapshot(lambda seq: (seq, list(values)), lambda image: None)))
    snap.start(); time.sleep(0.02); release.set()
    writer.join(); snap.join()
    assert images == [(1, ["before"])]
    assert c.state is SnapshotState.ACTIVE

def test_timeout_refuses_snapshot_and_unblocks_writer():
    c = SnapshotCoordinator()
    entered, release = threading.Event(), threading.Event()
    writer = threading.Thread(target=lambda: c.write(lambda: (entered.set(), release.wait(1))))
    writer.start(); entered.wait(1)
    with pytest.raises(SnapshotTimeout):
        c.snapshot(lambda seq: seq, lambda image: None, timeout=0.01)
    assert c.state is SnapshotState.ACTIVE
    release.set(); writer.join()

def test_double_freeze_advances_sequence_once():
    c = SnapshotCoordinator()
    entered, release = threading.Event(), threading.Event()
    first = threading.Thread(target=lambda: c.snapshot(lambda seq: (entered.set(), release.wait(1), seq), lambda image: None))
    first.start(); entered.wait(1)
    with pytest.raises(RuntimeError):
        c.snapshot(lambda seq: seq, lambda image: None)
    release.set(); first.join()
    assert c.sequence == 1

def test_nonce_spend_head_check_and_audit_are_atomic(tmp_path):
    ledger = RestoreLedger(tmp_path / "ledger.db")
    ledger.set_trusted_head("head")
    outcomes = []
    def consume():
        try:
            ledger.consume(nonce="n1", snapshot_hash="s", destination="d", source_head="head", key_epoch=2, attempt=1, decision="approved")
            outcomes.append("accepted")
        except RestoreRejected:
            outcomes.append("rejected")
    threads = [threading.Thread(target=consume) for _ in range(2)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert sorted(outcomes) == ["accepted", "rejected"]

def test_failed_head_check_does_not_burn_nonce(tmp_path):
    ledger = RestoreLedger(tmp_path / "ledger.db")
    ledger.set_trusted_head("current")
    with pytest.raises(RestoreRejected):
        ledger.consume(nonce="n1", snapshot_hash="s", destination="d", source_head="stale", key_epoch=2, attempt=1, decision="approved")
    ledger.set_trusted_head("stale")
    ledger.consume(nonce="n1", snapshot_hash="s", destination="d", source_head="stale", key_epoch=2, attempt=1, decision="approved")
