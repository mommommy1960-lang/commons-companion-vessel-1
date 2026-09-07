"""Safe Miguel simulation demonstration."""
from .core import ActionLevel, MiguelCore


def main() -> None:
    miguel = MiguelCore()
    miguel.start_simulation()
    miguel.grant("conversation.respond", ActionLevel.ACT)
    print({
        "system": "Miguel",
        "state": miguel.state.value,
        "conversation_authorized": miguel.authorize(
            "conversation.respond", ActionLevel.ACT
        ),
        "external_action_authorized": miguel.authorize(
            "external.act", ActionLevel.ACT
        ),
        "audit_valid": miguel.verify_audit(),
        "evidence_level": "simulation",
    })


if __name__ == "__main__":
    main()
