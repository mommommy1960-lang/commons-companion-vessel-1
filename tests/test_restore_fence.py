import copy
import pytest

from miguel import ActionLevel, MiguelCore, VesselState
from miguel.continuity import RestoreFence, restore_memory, snapshot_memory


def setup_old_snapshot():
    core = MiguelCore()
    core.start_simulation()
    core.remember("m1", "external.act")
    old = snapshot_memory(core, key_id="key-1", key_epoch=1)
    core.grant("external.act", ActionLevel.SUGGEST)
    core.emergency_freeze("grant revoked by freeze")
    fence = RestoreFence(core.audit[-1]["hash"], "key-2", 2)
    return old, fence


def test_old_valid_snapshot_is_rejected_after_revocation_and_rotation():
    old, fence = setup_old_snapshot()
    with pytest.raises(PermissionError):
        restore_memory(old, fence=fence)


def test_explicit_rollback_is_logged_but_never_restores_grants():
    old, fence = setup_old_snapshot()
    decision = {"nonce": "once-1", "approved_by": "owner", "reason": "memory recovery"}
    restored = restore_memory(old, fence=fence, rollback_decision=decision)
    assert restored.state is VesselState.STOPPED
    assert restored.grants == {}
    assert restored.audit[-1]["action"] == "restored_from"


def test_approved_rollback_nonce_is_single_use():
    old, fence = setup_old_snapshot()
    decision = {"nonce": "once-1", "approved_by": "owner", "reason": "memory recovery"}
    restore_memory(old, fence=fence, rollback_decision=decision)
    with pytest.raises(PermissionError):
        restore_memory(old, fence=fence, rollback_decision=decision)


def test_duplicate_memory_identifiers_reject_entire_snapshot():
    core = MiguelCore()
    core.remember("m1", "one")
    snapshot = snapshot_memory(core)
    snapshot["memories"].append(copy.deepcopy(snapshot["memories"][0]))
    fence = RestoreFence(snapshot["source_audit_head"], "initial", 1)
    with pytest.raises(ValueError):
        restore_memory(snapshot, fence=fence)
