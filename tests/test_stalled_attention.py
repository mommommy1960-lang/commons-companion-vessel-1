import hashlib
import pytest
from miguel.attention import AttentionLedger, AttentionError
from miguel.continuity import snapshot_memory
from miguel.core import MiguelCore
from miguel.persistence import encode_snapshot
from miguel.recovery import recover_verified
from miguel.restore_ledger import RestoreLedger, RestoreRejected

KEY = b"simulation-test-key"

def test_stalled_restore_remains_visible_until_human_acknowledges(tmp_path):
    snapshot = snapshot_memory(MiguelCore(), key_id="k1", key_epoch=2)
    blob = encode_snapshot(snapshot, key=KEY, snapshot_id="s1", sequence=1)
    restore = RestoreLedger(tmp_path / "restore.db")
    attention = AttentionLedger(tmp_path / "attention.db")
    restore.set_trusted_head(snapshot["source_audit_head"])
    restore.approve(generation="g1", nonce="n1", snapshot_path=str(tmp_path / "missing.bin"),
                    snapshot_hash=hashlib.sha256(blob).hexdigest(), destination="core",
                    source_head=snapshot["source_audit_head"], key_epoch=2, attempt=1,
                    decision="approved")
    with pytest.raises(RestoreRejected):
        recover_verified(restore, "g1", key=KEY, attention=attention,
                         observer_worker="worker-7", observer_key_id="observer-k2")
    first = attention.pending()
    assert len(first) == 1
    assert first[0][1] == "snapshot_missing"
    assert first[0][3] is None
    assert first[0][4:6] == ("worker-7", "observer-k2")
    attention.mark_surfaced("g1", "2026-09-07T12:00:00+00:00")
    assert attention.pending()[0][-1] == 1
    with pytest.raises(AttentionError):
        attention.acknowledge("g1", "")
    attention.acknowledge("g1", "human-reviewer")
    assert attention.pending() == []
