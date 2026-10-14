"""Store-and-Forward Local Buffer for Zone A Edge Collector.

Ensures zero data loss during network interruptions, VPN drops, or Zone B
server maintenance by persisting telemetry in a lightweight local SQLite database.
When connectivity is restored, buffered telemetry is replayed in strict
chronological order with original source timestamps intact.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CollectorBuffer:
    """Persistent FIFO buffer for edge telemetry store-and-forward."""

    def __init__(self, db_path: str = "data/collector_buffer.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
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
            conn.commit()

    def enqueue(self, packet: dict[str, Any]) -> int:
        """Stores a telemetry packet into the local buffer."""
        packet_json = json.dumps(packet)
        src_ts = packet.get("sourceTimestamp") or packet.get("source_timestamp") or datetime.now(timezone.utc).isoformat()
        seq = packet.get("sequenceNumber") or packet.get("sequence_number") or 0
        now_str = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
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
        with sqlite3.connect(self.db_path) as conn:
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
        """Removes or marks successfully transmitted packets."""
        if not packet_ids:
            return 0
        with sqlite3.connect(self.db_path) as conn:
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
        with sqlite3.connect(self.db_path) as conn:
            placeholders = ",".join("?" * len(packet_ids))
            conn.execute(
                f"UPDATE telemetry_buffer SET attempts = attempts + 1 WHERE id IN ({placeholders})",
                packet_ids
            )
            conn.commit()

    def pending_count(self) -> int:
        """Returns the number of buffered packets awaiting transmission."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM telemetry_buffer WHERE status = 'PENDING'")
            return cursor.fetchone()[0]

    def clear(self) -> None:
        """Empties the buffer (for testing purposes)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM telemetry_buffer")
            conn.commit()
