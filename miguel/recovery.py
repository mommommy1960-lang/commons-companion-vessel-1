"""Fail-closed recovery from the durable snapshot named by an approval."""
from __future__ import annotations
import hashlib
from pathlib import Path
from .attention import AttentionLedger
from .persistence import EnvelopeError, decode_snapshot
from .restore_ledger import RestoreLedger, RestoreRejected

def _stall(ledger, attention, generation, reason, expected, actual, worker, observer_key):
    ledger.stall(generation, reason=reason, expected_hash=expected, actual_hash=actual)
    if attention is not None:
        attention.require(generation=generation, reason=reason, expected_hash=expected,
                          actual_hash=actual, observer_worker=worker,
                          observer_key_id=observer_key)

def recover_verified(ledger: RestoreLedger, generation: str, *, key: bytes,
                     attention: AttentionLedger | None = None,
                     observer_worker: str = "unknown",
                     observer_key_id: str = "unknown"):
    job = ledger.job(generation)
    if job is None:
        raise RestoreRejected("unknown restore generation")
    path, expected, _destination, _head, _epoch, _parent, stage = job
    if stage not in ("APPROVED", "CONSTRUCTING"):
        raise RestoreRejected("generation is not recoverable")
    try:
        held = Path(path).read_bytes()
    except FileNotFoundError:
        _stall(ledger, attention, generation, "snapshot_missing", expected, None, observer_worker, observer_key_id)
        raise RestoreRejected("snapshot missing; generation stalled")
    actual = hashlib.sha256(held).hexdigest()
    if actual != expected:
        _stall(ledger, attention, generation, "snapshot_hash_mismatch", expected, actual, observer_worker, observer_key_id)
        raise RestoreRejected("snapshot changed; generation stalled")
    try:
        return decode_snapshot(held, key=key)
    except EnvelopeError as exc:
        _stall(ledger, attention, generation, "snapshot_authentication_failed", expected, actual, observer_worker, observer_key_id)
        raise RestoreRejected("snapshot authentication failed; generation stalled") from exc
