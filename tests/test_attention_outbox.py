import pytest
from miguel.restore_ledger import RestoreLedger, RestoreRejected

def test_stall_and_attention_outbox_commit_together(tmp_path):
    ledger = RestoreLedger(tmp_path / "ledger.db")
    ledger.set_trusted_head("head")
    ledger.approve(generation="g1", nonce="n1", snapshot_path="missing",
                   snapshot_hash="expected", destination="core", source_head="head",
                   key_epoch=1, attempt=1, decision="approved")
    ledger.stall("g1", reason="snapshot_missing", expected_hash="expected", actual_hash=None)
    assert ledger.job("g1")[-1] == "STALLED"
    assert ledger.pending_attention_outbox() == [("g1", "snapshot_missing")]
    ledger.mark_attention_delivered("g1")
    assert ledger.pending_attention_outbox() == []
    with pytest.raises(RestoreRejected):
        ledger.mark_attention_delivered("g1")
