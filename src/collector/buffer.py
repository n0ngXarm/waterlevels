"""Store-and-Forward Local Buffer for Zone A Edge Collector.

Ensures zero data loss during network interruptions, VPN drops, or Zone B
server maintenance by persisting telemetry in a lightweight local SQLite database.

Features:
- Strict FIFO chronological ordering with original timestamps.
- Monotonic sequence numbering and collector epoch persistence across restarts.
- Strict bounded disk footprint (Max 5,000 records / 5 MB limit, ring buffer overwrite).
- Retention enforcement (auto-purging records older than 72 hours).
"""

from datetime import datetime, timezone, timedelta
import contextlib
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Optional
import uuid

logger = logging.getLogger(__name__)


class CollectorBuffer:
    """Persistent bounded FIFO buffer for edge telemetry store-and-forward."""

    DEFAULT_MAX_RECORDS = 5000
    DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB safety ceiling for low-disk environments
    DEFAULT_RETENTION_HOURS = 72

    def __init__(
        self,
        db_path: str = "data/collector_buffer.db",
        max_records: int = DEFAULT_MAX_RECORDS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        retention_hours: int = DEFAULT_RETENTION_HOURS
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.retention_hours = retention_hours
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_buffer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_json TEXT NOT NULL,
                    source_timestamp TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'PENDING'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_buf_status ON telemetry_buffer(status, id)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS buffer_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        """Retrieves persistent metadata value."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM buffer_meta WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def set_meta(self, key: str, value: str) -> None:
        """Saves persistent metadata value."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO buffer_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value))
            )
            conn.commit()

    def get_epoch(self) -> str:
        """Returns or initializes persistent collector epoch ID."""
        epoch = self.get_meta("collector_epoch")
        if not epoch:
            epoch = f"EP-{uuid.uuid4().hex[:8].upper()}"
            self.set_meta("collector_epoch", epoch)
        return epoch

    def get_last_sequence_number(self) -> int:
        """Returns the last sequence number without incrementing."""
        val = self.get_meta("sequence_number", "0")
        try:
            return int(val)
        except ValueError:
            return 0

    def get_next_sequence_number(self) -> int:
        """Atomically increments and returns the next sequence number."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM buffer_meta WHERE key = 'sequence_number'")
            row = cur.fetchone()
            current = int(row[0]) if row and row[0].isdigit() else 0
            nxt = current + 1
            conn.execute(
                "INSERT INTO buffer_meta (key, value) VALUES ('sequence_number', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(nxt),)
            )
            conn.commit()
            return nxt

    def _enforce_limits(self, conn: sqlite3.Connection) -> None:
        """Prunes expired records and enforces max records / max file size constraints."""
        # 1. Prune records older than retention period
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)).isoformat()
        conn.execute("DELETE FROM telemetry_buffer WHERE created_at < ?", (cutoff,))

        # 2. Enforce max records limit (FIFO Ring Buffer: drop oldest pending)
        cur = conn.execute("SELECT COUNT(*) FROM telemetry_buffer WHERE status = 'PENDING'")
        count = cur.fetchone()[0]
        if count >= self.max_records:
            excess = count - self.max_records + 1
            logger.warning("Buffer reached maximum limit (%d >= %d). Dropping %d oldest records.", count, self.max_records, excess)
            conn.execute(
                "DELETE FROM telemetry_buffer WHERE id IN (SELECT id FROM telemetry_buffer WHERE status = 'PENDING' ORDER BY id ASC LIMIT ?)",
                (excess,)
            )

        # 3. Enforce file size limit if database exceeds max_bytes
        try:
            if self.db_path.exists() and self.db_path.stat().st_size > self.max_bytes:
                logger.warning("Buffer DB file size (%d bytes) exceeds ceiling (%d bytes). Purging oldest 15%% pending records.",
                               self.db_path.stat().st_size, self.max_bytes)
                drop_count = max(10, int(self.max_records * 0.15))
                conn.execute(
                    "DELETE FROM telemetry_buffer WHERE id IN (SELECT id FROM telemetry_buffer WHERE status = 'PENDING' ORDER BY id ASC LIMIT ?)",
                    (drop_count,)
                )
        except OSError:
            pass

    def enqueue(self, packet: dict[str, Any]) -> int:
        """Stores a telemetry packet into the local buffer with limit enforcements."""
        packet_json = json.dumps(packet)
        src_ts = packet.get("sourceTimestamp") or packet.get("source_timestamp") or datetime.now(timezone.utc).isoformat()
        seq = packet.get("sequenceNumber") or packet.get("sequence_number") or 0
        now_str = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            self._enforce_limits(conn)
            cursor = conn.execute(
                """
                INSERT INTO telemetry_buffer (packet_json, source_timestamp, sequence_number, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (packet_json, src_ts, seq, now_str)
            )
            conn.commit()
            return cursor.lastrowid

    def dequeue_batch(self, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieves oldest pending packets in strict chronological FIFO order."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, packet_json, attempts, source_timestamp
                FROM telemetry_buffer
                WHERE status = 'PENDING'
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

            results = []
            for r in rows:
                pkt = json.loads(r["packet_json"])
                results.append({
                    "id": r["id"],
                    "packet": pkt,
                    "attempts": r["attempts"],
                    "source_timestamp": r["source_timestamp"]
                })
            return results

    def mark_sent(self, packet_ids: list[int]) -> int:
        """Removes successfully transmitted packets."""
        if not packet_ids:
            return 0
        with self._get_connection() as conn:
            placeholders = ",".join("?" * len(packet_ids))
            cursor = conn.execute(
                f"DELETE FROM telemetry_buffer WHERE id IN ({placeholders})",
                packet_ids
            )
            conn.commit()
            return cursor.rowcount

    def increment_attempts(self, packet_ids: list[int]) -> None:
        """Increments transmission attempt count for failed packets."""
        if not packet_ids:
            return
        with self._get_connection() as conn:
            placeholders = ",".join("?" * len(packet_ids))
            conn.execute(
                f"UPDATE telemetry_buffer SET attempts = attempts + 1 WHERE id IN ({placeholders})",
                packet_ids
            )
            conn.commit()

    def pending_count(self) -> int:
        """Returns the number of buffered packets awaiting transmission."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM telemetry_buffer WHERE status = 'PENDING'")
            return cursor.fetchone()[0]

    def clear(self) -> None:
        """Empties the buffer (for testing purposes)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM telemetry_buffer")
            conn.execute("DELETE FROM buffer_meta")
            conn.commit()
