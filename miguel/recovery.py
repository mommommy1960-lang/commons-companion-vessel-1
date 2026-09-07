"""Fail-closed recovery from the durable snapshot named by an approval."""
from __future__ import annotations
import hashlib
from pathlib import Path
from .persistence import EnvelopeError, decode_snapshot
from .restore_ledger import RestoreLedger, RestoreRejected

def recover_verified(ledger: RestoreLedger, generation: str, *, key: bytes):
    job = ledger.job(generation)
    if job is None:
        raise RestoreRejected("unknown restore generation")
    path, expected, _destination, _head, _epoch, _parent, stage = job
    if stage not in ("APPROVED", "CONSTRUCTING"):
        raise RestoreRejected("generation is not recoverable")
    try:
        held = Path(path).read_bytes()
    except FileNotFoundError:
        ledger.stall(generation, reason="snapshot_missing", expected_hash=expected, actual_hash=None)
        raise RestoreRejected("snapshot missing; generation stalled")
    actual = hashlib.sha256(held).hexdigest()
    if actual != expected:
        ledger.stall(generation, reason="snapshot_hash_mismatch", expected_hash=expected, actual_hash=actual)
        raise RestoreRejected("snapshot changed; generation stalled")
    try:
        return decode_snapshot(held, key=key)
    except EnvelopeError as exc:
        ledger.stall(generation, reason="snapshot_authentication_failed", expected_hash=expected, actual_hash=actual)
        raise RestoreRejected("snapshot authentication failed; generation stalled") from exc
