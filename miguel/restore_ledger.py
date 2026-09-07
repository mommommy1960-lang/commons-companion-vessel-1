"""SQLite-backed atomic restore lifecycle ledger for simulation."""
from __future__ import annotations
import sqlite3
from contextlib import closing
from pathlib import Path

class RestoreRejected(PermissionError):
    pass

class RestoreLedger:
    STAGES = ("APPROVED", "CONSTRUCTING", "READY", "PUBLISHED", "STALLED")

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS control (singleton INTEGER PRIMARY KEY CHECK(singleton=1), trusted_head TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS spent (nonce TEXT PRIMARY KEY, snapshot_hash TEXT NOT NULL, destination TEXT NOT NULL, source_head TEXT NOT NULL, key_epoch INTEGER NOT NULL, attempt INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS restore_audit (nonce TEXT PRIMARY KEY, decision TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS restore_jobs (generation TEXT PRIMARY KEY, nonce TEXT UNIQUE NOT NULL, snapshot_path TEXT NOT NULL, snapshot_hash TEXT NOT NULL, destination TEXT NOT NULL, source_head TEXT NOT NULL, key_epoch INTEGER NOT NULL, parent_generation TEXT, stage TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS publication (singleton INTEGER PRIMARY KEY CHECK(singleton=1), visible_generation TEXT);\n            CREATE TABLE IF NOT EXISTS restore_failures (generation TEXT PRIMARY KEY, reason TEXT NOT NULL, expected_hash TEXT NOT NULL, actual_hash TEXT);
            INSERT OR IGNORE INTO publication(singleton, visible_generation) VALUES(1, NULL);
            """)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5.0, isolation_level=None)

    def set_trusted_head(self, head: str) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO control VALUES(1, ?) ON CONFLICT(singleton) DO UPDATE SET trusted_head=excluded.trusted_head", (head,))
            db.commit()

    def consume(self, *, nonce: str, snapshot_hash: str, destination: str, source_head: str, key_epoch: int, attempt: int, decision: str) -> None:
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
                db.rollback(); raise

    def approve(self, *, generation: str, nonce: str, snapshot_path: str, snapshot_hash: str, destination: str, source_head: str, key_epoch: int, attempt: int, decision: str, parent_generation: str | None = None) -> None:
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT trusted_head FROM control WHERE singleton=1").fetchone()
                if row is None or row[0] != source_head:
                    raise RestoreRejected("trusted head mismatch")
                db.execute("INSERT INTO spent VALUES(?, ?, ?, ?, ?, ?)", (nonce, snapshot_hash, destination, source_head, key_epoch, attempt))
                db.execute("INSERT INTO restore_audit VALUES(?, ?)", (nonce, decision))
                db.execute("INSERT INTO restore_jobs VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)", (generation, nonce, snapshot_path, snapshot_hash, destination, source_head, key_epoch, parent_generation, "APPROVED"))
                db.commit()
            except sqlite3.IntegrityError as exc:
                db.rollback(); raise RestoreRejected("generation or approval already used") from exc
            except BaseException:
                db.rollback(); raise

    def advance(self, generation: str, expected: str, target: str) -> None:
        allowed = {("APPROVED", "CONSTRUCTING"), ("CONSTRUCTING", "READY")}
        if (expected, target) not in allowed:
            raise RestoreRejected("illegal restore transition")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE restore_jobs SET stage=? WHERE generation=? AND stage=?", (target, generation, expected)).rowcount
            if changed != 1:
                db.rollback(); raise RestoreRejected("restore stage conflict")
            db.commit()

    def publish(self, generation: str) -> bool:
        """Idempotently publish one READY generation; return True only on first flip."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT stage, parent_generation FROM restore_jobs WHERE generation=?", (generation,)).fetchone()
            visible = db.execute("SELECT visible_generation FROM publication WHERE singleton=1").fetchone()[0]
            if visible == generation:
                db.execute("UPDATE restore_jobs SET stage='PUBLISHED' WHERE generation=?", (generation,))
                db.commit(); return False
            if job is None or job[0] != "READY" or visible != job[1]:
                db.rollback(); raise RestoreRejected("publication requires reconciliation")
            db.execute("UPDATE publication SET visible_generation=? WHERE singleton=1", (generation,))
            db.execute("UPDATE restore_jobs SET stage='PUBLISHED' WHERE generation=?", (generation,))
            db.commit(); return True


    def stall(self, generation: str, *, reason: str, expected_hash: str, actual_hash: str | None) -> None:
        """Record durable evidence and stop automatic recovery."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT stage, snapshot_hash FROM restore_jobs WHERE generation=?", (generation,)).fetchone()
            if job is None or job[0] in ("PUBLISHED", "STALLED"):
                db.rollback()
                raise RestoreRejected("generation cannot be stalled")
            if job[1] != expected_hash:
                db.rollback()
                raise RestoreRejected("expected hash does not match approval")
            db.execute("INSERT INTO restore_failures VALUES(?, ?, ?, ?)", (generation, reason, expected_hash, actual_hash))
            db.execute("UPDATE restore_jobs SET stage='STALLED' WHERE generation=?", (generation,))
            db.commit()

    def failure(self, generation: str):
        with self._connect() as db:
            return db.execute("SELECT reason, expected_hash, actual_hash FROM restore_failures WHERE generation=?", (generation,)).fetchone()

    def job(self, generation: str):
        with self._connect() as db:
            return db.execute("SELECT snapshot_path, snapshot_hash, destination, source_head, key_epoch, parent_generation, stage FROM restore_jobs WHERE generation=?", (generation,)).fetchone()
