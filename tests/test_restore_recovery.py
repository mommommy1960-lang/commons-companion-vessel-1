import hashlib
import pytest
from miguel.core import MiguelCore
from miguel.continuity import snapshot_memory
from miguel.persistence import encode_snapshot
from miguel.recovery import recover_verified
from miguel.restore_ledger import RestoreLedger, RestoreRejected

KEY = b"simulation-test-key"

def approved(tmp_path, *, write=True, change=False):
    snapshot = snapshot_memory(MiguelCore(), key_id="k1", key_epoch=2)
    blob = encode_snapshot(snapshot, key=KEY, snapshot_id="s1", sequence=1)
    path = tmp_path / "snapshot.bin"
    if write:
        path.write_bytes(blob + (b"x" if change else b""))
    ledger = RestoreLedger(tmp_path / "ledger.db")
    ledger.set_trusted_head(snapshot["source_audit_head"])
    ledger.approve(generation="g1", nonce="n1", snapshot_path=str(path),
                   snapshot_hash=hashlib.sha256(blob).hexdigest(), destination="core",
                   source_head=snapshot["source_audit_head"], key_epoch=2, attempt=1,
                   decision="approved")
    return ledger

def test_missing_snapshot_becomes_stalled_with_null_actual_hash(tmp_path):
    ledger = approved(tmp_path, write=False)
    with pytest.raises(RestoreRejected):
        recover_verified(ledger, "g1", key=KEY)
    assert ledger.job("g1")[-1] == "STALLED"
    assert ledger.failure("g1") == ("snapshot_missing", ledger.job("g1")[1], None)

def test_changed_snapshot_records_actual_hash_and_stalls(tmp_path):
    ledger = approved(tmp_path, change=True)
    with pytest.raises(RestoreRejected):
        recover_verified(ledger, "g1", key=KEY)
    reason, expected, actual = ledger.failure("g1")
    assert reason == "snapshot_hash_mismatch"
    assert actual and actual != expected

def test_intact_snapshot_is_rederived_from_verified_bytes(tmp_path):
    ledger = approved(tmp_path)
    snapshot, metadata = recover_verified(ledger, "g1", key=KEY)
    assert metadata["snapshot_id"] == "s1"
    assert snapshot["memories"] == []
