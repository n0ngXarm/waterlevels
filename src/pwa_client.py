"""PWA (การประปาส่วนภูมิภาค) API Client & RTU Quality Scraper."""

import json
import logging
import re
import ssl
from pathlib import Path
from typing import Any, Optional
import urllib.request
import urllib.error
from src.config import Config

logger = logging.getLogger(__name__)


class PWAClient:
    """Client for interacting with PWA services and sensor feeds."""

    OUTAGE_API_URL = "https://api-mg.pwa.co.th:8065/news/api/listPublish"
    RTU_MAP_URL = "https://dmamas.pwa.co.th/rtumonitor/maps_water_qlt.php"
    CALL1662_URL = "https://www.pwa.co.th/news/call1662"

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Config.DATA_DIR
        self.branches_cache: list[dict[str, str]] = []
        self._load_branches()

    def _load_branches(self) -> None:
        """Loads branch list from local JSON file or initializes empty."""
        branches_file = self.data_dir / "branches.json"
        if branches_file.exists():
            try:
                with open(branches_file, "r", encoding="utf-8") as f:
                    self.branches_cache = json.load(f)
            except Exception as e:
                logger.warning("Could not read branches.json: %s", e)

    # ---------------- Water Outages (หยุดจ่ายน้ำ) ----------------

    def fetch_outages(self, branch_code: str = "1001", page: int = 1, limit: int = 50) -> list[dict[str, Any]]:
        """
        Fetches water outage announcements from PWA API.
        branch_code='1001' means ALL branches.
        """
        payload = {
            "ba": [str(branch_code)],
            "page": page,
            "limit": limit
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.pwa.co.th/news/call1662"
        }

        req = urllib.request.Request(
            self.OUTAGE_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("data", [])
                logger.info("Fetched %d outages from PWA API (ba=%s)", len(items), branch_code)
                return items
        except Exception as e:
            logger.error("Failed to fetch outages from PWA API: %s", e)
            return []

    def get_all_active_outages(self, limit: int = 100) -> list[dict[str, Any]]:
        """Fetches all currently active water outage notices nationwide."""
        return self.fetch_outages(branch_code="1001", page=1, limit=limit)

    # ---------------- Branch Resolution ----------------

    def get_branches(self) -> list[dict[str, str]]:
        """Returns list of all PWA branches."""
        if not self.branches_cache:
            self._load_branches()
        return self.branches_cache

    def find_branch(self, query: str) -> Optional[dict[str, str]]:
        """
        Finds a branch by name or code.
        Examples: 'ชลบุรี', 'เชียงใหม่', '1004'
        """
        query_clean = query.strip().lower()
        branches = self.get_branches()

        # Exact code match
        for b in branches:
            if b.get("code") == query_clean:
                return b

        # Exact name match
        for b in branches:
            name = b.get("name", "").lower()
            if query_clean in name:
                return b

        return None

    # ---------------- RTU Real-Time Water Quality (ตรวจวัดคุณภาพน้ำ) ----------------

    def fetch_rtu_water_quality(self) -> dict[str, dict[str, Any]]:
        """
        Fetches real-time sensor measurements for water production stations nationwide.
        Returns dict keyed by station ID.
        """
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(self.RTU_MAP_URL, headers=headers)

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            idx = html.find("var pointlist =")
            if idx == -1:
                logger.error("Could not find 'var pointlist =' in RTU page")
                return {}

            sub = html[idx + len("var pointlist ="):].strip()
            data, _ = json.JSONDecoder().raw_decode(sub)
            logger.info("Successfully fetched %d RTU water quality stations", len(data))
            return data
        except Exception as e:
            logger.error("Failed to fetch RTU water quality data: %s", e)
            return {}

    def check_station_quality(self, station: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Checks if a station's water quality measurements meet PWA standards.
        Returns: (is_pass: bool, issues: list[str])
        """
        issues: list[str] = []

        # If station explicitly marked fail
        pic_status = station.get("pic", "").strip().lower()
        if pic_status == "fail":
            issues.append("สถานะการตรวจวัด: ไม่ผ่านเกณฑ์มาตรฐาน กปภ.")

        # Check pH (Standard: 6.5 - 8.5)
        raw_ph = station.get("pH", "")
        try:
            if raw_ph and raw_ph != "-":
                ph_val = float(raw_ph)
                if ph_val < Config.PH_MIN:
                    issues.append(f"ค่า pH ({ph_val:.2f}) ต่ำกว่าเกณฑ์ขั้นต่ำ {Config.PH_MIN} (มีความเป็นกรด)")
                elif ph_val > Config.PH_MAX:
                    issues.append(f"ค่า pH ({ph_val:.2f}) สูงกว่าเกณฑ์สูงสุด {Config.PH_MAX} (มีความเป็นด่าง)")
        except (ValueError, TypeError):
            pass

        # Check NTU Turbidity (Standard: <= 5.0 NTU)
        raw_ntu = station.get("NTU", "")
        try:
            if raw_ntu and raw_ntu != "-":
                ntu_val = float(raw_ntu)
                if ntu_val > Config.NTU_MAX:
                    issues.append(f"ค่าความขุ่น ({ntu_val:.2f} NTU) เกินเกณฑ์สูงสุด {Config.NTU_MAX} NTU")
        except (ValueError, TypeError):
            pass

        # Check Residual Chlorine (Standard: 0.2 - 2.0 mg/L)
        raw_cl = station.get("Cl", "")
        try:
            if raw_cl and raw_cl != "-":
                cl_val = float(raw_cl)
                if cl_val < Config.CL_MIN:
                    issues.append(f"คลอรีนคงเหลือ ({cl_val:.2f} mg/L) ต่ำกว่าเกณฑ์ขั้นต่ำ {Config.CL_MIN} mg/L")
                elif cl_val > Config.CL_MAX:
                    issues.append(f"คลอรีนคงเหลือ ({cl_val:.2f} mg/L) สูงกว่าเกณฑ์สูงสุด {Config.CL_MAX} mg/L")
        except (ValueError, TypeError):
            pass

        is_normal = len(issues) == 0
        return is_normal, issues
