"""Bridge connecting live PWA feeds to Aqua Command Center Web Dashboard."""

import json
import logging
import os
from typing import Any, Optional
import urllib.request
import urllib.error
from src.config import Config

logger = logging.getLogger(__name__)

# Mapping from PWA station and branch keywords to Aqua Command Chiang Mai station IDs
STATION_MAP = {
    "ป่าตัน": "CM-01",
    "เชียงใหม่": "CM-01",
    "อุโมงค์": "CM-02",
    "สุเทพ": "CM-02",
    "แม่กวง": "CM-03",
    "สันทราย": "CM-03",
    "แม่แฝก": "CM-04",
    "แม่ริม": "CM-05",
    "สันกำแพง": "CM-06",
    "หางดง": "CM-07",
    "สารภี": "CM-08",
    "แม่แตง": "CM-09",
    "เมืองแกน": "CM-09",
    "จอมทอง": "CM-10",
    "ฝาง": "CM-11",
    "ฮอด": "CM-12",
}


class AquaBridge:
    """Sends telemetry and incidents into Aqua Command Center dashboard."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = base_url or os.getenv("AQUA_COMMAND_URL", "http://127.0.0.1:8787")
        self.api_key = api_key or os.getenv("ADMIN_API_KEY", "")
        if not self.api_key:
            logger.warning("ADMIN_API_KEY is not configured for AquaBridge. Authenticated endpoints will reject requests.")

    def _post(self, path: str, payload: dict[str, Any]) -> bool:
        """Makes an authenticated POST request to Aqua Command Center."""
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status in (200, 202)
        except Exception as e:
            logger.debug("AquaBridge post to %s failed: %s", path, e)
            return False

    def push_telemetry(
        self,
        station_id: str,
        turbidity_ntu: Optional[float] = None,
        chlorine_mgl: Optional[float] = None,
        pressure_bar: Optional[float] = None,
        tank_level_pct: Optional[float] = None,
        online: bool = True
    ) -> bool:
        """Pushes sensor telemetry for a specific station."""
        data: dict[str, Any] = {
            "stationId": station_id,
            "online": online
        }
        if turbidity_ntu is not None:
            data["turbidityNtu"] = round(turbidity_ntu, 2)
        if chlorine_mgl is not None:
            data["chlorineMgL"] = round(chlorine_mgl, 2)
        if pressure_bar is not None:
            data["pressureBar"] = round(pressure_bar, 2)
        if tank_level_pct is not None:
            data["tankLevelPct"] = round(tank_level_pct, 1)

        return self._post("/api/telemetry", data)

    def sync_rtu_stations(self, rtu_data: dict[str, dict[str, Any]]) -> int:
        """
        Parses 660+ live PWA RTU stations and feeds corresponding values
        into Aqua Command Center stations.
        """
        updated_count = 0
        for station_id, station in rtu_data.items():
            name = station.get("plantname", "") + " " + (station.get("wwcode_name") or "")
            matched_id = None
            for kw, target_id in STATION_MAP.items():
                if kw in name:
                    matched_id = target_id
                    break

            if matched_id:
                def _safe_float(v: Any) -> Optional[float]:
                    try:
                        return float(v) if v and v != "-" else None
                    except (ValueError, TypeError):
                        return None

                ntu = _safe_float(station.get("NTU"))
                cl = _safe_float(station.get("Cl"))
                is_online = station.get("pic") in ("pass", "fail")

                if self.push_telemetry(matched_id, turbidity_ntu=ntu, chlorine_mgl=cl, online=is_online):
                    updated_count += 1

        logger.info("AquaBridge synchronized %d live stations to Command Center.", updated_count)
        return updated_count

    def push_pwa_incident(self, outage: dict[str, Any], is_resolved: bool = False) -> bool:
        """
        Pushes a PWA Water Outage announcement into Aqua Command Center
        so it appears in the Incident Table and Map in real time.
        """
        branch_name = outage.get("branch_name", "กปภ.")
        matched_id = None
        for kw, target_id in STATION_MAP.items():
            if kw in branch_name:
                matched_id = target_id
                break

        severity = "resolved" if is_resolved else "critical" if "แตก" in outage.get("title", "") else "warning"
        title = outage.get("title", "ประกาศหยุดจ่ายน้ำ")
        cause = outage.get("cause", "")
        area = outage.get("affected_area", "")
        message = f"{cause} | พื้นที่: {area}"[:250]

        payload = {
            "stationId": matched_id or "PWA-HQ",
            "stationName": f"กปภ.สาขา{branch_name}",
            "region": "การประปาส่วนภูมิภาค",
            "title": f"[กปภ.] {title}",
            "severity": severity,
            "message": message,
            "value": outage.get("working_status_name", "กำลังดำเนินการ"),
            "ruleId": "pwa-outage",
            "link": outage.get("link", ""),
            "demo": False
        }

        return self._post("/api/incidents", payload)
