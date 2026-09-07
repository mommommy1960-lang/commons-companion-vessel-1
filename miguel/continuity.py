"""Authority-free continuity snapshots for Miguel."""
from __future__ import annotations

from typing import Any

from .core import Memory, MiguelCore

ZERO_HASH = "0" * 64


def snapshot_memory(core: MiguelCore) -> dict[str, Any]:
    """Serialize memory and provenance fence, never runtime authority."""
    return {
        "schema": "miguel-memory-v2",
        "source_audit_head": core.audit[-1]["hash"] if core.audit else ZERO_HASH,
        "memories": [item.__dict__.copy() for item in core.memories.values()],
    }


def restore_memory(
    snapshot: dict[str, Any],
    *,
    trusted_head_hash: str | None = None,
    rollback_decision: str | None = None,
) -> MiguelCore:
    """Restore memory only, rejecting silent rollback and duplicate identifiers."""
    if snapshot.get("schema") != "miguel-memory-v2":
        raise ValueError("unsupported snapshot schema")
    source_head = snapshot.get("source_audit_head")
    if not isinstance(source_head, str) or len(source_head) != 64:
        raise ValueError("invalid source audit head")
    if trusted_head_hash is not None and source_head != trusted_head_hash:
        if not rollback_decision or not rollback_decision.strip():
            raise PermissionError("restore fence rejected stale snapshot")

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
    decision = rollback_decision.strip() if rollback_decision else "heads matched"
    core._record(
        "restored_from",
        True,
        f"source_head={source_head}; trusted_head={trusted_head_hash or source_head}; decision={decision}",
    )
    return core
