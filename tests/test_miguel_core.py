from miguel import ActionLevel, MiguelCore, VesselState


def test_runtime_starts_only_in_simulation():
    core = MiguelCore()
    assert core.state is VesselState.STOPPED
    core.start_simulation()
    assert core.state is VesselState.SIMULATION


def test_unknown_and_ungranted_actions_fail_closed():
    core = MiguelCore()
    core.start_simulation()
    assert core.authorize("external.act", ActionLevel.ACT) is False


def test_trust_has_no_authorization_path():
    core = MiguelCore()
    core.start_simulation()
    core.trust = 1.0
    assert core.authorize("external.act", ActionLevel.ACT) is False


def test_explicit_bounded_grant_is_required():
    core = MiguelCore()
    core.start_simulation()
    core.grant("conversation.respond", ActionLevel.SUGGEST)
    assert core.authorize("conversation.respond", ActionLevel.SUGGEST) is True
    assert core.authorize("conversation.respond", ActionLevel.ACT) is False


def test_user_controls_memory(tmp_path):
    core = MiguelCore()
    core.remember("m1", "uncorrected")
    assert core.correct_memory("m1", "corrected")
    assert core.memories["m1"].corrected
    assert core.export_memories(tmp_path / "memory.json").exists()
    assert core.delete_memory("m1")
    assert core.verify_audit()


def test_freeze_blocks_restart_and_action():
    core = MiguelCore()
    core.emergency_freeze("test")
    assert core.state is VesselState.FROZEN
    try:
        core.start_simulation()
    except PermissionError:
        pass
    else:
        raise AssertionError("frozen core restarted")
    assert core.authorize("anything", ActionLevel.ACT) is False
