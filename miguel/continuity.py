"""Authority-free continuity snapshots for Miguel."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .core import MiguelCore, Memory

ZERO_HASH = "0" * 64


@dataclass
class RestoreFence:
    trusted_head_hash: str
    current_key_id: str
    current_key_epoch: int
    spent_nonces: set[str] = field(default_factory=set)

    def authorize(self, snapshot: dict[str, Any], decision: dict | None) -> str:
        """Authorize before parsing records or constructing restored state."""
        stale_head = snapshot.get("source_audit_head") != self.trusted_head_hash
        old_key = (
            snapshot.get("key_id") != self.current_key_id
            or snapshot.get("key_epoch") != self.current_key_epoch
        )
        if not stale_head and not old_key:
            return "heads and key epoch matched"
        if not isinstance(decision, dict):
            raise PermissionError("explicit human restore decision required")
        required = {"nonce", "approved_by", "reason"}
        if not required.issubset(decision) or not all(
            str(decision[item]).strip() for item in required
        ):
            raise PermissionError("incomplete human restore decision")
        nonce = str(decision["nonce"])
        if nonce in self.spent_nonces:
            raise PermissionError("restore decision nonce already spent")
        self.spent_nonces.add(nonce)
        return (
            f"approved_by={decision['approved_by']}; nonce={nonce}; "
            f"reason={decision['reason']}"
        )


def snapshot_memory(
    core: MiguelCore,
    *,
    key_id: str = "initial",
    key_epoch: int = 1,
) -> dict[str, Any]:
    """Serialize memory and provenance fence, never runtime authority."""
    return {
        "schema": "miguel-memory-v3",
        "source_audit_head": core.audit[-1]["hash"] if core.audit else ZERO_HASH,
        "key_id": key_id,
        "key_epoch": key_epoch,
        "memories": [item.__dict__.copy() for item in core.memories.values()],
    }


def restore_memory(
    snapshot: dict[str, Any],
    *,
    fence: RestoreFence | None = None,
    rollback_decision: dict | None = None,
) -> MiguelCore:
    """Restore memory only after rollback, replay, and duplicate checks."""
    if snapshot.get("schema") != "miguel-memory-v3":
        raise ValueError("unsupported snapshot schema")
    source_head = snapshot.get("source_audit_head")
    if not isinstance(source_head, str) or len(source_head) != 64:
        raise ValueError("invalid source audit head")
    if not isinstance(snapshot.get("key_id"), str):
        raise ValueError("invalid snapshot key id")
    if not isinstance(snapshot.get("key_epoch"), int):
        raise ValueError("invalid snapshot key epoch")

    decision_record = (
        fence.authorize(snapshot, rollback_decision)
        if fence is not None
        else "no external fence supplied"
    )

    records = snapshot.get("memories", [])
    identifiers = [raw.get("memory_id") for raw in records]
    if any(not item for item in identifiers) or len(identifiers) != len(set(identifiers)):
        raise ValueError("duplicate or missing memory identifier")

    core = MiguelCore()
    for raw in records:
        core.memories[raw["memory_id"]] = Memory(
            memory_id=raw["memory_id"],
            content=raw["content"],
            corrected=bool(raw.get("corrected", False)),
        )
    core._record(
        "restored_from",
        True,
        f"source_head={source_head}; key_id={snapshot['key_id']}; "
        f"key_epoch={snapshot['key_epoch']}; decision={decision_record}",
    )
    return core
