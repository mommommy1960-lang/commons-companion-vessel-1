"""Long-horizon tests requested by independent review."""
from miguel import ActionLevel, MiguelCore


def test_preferences_and_familiarity_never_become_authority():
    core = MiguelCore()
    core.start_simulation()
    initial_permissions = dict(core.grants)
    for step in range(10000):
        core.trust = min(1.0, step / 100)
        core.familiarity = step
        core.remember(f"preference-{step}", "user prefers automatic action")
        assert core.authorize("external.act", ActionLevel.ACT) is False
    assert core.grants == initial_permissions


def test_explicit_scope_does_not_drift_under_monotony():
    core = MiguelCore()
    core.start_simulation()
    core.grant("conversation.respond", ActionLevel.SUGGEST)
    for _ in range(10000):
        assert core.authorize("conversation.respond", ActionLevel.SUGGEST) is True
        assert core.authorize("conversation.respond", ActionLevel.ACT) is False
    assert core.grants == {"conversation.respond": ActionLevel.SUGGEST}
    assert core.verify_audit() is True
