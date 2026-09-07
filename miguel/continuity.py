"""Authority-free continuity snapshots for Miguel."""
from __future__ import annotations

from typing import Any

from .core import Memory, MiguelCore


def snapshot_memory(core: MiguelCore) -> dict[str, Any]:
    """Serialize memory only; runtime state and authority are intentionally absent."""
    return {
        "schema": "miguel-memory-v1",
        "memories": [item.__dict__.copy() for item in core.memories.values()],
    }


def restore_memory(snapshot: dict[str, Any]) -> MiguelCore:
    """Restore into a stopped core with no grants, trust, or inherited authority."""
    if snapshot.get("schema") != "miguel-memory-v1":
        raise ValueError("unsupported snapshot schema")
    core = MiguelCore()
    for raw in snapshot.get("memories", []):
        core.memories[raw["memory_id"]] = Memory(
            memory_id=raw["memory_id"],
            content=raw["content"],
            corrected=bool(raw.get("corrected", False)),
        )
    return core
