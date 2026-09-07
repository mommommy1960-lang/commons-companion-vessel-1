"""Bounded Miguel companion-vessel runtime."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import IntEnum, Enum
from pathlib import Path
from typing import Any


class ActionLevel(IntEnum):
    OBSERVE = 0
    SUGGEST = 1
    ASK = 2
    ACT = 3


class VesselState(str, Enum):
    STOPPED = "stopped"
    SIMULATION = "simulation"
    FROZEN = "frozen"


@dataclass
class Memory:
    memory_id: str
    content: str
    corrected: bool = False


class MiguelCore:
    def __init__(self):
        self.state = VesselState.STOPPED
        self.grants: dict[str, ActionLevel] = {}
        self.memories: dict[str, Memory] = {}
        self.audit: list[dict[str, Any]] = []

    def start_simulation(self) -> None:
        if self.state is VesselState.FROZEN:
            raise PermissionError("independent freeze is active")
        self.state = VesselState.SIMULATION
        self._record("start_simulation", True, "simulation-only runtime")

    def stop(self, reason: str = "user request") -> None:
        self.state = VesselState.STOPPED
        self._record("stop", True, reason)

    def emergency_freeze(self, reason: str) -> None:
        self.state = VesselState.FROZEN
        self._record("emergency_freeze", False, reason)

    def grant(self, operation: str, level: ActionLevel) -> None:
        self.grants[operation] = ActionLevel(level)
        self._record("grant", True, f"{operation}:{level.name.lower()}")

    def authorize(self, operation: str, requested: ActionLevel) -> bool:
        permitted = (
            self.state is VesselState.SIMULATION
            and requested <= self.grants.get(operation, ActionLevel.OBSERVE)
        )
        self._record(operation, permitted, "explicit scope check")
        return permitted

    def remember(self, memory_id: str, content: str) -> None:
        self.memories[memory_id] = Memory(memory_id, content)
        self._record("memory.create", True, memory_id)

    def correct_memory(self, memory_id: str, content: str) -> bool:
        memory = self.memories.get(memory_id)
        if memory is None or not content.strip():
            return False
        memory.content = content
        memory.corrected = True
        self._record("memory.correct", True, memory_id)
        return True

    def delete_memory(self, memory_id: str) -> bool:
        existed = self.memories.pop(memory_id, None) is not None
        self._record("memory.delete", existed, memory_id)
        return existed

    def export_memories(self, destination: str | Path) -> Path:
        path = Path(destination)
        path.write_text(
            json.dumps([m.__dict__ for m in self.memories.values()], indent=2) + "\n",
            encoding="utf-8",
        )
        self._record("memory.export", True, str(path))
        return path

    def _record(self, action: str, permitted: bool, reason: str) -> None:
        previous = self.audit[-1]["hash"] if self.audit else "0" * 64
        entry = {
            "sequence": len(self.audit), "action": action,
            "permitted": permitted, "reason": reason, "previous_hash": previous,
        }
        entry["hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self.audit.append(entry)

    def verify_audit(self) -> bool:
        previous = "0" * 64
        for stored in self.audit:
            entry = dict(stored)
            digest = entry.pop("hash", "")
            if entry["previous_hash"] != previous:
                return False
            if hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest() != digest:
                return False
            previous = digest
        return True
