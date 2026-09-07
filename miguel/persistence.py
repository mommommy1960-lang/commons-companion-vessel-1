"""Authenticated, strict TLV persistence for Miguel continuity snapshots.

This module provides a single-file atomic replacement layer. It does not claim
that filesystem atomicity creates an application-level snapshot boundary.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import struct
import tempfile
from pathlib import Path
from typing import Any

MAGIC = b"CSP1"
MAC_SIZE = 32
FIELDS = (
    ("schema", 1), ("snapshot_id", 2), ("sequence", 3),
    ("source_audit_head", 4), ("key_id", 5), ("key_epoch", 6),
    ("memories", 7),
)
TAGS = {name: tag for name, tag in FIELDS}
NAMES = {tag: name for name, tag in FIELDS}
MEMORY_FIELDS = (("memory_id", 1), ("content", 2), ("provenance", 3), ("corrected", 4))


class EnvelopeError(ValueError):
    pass


def _field(tag: int, value: bytes) -> bytes:
    return struct.pack(">BI", tag, len(value)) + value


def _parse_fields(data: bytes, allowed: dict[int, str]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    offset = 0
    last_tag = 0
    while offset < len(data):
        if len(data) - offset < 5:
            raise EnvelopeError("truncated TLV header")
        tag, size = struct.unpack(">BI", data[offset:offset + 5])
        offset += 5
        if tag not in allowed:
            raise EnvelopeError("unknown TLV tag")
        if tag <= last_tag:
            raise EnvelopeError("duplicate or noncanonical TLV tag")
        last_tag = tag
        if size > len(data) - offset:
            raise EnvelopeError("truncated TLV value")
        result[allowed[tag]] = data[offset:offset + size]
        offset += size
    return result


def _memory_bytes(raw: dict[str, Any]) -> bytes:
    values = {
        "memory_id": str(raw["memory_id"]).encode(),
        "content": str(raw["content"]).encode(),
        "corrected": b"\x01" if bool(raw.get("corrected", False)) else b"\x00",
    }
    if "provenance" in raw:
        values["provenance"] = str(raw["provenance"]).encode()
    return b"".join(_field(tag, values[key]) for key, tag in MEMORY_FIELDS if key in values)


def encode_snapshot(snapshot: dict[str, Any], *, key: bytes, snapshot_id: str, sequence: int) -> bytes:
    if not key:
        raise EnvelopeError("authentication key required")
    if snapshot.get("schema") != "miguel-memory-v3":
        raise EnvelopeError("unexpected snapshot schema")
    records = snapshot.get("memories")
    if not isinstance(records, list):
        raise EnvelopeError("memories must be a list")
    memory_blob = b"".join(_field(1, _memory_bytes(record)) for record in records)
    values = {
        "schema": snapshot["schema"].encode(),
        "snapshot_id": snapshot_id.encode(),
        "sequence": struct.pack(">Q", sequence),
        "source_audit_head": snapshot["source_audit_head"].encode(),
        "key_id": snapshot["key_id"].encode(),
        "key_epoch": struct.pack(">Q", snapshot["key_epoch"]),
        "memories": memory_blob,
    }
    payload = b"".join(_field(tag, values[name]) for name, tag in FIELDS)
    header = MAGIC + struct.pack(">Q", len(payload))
    return header + payload + hmac.new(key, header + payload, hashlib.sha256).digest()


def decode_snapshot(blob: bytes, *, key: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(blob) < 12 + MAC_SIZE or blob[:4] != MAGIC:
        raise EnvelopeError("invalid or truncated envelope")
    size = struct.unpack(">Q", blob[4:12])[0]
    expected = 12 + size + MAC_SIZE
    if len(blob) != expected:
        raise EnvelopeError("physical byte count differs from authenticated length")
    signed, supplied = blob[:-MAC_SIZE], blob[-MAC_SIZE:]
    if not hmac.compare_digest(hmac.new(key, signed, hashlib.sha256).digest(), supplied):
        raise EnvelopeError("envelope authentication failed")
    parsed = _parse_fields(blob[12:12 + size], NAMES)
    if set(parsed) != set(TAGS):
        raise EnvelopeError("missing required envelope field")
    if parsed["schema"].decode() != "miguel-memory-v3":
        raise EnvelopeError("unsupported schema")
    records = []
    memory_data = parsed["memories"]
    offset = 0
    ids: set[str] = set()
    mem_names = {tag: name for name, tag in MEMORY_FIELDS}
    while offset < len(memory_data):
        if len(memory_data) - offset < 5:
            raise EnvelopeError("truncated memory frame")
        tag, length = struct.unpack(">BI", memory_data[offset:offset + 5])
        offset += 5
        if tag != 1 or length > len(memory_data) - offset:
            raise EnvelopeError("invalid memory frame")
        item = _parse_fields(memory_data[offset:offset + length], mem_names)
        offset += length
        if not {"memory_id", "content", "corrected"}.issubset(item):
            raise EnvelopeError("missing memory field")
        memory_id = item["memory_id"].decode()
        if not memory_id or memory_id in ids:
            raise EnvelopeError("duplicate or missing memory identifier")
        ids.add(memory_id)
        record = {"memory_id": memory_id, "content": item["content"].decode(),
                  "corrected": item["corrected"] == b"\x01"}
        if "provenance" in item:
            record["provenance"] = item["provenance"].decode()
        records.append(record)
    snapshot = {
        "schema": parsed["schema"].decode(),
        "source_audit_head": parsed["source_audit_head"].decode(),
        "key_id": parsed["key_id"].decode(),
        "key_epoch": struct.unpack(">Q", parsed["key_epoch"])[0],
        "memories": records,
    }
    metadata = {"snapshot_id": parsed["snapshot_id"].decode(),
                "sequence": struct.unpack(">Q", parsed["sequence"])[0]}
    return snapshot, metadata


def atomic_write(path: str | Path, blob: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_verified(path: str | Path, *, key: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    with open(path, "rb") as stream:
        held_image = stream.read()
    return decode_snapshot(held_image, key=key)
