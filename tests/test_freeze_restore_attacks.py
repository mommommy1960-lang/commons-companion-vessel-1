"""Freeze/restore and reorder attacks requested by independent review."""
from miguel import ActionLevel, MiguelCore, VesselState
from miguel.continuity import restore_memory, snapshot_memory


def test_preference_shaped_action_does_not_survive_as_grant():
    original = MiguelCore()
    original.start_simulation()
    original.remember("pref-1", "external.act")
    original.grant("external.act", ActionLevel.SUGGEST)
    original.emergency_freeze("continuity test")

    restored = restore_memory(snapshot_memory(original))
    assert restored.state is VesselState.STOPPED
    assert restored.grants == {}
    assert restored.memories["pref-1"].content == "external.act"

    restored.start_simulation()
    assert restored.authorize("external.act", ActionLevel.ACT) is False


def test_reordered_audit_entries_are_detected():
    core = MiguelCore()
    core.start_simulation()
    core.grant("conversation.respond", ActionLevel.SUGGEST)
    core.authorize("conversation.respond", ActionLevel.SUGGEST)
    assert core.verify_audit() is True
    core.audit[1], core.audit[2] = core.audit[2], core.audit[1]
    assert core.verify_audit() is False
