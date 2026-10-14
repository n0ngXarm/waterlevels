"""Background monitoring service for PWA outages and RTU water quality."""

import logging
import threading
import time
from typing import Any, Optional
from src.config import Config
from src.database import Database
from src.pwa_client import PWAClient
from src.telegram_notifier import TelegramNotifier
from src.aqua_bridge import AquaBridge

logger = logging.getLogger(__name__)


class WaterMonitorService:
    """Service that periodically checks PWA feeds and triggers Telegram alerts."""

    def __init__(
        self,
        db: Optional[Database] = None,
        pwa: Optional[PWAClient] = None,
        notifier: Optional[TelegramNotifier] = None,
        bridge: Optional[AquaBridge] = None
    ):
        self.db = db or Database()
        self.pwa = pwa or PWAClient()
        self.notifier = notifier or TelegramNotifier()
        self.bridge = bridge or AquaBridge()
        self.is_running = False
        self._stop_event = threading.Event()
        self.is_initialized = False

    def initialize_baseline(self) -> None:
        """
        Initializes baseline data silently on cold start so that existing historical
        notices are saved to SQLite without spamming the user's Telegram.
        """
        existing_count = self.db.count_outages()
        if existing_count == 0:
            logger.info("Database is empty. Performing silent baseline synchronization...")
            outages = self.pwa.get_all_active_outages(limit=100)
            for item in outages:
                status = item.get("working_status_name", "กำลังดำเนินการ")
                self.db.save_outage(item, initial_status=status)

            logger.info("Baseline sync completed. Saved %d existing notices silently.", len(outages))

            # Send a single polite startup notification
            if self.notifier.default_chat_id:
                startup_msg = (
                    "🟢 <b>[ระบบเริ่มการเฝ้าระวังน้ำประปา 24/7]</b>\n"
                    "──────────────────\n"
                    f"บันทึกฐานข้อมูลประกาศเดิมแล้ว <b>{len(outages)}</b> รายการ\n"
                    "ต่อจากนี้ระบบจะแจ้งเตือนเฉพาะเมื่อมี:\n"
                    " • 🚨 <b>ประกาศใหม่ล่าสุด</b>\n"
                    " • 🟢 <b>อัปเดตเมื่อการซ่อมบำรุงแล้วเสร็จ</b> (น้ำเริ่มกลับมาไหลปกติ)\n"
                    "──────────────────\n"
                    "🔔 <i>ระบบจะไม่ส่งประกาศเก่าย้อนหลังเพื่อไม่ให้รบกวนคุณ</i>"
                )
                self.notifier.send_message(self.notifier.default_chat_id, startup_msg)

        self.is_initialized = True

    def check_outages_once(self) -> int:
        """
        Runs one cycle of checking water outages from PWA API.
        Returns count of new/updated alerts dispatched.
        """
        if not Config.ENABLE_OUTAGE_ALERT:
            logger.info("Outage alert check is disabled in config.")
            return 0

        if not self.is_initialized:
            self.initialize_baseline()

        logger.info("Checking PWA water outage API...")
        outages = self.pwa.get_all_active_outages(limit=100)
        if not outages:
            logger.info("No outages returned from PWA API.")
            return 0

        subscribers = self.db.get_active_subscribers()
        dispatched_count = 0
        max_alerts_per_cycle = 5  # Anti-flood safeguard

        for item in outages:
            if dispatched_count >= max_alerts_per_cycle:
                logger.warning("Reached max alerts limit (%d) for this cycle. Pausing to avoid flooding.", max_alerts_per_cycle)
                break

            alert_key = self.db.generate_alert_key(item)
            current_status = item.get("working_status_name", "กำลังดำเนินการ")
            existing = self.db.get_outage(alert_key)

            if not existing:
                # Brand new outage announcement published AFTER baseline!
                logger.info("New outage found: [%s] %s", item.get("branch_name"), item.get("title"))
                self.db.save_outage(item, initial_status=current_status)

                # Bridge to Aqua Command Center dashboard
                self.bridge.push_pwa_incident(item, is_resolved=False)

                # Send Telegram alert
                sent = self.notifier.broadcast_outage(item, subscribers, is_update=False)
                if sent > 0:
                    dispatched_count += 1
                    self.db.log_event("NEW_OUTAGE_ALERT", f"Branch: {item.get('branch_name')}, Sent: {sent}")
                    time.sleep(2)  # Delay between sends to prevent Telegram flood
            else:
                # Existing outage: check if status changed (e.g. repair finished!)
                last_status = existing.get("last_status_alerted")
                if current_status and last_status and current_status != last_status:
                    logger.info(
                        "Outage status changed for [%s]: %s -> %s",
                        item.get("branch_name"), last_status, current_status
                    )
                    self.db.update_outage_status(alert_key, current_status)

                    # Bridge status update to Aqua Command Center
                    is_resolved = (current_status == "ดำเนินการแล้วเสร็จ")
                    self.bridge.push_pwa_incident(item, is_resolved=is_resolved)

                    # Send update alert (e.g. repairs completed)
                    sent = self.notifier.broadcast_outage(item, subscribers, is_update=True)
                    if sent > 0:
                        dispatched_count += 1
                        self.db.log_event("OUTAGE_STATUS_UPDATE", f"Branch: {item.get('branch_name')}, Status: {current_status}")
                        time.sleep(2)

        logger.info("Outage check completed. Dispatched %d alerts.", dispatched_count)
        return dispatched_count

    def check_quality_once(self) -> int:
        """
        Runs one cycle of checking RTU water quality stations.
        Returns count of abnormal quality alerts dispatched.
        """
        if not Config.ENABLE_QUALITY_ALERT:
            return 0

        subscribers = self.db.get_active_subscribers()
        # Only check quality if there are subscribers specifically requesting quality alerts
        quality_subs = [s for s in subscribers if "quality" in s.get("alert_types", [])]
        if not quality_subs and not Config.TELEGRAM_CHAT_ID:
            return 0

        logger.info("Checking PWA RTU water quality map...")
        stations = self.pwa.fetch_rtu_water_quality()
        if not stations:
            return 0

        # Synchronize live RTU sensor measurements to Aqua Command Center dashboard
        self.bridge.sync_rtu_stations(stations)

        dispatched_count = 0
        max_quality_per_cycle = 3

        for station_id, station in stations.items():
            if dispatched_count >= max_quality_per_cycle:
                break

            is_normal, issues = self.pwa.check_station_quality(station)
            if not is_normal:
                # Skip if all sensors are just offline ("-") to prevent spam
                raw_ph = station.get("pH")
                raw_ntu = station.get("NTU")
                raw_cl = station.get("Cl")
                if raw_ph == "-" and raw_ntu == "-" and raw_cl == "-":
                    continue

                # Check cooldown to avoid spamming alerts for the same station
                if not self.db.is_quality_alert_in_cooldown(
                    station_id,
                    cooldown_hours=Config.QUALITY_ALERT_COOLDOWN_HOURS
                ):
                    plantname = station.get("plantname", "")
                    division = station.get("wwcode_name") or station.get("divisionname") or ""

                    def _safe_float(val: Any) -> Optional[float]:
                        try:
                            return float(val) if val and val != "-" else None
                        except (ValueError, TypeError):
                            return None

                    ph_val = _safe_float(raw_ph)
                    ntu_val = _safe_float(raw_ntu)
                    cl_val = _safe_float(raw_cl)

                    self.db.save_quality_alert(
                        station_id=station_id,
                        plantname=plantname,
                        divisionname=division,
                        ph=ph_val,
                        ntu=ntu_val,
                        cl=cl_val,
                        status=station.get("pic", "fail"),
                        issues=issues
                    )

                    sent = self.notifier.broadcast_quality_alert(
                        station_id, station, issues, subscribers
                    )
                    if sent > 0:
                        dispatched_count += 1
                        self.db.log_event("QUALITY_ALERT", f"Station: {plantname}, Issues: {len(issues)}")
                        time.sleep(2)

        return dispatched_count

    def run_loop(self) -> None:
        """Starts the periodic monitoring loop."""
        self.is_running = True
        self._stop_event.clear()

        # Initialize baseline silently before starting loops
        self.initialize_baseline()

        logger.info(
            "Starting PWA Water Monitor loop (Interval: %d seconds)...",
            Config.CHECK_INTERVAL_SECONDS
        )

        while not self._stop_event.is_set():
            try:
                self.check_outages_once()
                self.check_quality_once()
            except Exception as e:
                logger.error("Error in monitor cycle: %s", e, exc_info=True)

            # Wait for next cycle or stop signal
            if self._stop_event.wait(timeout=Config.CHECK_INTERVAL_SECONDS):
                break

        logger.info("PWA Water Monitor loop stopped.")

    def stop(self) -> None:
        """Signals the monitor loop to stop."""
        self.is_running = False
        self._stop_event.set()
