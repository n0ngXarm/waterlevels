"""Database operations for PWA Water Notification System using SQLite."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from src.config import Config


class Database:
    """SQLite database manager for tracking alerts and subscribers."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Returns SQLite connection with dict-like row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initializes database schema and tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Table for water outage / interruption notices
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS outage_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_key TEXT UNIQUE,
                    branch_name TEXT,
                    title TEXT,
                    cause TEXT,
                    affected_area TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    extend_end_date TEXT,
                    working_status_name TEXT,
                    publish_date TEXT,
                    link TEXT,
                    thumbnail TEXT,
                    contact TEXT,
                    comment TEXT,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_status_alerted TEXT,
                    last_alert_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table for RTU water quality alerts
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quality_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT,
                    plantname TEXT,
                    divisionname TEXT,
                    ph REAL,
                    ntu REAL,
                    cl REAL,
                    status TEXT,
                    issues TEXT,
                    alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table for Telegram subscribers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id TEXT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    branches TEXT DEFAULT '["*"]',
                    alert_types TEXT DEFAULT '["outage"]',
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # System event log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    # ---------------- Outage Operations ----------------

    @staticmethod
    def generate_alert_key(outage: dict[str, Any]) -> str:
        """Generates unique key for an outage item based on link and branch."""
        link = outage.get("link", "").strip()
        if link:
            return link
        # Fallback to combination of branch and title and start_date
        return f"{outage.get('branch_name', '')}_{outage.get('title', '')}_{outage.get('start_date', '')}"

    def get_outage(self, alert_key: str) -> Optional[dict[str, Any]]:
        """Retrieves an outage record by alert key."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM outage_alerts WHERE alert_key = ?", (alert_key,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_outage(self, outage: dict[str, Any], initial_status: str) -> bool:
        """Saves a new outage record. Returns True if inserted."""
        alert_key = self.generate_alert_key(outage)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO outage_alerts (
                        alert_key, branch_name, title, cause, affected_area,
                        start_date, end_date, extend_end_date, working_status_name,
                        publish_date, link, thumbnail, contact, comment,
                        last_status_alerted, last_alert_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    alert_key,
                    outage.get("branch_name", ""),
                    outage.get("title", ""),
                    outage.get("cause", ""),
                    outage.get("affected_area", ""),
                    outage.get("start_date", ""),
                    outage.get("end_date", ""),
                    outage.get("extend_end_date", ""),
                    outage.get("working_status_name", ""),
                    outage.get("publish_date", ""),
                    outage.get("link", ""),
                    outage.get("thumbnail", ""),
                    outage.get("contact", ""),
                    outage.get("comment", ""),
                    initial_status,
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def update_outage_status(self, alert_key: str, new_status: str) -> None:
        """Updates the status and last alerted status of an outage."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE outage_alerts
                SET working_status_name = ?,
                    last_status_alerted = ?,
                    last_alert_at = CURRENT_TIMESTAMP
                WHERE alert_key = ?
            """, (new_status, new_status, alert_key))
            conn.commit()

    def get_recent_outages(self, limit: int = 5, branch_name: Optional[str] = None) -> list[dict[str, Any]]:
        """Gets recent outages from database, optionally filtered by branch."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if branch_name:
                cursor.execute("""
                    SELECT * FROM outage_alerts
                    WHERE branch_name LIKE ?
                    ORDER BY id DESC LIMIT ?
                """, (f"%{branch_name}%", limit))
            else:
                cursor.execute("""
                    SELECT * FROM outage_alerts
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # ---------------- Quality Operations ----------------

    def is_quality_alert_in_cooldown(self, station_id: str, cooldown_hours: int = 6) -> bool:
        """Checks if a quality alert for this station was sent within cooldown period."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT alerted_at FROM quality_alerts
                WHERE station_id = ?
                ORDER BY alerted_at DESC LIMIT 1
            """, (station_id,))
            row = cursor.fetchone()
            if not row:
                return False

            try:
                alerted_time = datetime.fromisoformat(row["alerted_at"])
                return datetime.utcnow() - alerted_time < timedelta(hours=cooldown_hours)
            except Exception:
                return False

    def save_quality_alert(
        self,
        station_id: str,
        plantname: str,
        divisionname: str,
        ph: Optional[float],
        ntu: Optional[float],
        cl: Optional[float],
        status: str,
        issues: list[str]
    ) -> None:
        """Records a water quality alert."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO quality_alerts (
                    station_id, plantname, divisionname, ph, ntu, cl, status, issues, alerted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                station_id,
                plantname,
                divisionname,
                ph,
                ntu,
                cl,
                status,
                json.dumps(issues, ensure_ascii=False)
            ))
            conn.commit()

    # ---------------- Subscriber Operations ----------------

    def add_or_update_subscriber(
        self,
        chat_id: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        branches: Optional[list[str]] = None,
        alert_types: Optional[list[str]] = None
    ) -> None:
        """Adds or updates a Telegram subscriber."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscribers WHERE chat_id = ?", (str(chat_id),))
            existing = cursor.fetchone()

            branches_json = json.dumps(branches if branches is not None else ["*"], ensure_ascii=False)
            types_json = json.dumps(alert_types if alert_types is not None else ["outage"], ensure_ascii=False)

            if existing:
                cursor.execute("""
                    UPDATE subscribers
                    SET username = COALESCE(?, username),
                        first_name = COALESCE(?, first_name),
                        branches = COALESCE(?, branches),
                        alert_types = COALESCE(?, alert_types),
                        is_active = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                """, (username, first_name, branches_json if branches is not None else None,
                      types_json if alert_types is not None else None, str(chat_id)))
            else:
                cursor.execute("""
                    INSERT INTO subscribers (chat_id, username, first_name, branches, alert_types, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (str(chat_id), username, first_name, branches_json, types_json))
            conn.commit()

    def set_subscriber_active(self, chat_id: str, active: bool) -> None:
        """Activates or deactivates a subscriber."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE subscribers
                SET is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (1 if active else 0, str(chat_id)))
            conn.commit()

    def get_subscriber(self, chat_id: str) -> Optional[dict[str, Any]]:
        """Gets subscriber information."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscribers WHERE chat_id = ?", (str(chat_id),))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            data["branches"] = json.loads(data["branches"]) if data["branches"] else ["*"]
            data["alert_types"] = json.loads(data["alert_types"]) if data["alert_types"] else ["outage"]
            return data

    def get_active_subscribers(self) -> list[dict[str, Any]]:
        """Returns all active subscribers with parsed JSON fields."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscribers WHERE is_active = 1")
            results = []
            for row in cursor.fetchall():
                data = dict(row)
                data["branches"] = json.loads(data["branches"]) if data["branches"] else ["*"]
                data["alert_types"] = json.loads(data["alert_types"]) if data["alert_types"] else ["outage"]
                results.append(data)
            return results

    def count_subscribers(self) -> int:
        """Counts active subscribers."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM subscribers WHERE is_active = 1")
            return cursor.fetchone()[0]

    def count_outages(self) -> int:
        """Counts total tracked outages."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM outage_alerts")
            return cursor.fetchone()[0]

    # ---------------- System Logs ----------------

    def log_event(self, event_type: str, message: str) -> None:
        """Logs a system event."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO system_logs (event_type, message) VALUES (?, ?)", (event_type, message))
            conn.commit()
