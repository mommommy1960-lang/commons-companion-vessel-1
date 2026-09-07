"""SQLite-backed atomic restore approval ledger for simulation."""
from __future__ import annotations
import sqlite3
from contextlib import closing
from pathlib import Path

class RestoreRejected(PermissionError):
    pass

class RestoreLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS control (singleton INTEGER PRIMARY KEY CHECK(singleton=1), trusted_head TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS spent (nonce TEXT PRIMARY KEY, snapshot_hash TEXT NOT NULL, destination TEXT NOT NULL, source_head TEXT NOT NULL, key_epoch INTEGER NOT NULL, attempt INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS restore_audit (nonce TEXT PRIMARY KEY, decision TEXT NOT NULL);
            """)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5.0, isolation_level=None)

    def set_trusted_head(self, head: str) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO control VALUES(1, ?) ON CONFLICT(singleton) DO UPDATE SET trusted_head=excluded.trusted_head", (head,))
            db.commit()

    def consume(self, *, nonce: str, snapshot_hash: str, destination: str, source_head: str, key_epoch: int, attempt: int, decision: str) -> None:
        """Compare head, spend nonce, and write audit as one transaction."""
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT trusted_head FROM control WHERE singleton=1").fetchone()
                if row is None or row[0] != source_head:
                    raise RestoreRejected("trusted head mismatch")
                db.execute("INSERT INTO spent VALUES(?, ?, ?, ?, ?, ?)", (nonce, snapshot_hash, destination, source_head, key_epoch, attempt))
                db.execute("INSERT INTO restore_audit VALUES(?, ?)", (nonce, decision))
                db.commit()
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise RestoreRejected("restore approval already spent") from exc
            except BaseException:
                db.rollback()
                raise
