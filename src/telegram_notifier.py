"""Telegram notification dispatcher with rich HTML formatting and fallback handling."""

import html
import json
import logging
from typing import Any, Optional
import urllib.request
import urllib.error
from src.config import Config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Manages Telegram Bot API communication and formatting."""

    API_BASE = "https://api.telegram.org/bot"

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or Config.TELEGRAM_BOT_TOKEN
        self.default_chat_id = Config.TELEGRAM_CHAT_ID

    @property
    def is_configured(self) -> bool:
        """Returns True if bot token is configured."""
        return bool(self.bot_token)

    def _api_url(self, method: str) -> str:
        """Constructs Telegram Bot API endpoint URL."""
        return f"{self.API_BASE}{self.bot_token}/{method}"

    def test_connection(self) -> tuple[bool, str]:
        """Tests connection with Telegram API using getMe."""
        if not self.is_configured:
            return False, "TELEGRAM_BOT_TOKEN ยังไม่ได้ตั้งค่าใน .env"

        try:
            req = urllib.request.Request(self._api_url("getMe"), headers={"User-Agent": "PWA-Water-Alert/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    bot_user = data.get("result", {}).get("username", "Unknown")
                    bot_name = data.get("result", {}).get("first_name", "Unknown")
                    return True, f"เชื่อมต่อสำเร็จ: {bot_name} (@{bot_user})"
                return False, f"Telegram API error: {data.get('description')}"
        except Exception as e:
            return False, f"การเชื่อมต่อล้มเหลว: {e}"

    def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: Optional[dict[str, Any]] = None,
        disable_web_page_preview: bool = True
    ) -> bool:
        """Sends an HTML formatted text message."""
        if not self.is_configured:
            logger.warning("Telegram Bot Token is not configured. Message skipped.")
            return False

        payload: dict[str, Any] = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_web_page_preview
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._api_url("sendMessage"),
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return bool(res.get("ok"))
        except Exception as e:
            logger.error("Failed to send Telegram message to %s: %s", chat_id, e)
            return False

    def send_photo(
        self,
        chat_id: str,
        photo_url: str,
        caption: str,
        reply_markup: Optional[dict[str, Any]] = None
    ) -> bool:
        """
        Sends photo with caption. Falls back to text message if photo fails
        or if caption length exceeds Telegram's 1024-character photo caption limit.
        """
        if not self.is_configured:
            return False

        # Telegram photo caption limit is 1024 chars
        if len(caption) > 1000:
            # Send photo with concise caption, followed by full text
            short_caption = caption[:950] + "...\n(อ่านรายละเอียดเพิ่มเติมด้านล่าง)"
            photo_payload: dict[str, Any] = {
                "chat_id": str(chat_id),
                "photo": photo_url,
                "caption": short_caption,
                "parse_mode": "HTML"
            }
            try:
                req = urllib.request.Request(
                    self._api_url("sendPhoto"),
                    data=json.dumps(photo_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=15):
                    pass
                # Send the rest as text message
                return self.send_message(chat_id, caption, reply_markup=reply_markup)
            except Exception as e:
                logger.warning("Failed to send photo, falling back to message: %s", e)
                return self.send_message(chat_id, caption, reply_markup=reply_markup)

        payload: dict[str, Any] = {
            "chat_id": str(chat_id),
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            req = urllib.request.Request(
                self._api_url("sendPhoto"),
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    return True
                # Fallback to sendMessage if photo URL rejected
                return self.send_message(chat_id, caption, reply_markup=reply_markup)
        except Exception as e:
            logger.warning("sendPhoto failed (%s), falling back to text message", e)
            return self.send_message(chat_id, caption, reply_markup=reply_markup)

    # ---------------- Formatters ----------------

    @staticmethod
    def format_outage_message(outage: dict[str, Any], is_update: bool = False) -> str:
        """Formats water outage notice into rich Telegram HTML."""
        branch = html.escape(outage.get("branch_name", "ไม่ระบุสาขา"))
        title = html.escape(outage.get("title", ""))
        cause = html.escape(outage.get("cause", "ไม่มีข้อมูล"))
        area = html.escape(outage.get("affected_area", "ไม่มีข้อมูล"))
        status = outage.get("working_status_name", "กำลังดำเนินการ")
        start = outage.get("start_date", "-")
        end = outage.get("end_date", "-")
        extend_end = outage.get("extend_end_date")
        contact = html.escape(outage.get("contact", "1662"))
        comment = html.escape(outage.get("comment", ""))

        # Status icon and styling
        if status == "ดำเนินการแล้วเสร็จ":
            status_badge = "🟢 <b>ดำเนินการแล้วเสร็จ (น้ำไหลปกติแล้ว)</b>"
            header = "✅ <b>[อัปเดต: น้ำประปาไหลปกติแล้ว]</b>"
        elif status == "ยกเลิก":
            status_badge = "⚪ <b>ยกเลิกประกาศ</b>"
            header = "ℹ️ <b>[แจ้งยกเลิกประกาศหยุดจ่ายน้ำ]</b>"
        else:
            status_badge = "🟡 <b>กำลังดำเนินการซ่อมบำรุง</b>"
            header = "🚨 <b>[ประกาศหยุดจ่ายน้ำฉุกเฉิน / ซ่อมท่อ]</b>" if not is_update else "⚠️ <b>[อัปเดตสถานะการหยุดจ่ายน้ำ]</b>"

        time_info = f"⏱️ <b>ระยะเวลา:</b> {start} ถึง {end}"
        if extend_end:
            time_info += f"\n⏳ <b>เลื่อนเวลาเสร็จสิ้นเป็น:</b> {extend_end}"

        lines = [
            header,
            f"💧 <b>การประปาส่วนภูมิภาค (กปภ.) สาขา{branch}</b>",
            "──────────────────",
            f"📌 <b>เรื่อง:</b> {title}",
            f"⚙️ <b>สาเหตุ:</b> {cause}",
            f"📍 <b>พื้นที่ได้รับผลกระทบ:</b>\n{area}",
            time_info,
            f"📊 <b>สถานะ:</b> {status_badge}",
        ]

        if contact:
            lines.append(f"📞 <b>ติดต่อสอบถาม:</b> {contact} หรือ โทร 1662")

        if comment:
            lines.append(f"💬 <b>คำแนะนำ:</b> {comment}")

        lines.append("──────────────────")
        lines.append("🔔 <i>ระบบแจ้งเตือนน้ำประปาส่วนภูมิภาคอัตโนมัติ</i>")

        return "\n".join(lines)

    @staticmethod
    def get_outage_keyboard(outage: dict[str, Any]) -> dict[str, Any]:
        """Generates inline keyboard for an outage message."""
        buttons = []
        link = outage.get("link")
        if link and link.startswith("http"):
            buttons.append([{"text": "📄 ดูประกาศฉบับเต็ม / แผนผัง", "url": link}])

        buttons.append([
            {"text": "📞 สายด่วน กปภ. 1662", "url": "https://www.pwa.co.th/news/call1662"}
        ])

        return {"inline_keyboard": buttons}

    @staticmethod
    def format_quality_alert_message(
        station_id: str,
        station: dict[str, Any],
        issues: list[str]
    ) -> str:
        """Formats water quality alert into rich Telegram HTML."""
        plantname = html.escape(station.get("plantname", "ไม่ระบุสถานี"))
        division = html.escape(station.get("wwcode_name") or station.get("divisionname") or "-")
        date_str = station.get("date", "-")
        time_str = station.get("time", "-")
        ph = station.get("pH", "-")
        ntu = station.get("NTU", "-")
        cl = station.get("Cl", "-")

        lines = [
            "⚠️ <b>[แจ้งเตือนคุณภาพน้ำประปา RTU ผิดเกณฑ์มาตรฐาน]</b>",
            f"🏭 <b>สถานีผลิตน้ำ:</b> {plantname}",
            f"🏢 <b>สังกัด:</b> {division}",
            "──────────────────",
            "🚨 <b>ประเด็นที่ไม่ผ่านเกณฑ์:</b>",
        ]

        for issue in issues:
            lines.append(f" • ❌ {html.escape(issue)}")

        lines.extend([
            "",
            "🧪 <b>ค่าตรวจวัดเซนเซอร์ RTU ล่าสุด:</b>",
            f" • ค่าความเป็นกรด-ด่าง (pH): <b>{ph}</b> (เกณฑ์: {Config.PH_MIN} - {Config.PH_MAX})",
            f" • ความขุ่น (Turbidity): <b>{ntu} NTU</b> (เกณฑ์: ≤ {Config.NTU_MAX} NTU)",
            f" • คลอรีนคงเหลือ (Cl): <b>{cl} mg/L</b> (เกณฑ์: {Config.CL_MIN} - {Config.CL_MAX} mg/L)",
            f"🕒 <b>เวลาตรวจวัด:</b> {date_str} {time_str} น.",
            "──────────────────",
            "ℹ️ <i>ข้อมูลส่งตรงจากสถานีตรวจวัดคุณภาพน้ำ RTU การประปาส่วนภูมิภาค</i>"
        ])

        return "\n".join(lines)

    # ---------------- Broadcast Functions ----------------

    def broadcast_outage(
        self,
        outage: dict[str, Any],
        subscribers: list[dict[str, Any]],
        is_update: bool = False
    ) -> int:
        """
        Broadcasts water outage notice to default chat_id and relevant subscribers.
        Returns total number of recipients successfully sent to.
        """
        branch_name = outage.get("branch_name", "")
        message = self.format_outage_message(outage, is_update=is_update)
        keyboard = self.get_outage_keyboard(outage)
        photo_url = outage.get("link")

        # Collect target chat_ids to prevent duplicates
        target_chat_ids: set[str] = set()

        # Check default configured chat_id
        if self.default_chat_id and Config.is_branch_monitored(branch_name):
            target_chat_ids.add(str(self.default_chat_id))

        # Check subscribers
        for sub in subscribers:
            chat_id = str(sub.get("chat_id"))
            sub_branches = sub.get("branches", ["*"])
            alert_types = sub.get("alert_types", ["outage"])

            if "outage" not in alert_types:
                continue

            # Check if subscriber wants this branch
            if "*" in sub_branches:
                target_chat_ids.add(chat_id)
            else:
                for sb in sub_branches:
                    if sb.lower() in branch_name.lower():
                        target_chat_ids.add(chat_id)
                        break

        success_count = 0
        for chat_id in target_chat_ids:
            sent = False
            # If poster image link is present, try sending photo
            if photo_url and photo_url.startswith("http") and not photo_url.endswith(".pdf"):
                sent = self.send_photo(chat_id, photo_url, message, reply_markup=keyboard)
            if not sent:
                sent = self.send_message(chat_id, message, reply_markup=keyboard)

            if sent:
                success_count += 1

        logger.info("Broadcast outage to %d recipients (Branch: %s)", success_count, branch_name)
        return success_count

    def broadcast_quality_alert(
        self,
        station_id: str,
        station: dict[str, Any],
        issues: list[str],
        subscribers: list[dict[str, Any]]
    ) -> int:
        """Broadcasts water quality alert to subscribers."""
        message = self.format_quality_alert_message(station_id, station, issues)
        target_chat_ids: set[str] = set()

        if self.default_chat_id and Config.ENABLE_QUALITY_ALERT:
            target_chat_ids.add(str(self.default_chat_id))

        plant_name = station.get("plantname", "").lower()

        for sub in subscribers:
            chat_id = str(sub.get("chat_id"))
            alert_types = sub.get("alert_types", ["outage"])
            if "quality" not in alert_types:
                continue

            sub_branches = sub.get("branches", ["*"])
            if "*" in sub_branches:
                target_chat_ids.add(chat_id)
            else:
                for sb in sub_branches:
                    if sb.lower() in plant_name:
                        target_chat_ids.add(chat_id)
                        break

        success_count = 0
        for chat_id in target_chat_ids:
            if self.send_message(chat_id, message):
                success_count += 1

        return success_count
