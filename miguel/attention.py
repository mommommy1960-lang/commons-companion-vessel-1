"""Durable attention queue with no authorization capability."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

class AttentionError(ValueError):
    pass

class AttentionLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS requests (generation TEXT PRIMARY KEY, reason TEXT NOT NULL, expected_hash TEXT NOT NULL, actual_hash TEXT, observer_worker TEXT NOT NULL, observer_key_id TEXT NOT NULL, first_observed TEXT NOT NULL, last_surfaced TEXT, surface_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, acknowledged_by TEXT);
            """)

    def require(self, *, generation: str, reason: str, expected_hash: str, actual_hash: str | None, observer_worker: str, observer_key_id: str, observed_at: str | None = None) -> None:
        observed_at = observed_at or datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO requests(generation, reason, expected_hash, actual_hash, observer_worker, observer_key_id, first_observed, status) VALUES(?, ?, ?, ?, ?, ?, ?, 'OPEN')", (generation, reason, expected_hash, actual_hash, observer_worker, observer_key_id, observed_at))

    def pending(self):
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT generation, reason, expected_hash, actual_hash, observer_worker, observer_key_id, first_observed, last_surfaced, surface_count FROM requests WHERE status='OPEN' ORDER BY first_observed").fetchall()

    def mark_surfaced(self, generation: str, surfaced_at: str | None = None) -> None:
        surfaced_at = surfaced_at or datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as db:
            changed = db.execute("UPDATE requests SET last_surfaced=?, surface_count=surface_count+1 WHERE generation=? AND status='OPEN'", (surfaced_at, generation)).rowcount
            if changed != 1:
                raise AttentionError("no open attention request")

    def acknowledge(self, generation: str, acknowledged_by: str) -> None:
        if not acknowledged_by.strip():
            raise AttentionError("human identity required")
        with sqlite3.connect(self.path) as db:
            changed = db.execute("UPDATE requests SET status='ACKNOWLEDGED', acknowledged_by=? WHERE generation=? AND status='OPEN'", (acknowledged_by, generation)).rowcount
            if changed != 1:
                raise AttentionError("no open attention request")
