"""Docker health check script for PWA Water Alert System."""

import sys
import sqlite3
from pathlib import Path
import urllib.request

DATA_DIR = Path("/app/data")
DB_PATH = DATA_DIR / "pwa_alerts.db"

def check_db() -> bool:
    """Verifies SQLite database is readable."""
    if not DB_PATH.exists():
        # Database might not be initialized on very first seconds
        return True
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        cursor.fetchone()
        conn.close()
        return True
    except Exception as e:
        print(f"Healthcheck DB failure: {e}", file=sys.stderr)
        return False

def check_network() -> bool:
    """Verifies internet connectivity to Telegram API."""
    try:
        req = urllib.request.Request("https://api.telegram.org", headers={"User-Agent": "Healthcheck"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 302, 404)
    except Exception:
        # Fallback to check PWA website
        try:
            req = urllib.request.Request("https://www.pwa.co.th", headers={"User-Agent": "Healthcheck"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 301, 302)
        except Exception as e:
            print(f"Healthcheck Network failure: {e}", file=sys.stderr)
            return False

def main() -> None:
    if not check_db():
        sys.exit(1)
    if not check_network():
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
