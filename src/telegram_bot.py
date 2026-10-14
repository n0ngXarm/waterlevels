"""Interactive Telegram Bot Handler for PWA Water Alert System."""

import html
import json
import logging
import time
from typing import Any, Optional
import urllib.request
from src.config import Config
from src.database import Database
from src.pwa_client import PWAClient
from src.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class TelegramBot:
    """Handles Telegram Bot interactive commands and polling."""

    def __init__(self, db: Database, pwa: PWAClient, notifier: TelegramNotifier):
        self.db = db
        self.pwa = pwa
        self.notifier = notifier
        self.is_running = False
        self.last_update_id = 0

    def start_polling(self) -> None:
        """Starts the long-polling loop for receiving Telegram commands."""
        if not self.notifier.is_configured:
            logger.error("Cannot start bot polling: TELEGRAM_BOT_TOKEN is not set.")
            return

        self.is_running = True
        logger.info("Telegram Bot polling started...")

        while self.is_running:
            try:
                updates = self._get_updates(offset=self.last_update_id + 1, timeout=20)
                for update in updates:
                    self.last_update_id = max(self.last_update_id, update.get("update_id", 0))
                    self._handle_update(update)
            except Exception as e:
                logger.error("Error during bot polling: %s", e)
                time.sleep(3)

    def stop(self) -> None:
        """Stops the polling loop."""
        self.is_running = False
        logger.info("Telegram Bot polling stopped.")

    def _get_updates(self, offset: int = 0, timeout: int = 20) -> list[dict[str, Any]]:
        """Calls getUpdates from Telegram API."""
        url = self.notifier._api_url(f"getUpdates?offset={offset}&timeout={timeout}")
        req = urllib.request.Request(url, headers={"User-Agent": "PWA-Water-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("result", [])

    def _handle_update(self, update: dict[str, Any]) -> None:
        """Dispatches an update to the corresponding handler."""
        # Handle regular message
        message = update.get("message")
        if message:
            text = message.get("text", "").strip()
            chat_id = str(message.get("chat", {}).get("id"))
            user = message.get("from", {})
            username = user.get("username")
            first_name = user.get("first_name", "")

            if not text:
                return

            logger.info("Received command from %s (@%s): %s", chat_id, username, text)

            if text.startswith("/start"):
                self._cmd_start(chat_id, username, first_name)
            elif text.startswith("/help"):
                self._cmd_help(chat_id)
            elif text.startswith("/latest"):
                parts = text.split(maxsplit=1)
                branch_arg = parts[1].strip() if len(parts) > 1 else None
                self._cmd_latest(chat_id, branch_arg)
            elif text.startswith("/branch"):
                parts = text.split(maxsplit=1)
                branch_arg = parts[1].strip() if len(parts) > 1 else None
                self._cmd_branch(chat_id, branch_arg)
            elif text.startswith("/quality"):
                parts = text.split(maxsplit=1)
                query_arg = parts[1].strip() if len(parts) > 1 else None
                self._cmd_quality(chat_id, query_arg)
            elif text.startswith("/subscribe"):
                parts = text.split(maxsplit=1)
                branches_arg = parts[1].strip() if len(parts) > 1 else "*"
                self._cmd_subscribe(chat_id, username, first_name, branches_arg)
            elif text.startswith("/unsubscribe"):
                self._cmd_unsubscribe(chat_id)
            elif text.startswith("/status"):
                self._cmd_status(chat_id)
            else:
                self.notifier.send_message(
                    chat_id,
                    "❓ ไม่พบคำสั่งนี้ พิมพ์ /help เพื่อดูคำสั่งทั้งหมดที่สามารถใช้งานได้ครับ"
                )

        # Handle callback query (inline button clicks)
        callback = update.get("callback_query")
        if callback:
            self._handle_callback_query(callback)

    # ---------------- Command Handlers ----------------

    def _cmd_start(self, chat_id: str, username: Optional[str], first_name: str) -> None:
        """Handler for /start command."""
        # Auto-subscribe with default all branches
        self.db.add_or_update_subscriber(chat_id, username, first_name, branches=["*"], alert_types=["outage", "quality"])

        greeting = f"สวัสดีครับคุณ {html.escape(first_name)}! 👋"
        msg = (
            f"{greeting}\n\n"
            "ยินดีต้อนรับสู่ <b>ระบบแจ้งเตือนน้ำประปาส่วนภูมิภาค (กปภ.)</b>\n"
            "ระบบนี้จะช่วยแจ้งเตือนข้อมูลเกี่ยวกับน้ำประปาให้คุณอัตโนมัติ:\n\n"
            "🔹 <b>ประกาศหยุดจ่ายน้ำ / ท่อแตก / ซ่อมท่อ</b> ทั่วประเทศ\n"
            "🔹 <b>อัปเดตสถานะการซ่อมบำรุง</b> (เมื่อน้ำเริ่มกลับมาไหลปกติ)\n"
            "🔹 <b>ตรวจวัดคุณภาพน้ำประปา RTU</b> (pH, ความขุ่น, คลอรีนคงเหลือ)\n\n"
            "✅ <i>ระบบได้เปิดใช้งานการแจ้งเตือนสำหรับคุณแล้ว (ทุกสาขาทั่วประเทศ)</i>\n"
            "หากต้องการรับเฉพาะสาขาของคุณ พิมพ์: <code>/subscribe &lt;ชื่อสาขา&gt;</code>\n\n"
            "เลือกเมนูด้านล่างหรือพิมพ์คำสั่งได้ทันที:"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🚨 ข่าวหยุดจ่ายน้ำล่าสุด", "callback_data": "cmd_latest"},
                    {"text": "💧 ตรวจสอบคุณภาพน้ำ", "callback_data": "cmd_quality"}
                ],
                [
                    {"text": "📍 สถานะระบบ", "callback_data": "cmd_status"},
                    {"text": "📖 วิธีใช้งาน / คำสั่ง", "callback_data": "cmd_help"}
                ],
                [
                    {"text": "🌐 ศูนย์ควบคุม Web Dashboard", "url": "http://localhost:8787"}
                ]
            ]
        }

        self.notifier.send_message(chat_id, msg, reply_markup=keyboard)

    def _cmd_help(self, chat_id: str) -> None:
        """Handler for /help command."""
        msg = (
            "📖 <b>คู่มือคำสั่งใช้งานระบบแจ้งเตือนน้ำประปา กปภ.</b>\n"
            "──────────────────\n"
            "🔹 <code>/latest</code> - ดูประกาศหยุดจ่ายน้ำล่าสุด 5 รายการ\n"
            "🔹 <code>/latest &lt;ชื่อสาขา&gt;</code> - ดูประกาศเฉพาะสาขา เช่น <code>/latest ชลบุรี</code>\n"
            "🔹 <code>/branch &lt;ชื่อสาขา&gt;</code> - ค้นหาสาขา กปภ. และดูสถานะน้ำ\n"
            "🔹 <code>/quality</code> - สรุปสถานะตรวจวัดคุณภาพน้ำประปา RTU ทั่วประเทศ\n"
            "🔹 <code>/quality &lt;ชื่อสถานีหรือสาขา&gt;</code> - ดูค่า pH, ความขุ่น, คลอรีนเฉพาะจุด\n"
            "🔹 <code>/subscribe &lt;สาขา1, สาขา2&gt;</code> - เลือกรับแจ้งเตือนเฉพาะสาขาที่ต้องการ\n"
            "🔹 <code>/subscribe *</code> - รับแจ้งเตือนทุกสาขาทั่วประเทศ\n"
            "🔹 <code>/unsubscribe</code> - ปิดการแจ้งเตือน\n"
            "🔹 <code>/status</code> - ตรวจสอบสถานะการทำงานของระบบ\n"
            "──────────────────\n"
            "📞 <i>สายด่วนการประปาส่วนภูมิภาค โทร 1662</i>"
        )
        self.notifier.send_message(chat_id, msg)

    def _cmd_latest(self, chat_id: str, branch_arg: Optional[str] = None) -> None:
        """Handler for /latest [branch] command."""
        self.notifier.send_message(chat_id, "⏳ กำลังดึงข้อมูลประกาศหยุดจ่ายน้ำล่าสุดจาก กปภ. กรุณารอสักครู่...")

        branch_code = "1001"
        branch_filter_name = None

        if branch_arg:
            found = self.pwa.find_branch(branch_arg)
            if found:
                branch_code = found.get("code", "1001")
                branch_filter_name = found.get("name")
            else:
                branch_filter_name = branch_arg

        outages = self.pwa.fetch_outages(branch_code=branch_code, page=1, limit=5)

        if not outages:
            text = f"✅ ไม่พบประกาศหยุดจ่ายน้ำสำหรับ '{branch_arg or 'ทั่วประเทศ'}' ในขณะนี้ (น้ำประปาให้บริการปกติ)"
            self.notifier.send_message(chat_id, text)
            return

        for item in outages[:4]:
            msg = self.notifier.format_outage_message(item)
            kb = self.notifier.get_outage_keyboard(item)
            photo_url = item.get("link")
            if photo_url and photo_url.startswith("http") and not photo_url.endswith(".pdf"):
                self.notifier.send_photo(chat_id, photo_url, msg, reply_markup=kb)
            else:
                self.notifier.send_message(chat_id, msg, reply_markup=kb)

    def _cmd_branch(self, chat_id: str, branch_arg: Optional[str]) -> None:
        """Handler for /branch command."""
        if not branch_arg:
            self.notifier.send_message(
                chat_id,
                "ℹ️ กรุณาระบุชื่อสาขาที่ต้องการค้นหา เช่น:\n<code>/branch ชลบุรี</code> หรือ <code>/branch เชียงใหม่</code>"
            )
            return

        found = self.pwa.find_branch(branch_arg)
        if not found:
            self.notifier.send_message(chat_id, f"❌ ไม่พบสาขาที่ตรงกับคำค้น '{branch_arg}'")
            return

        code = found.get("code")
        name = found.get("name")
        outages = self.pwa.fetch_outages(branch_code=code, limit=3)

        lines = [
            f"🏢 <b>ข้อมูลการประปาส่วนภูมิภาค: {name}</b>",
            f"🔑 <b>รหัสสาขา:</b> <code>{code}</code>",
            "──────────────────",
        ]

        if outages:
            lines.append(f"⚠️ <b>พบประกาศหยุดจ่ายน้ำ {len(outages)} รายการ:</b>\n")
            for idx, outg in enumerate(outages, 1):
                st = outg.get("working_status_name", "กำลังดำเนินการ")
                lines.append(f"{idx}. 📌 <b>{html.escape(outg.get('title', ''))}</b>")
                lines.append(f"   ⏱️ {outg.get('start_date')} - {outg.get('end_date')}")
                lines.append(f"   📊 สถานะ: <b>{st}</b>\n")
        else:
            lines.append("✅ <b>สถานะปัจจุบัน:</b> น้ำประปาไหลปกติ ไม่มีประกาศหยุดจ่ายน้ำ")

        lines.append("──────────────────")
        lines.append(f"🔔 รับแจ้งเตือนสาขานี้ พิมพ์: <code>/subscribe {name}</code>")

        self.notifier.send_message(chat_id, "\n".join(lines))

    def _cmd_quality(self, chat_id: str, query: Optional[str] = None) -> None:
        """Handler for /quality [station_name] command."""
        self.notifier.send_message(chat_id, "⏳ กำลังดึงข้อมูลตรวจวัดคุณภาพน้ำประปา RTU...")
        stations = self.pwa.fetch_rtu_water_quality()

        if not stations:
            self.notifier.send_message(chat_id, "⚠️ ไม่สามารถเชื่อมต่อระบบตรวจวัดคุณภาพน้ำ RTU ได้ในขณะนี้")
            return

        if query:
            query_clean = query.lower()
            matches = [
                (sid, s) for sid, s in stations.items()
                if query_clean in s.get("plantname", "").lower() or query_clean in s.get("wwcode_name", "").lower()
            ]

            if not matches:
                self.notifier.send_message(chat_id, f"❌ ไม่พบสถานีผลิตน้ำที่ตรงกับคำค้น '{query}'")
                return

            lines = [f"💧 <b>ผลการตรวจวัดคุณภาพน้ำ ({len(matches)} สถานีที่พบ):</b>\n"]
            for sid, st in matches[:5]:
                is_normal, issues = self.pwa.check_station_quality(st)
                badge = "🟢 ผ่านเกณฑ์มาตรฐาน" if is_normal else "🔴 ไม่ผ่านเกณฑ์มาตรฐาน"
                lines.append(f"🏭 <b>{html.escape(st.get('plantname', ''))}</b>")
                lines.append(f"   สถานะ: {badge}")
                lines.append(f"   • pH: <b>{st.get('pH', '-')}</b> | ความขุ่น: <b>{st.get('NTU', '-')} NTU</b> | คลอรีน: <b>{st.get('Cl', '-')} mg/L</b>")
                lines.append(f"   • อัปเดต: {st.get('date', '')} {st.get('time', '')} น.\n")

            self.notifier.send_message(chat_id, "\n".join(lines))
            return

        # Overall summary
        total = len(stations)
        pass_count = sum(1 for s in stations.values() if s.get("pic") == "pass")
        fail_count = total - pass_count

        lines = [
            "💧 <b>สรุปสถานการณ์คุณภาพน้ำประปา RTU ทั่วประเทศ</b>",
            "──────────────────",
            f"🏭 สถานีตรวจวัดทั้งหมด: <b>{total}</b> สถานี",
            f"🟢 ผ่านเกณฑ์มาตรฐาน: <b>{pass_count}</b> สถานี ({pass_count/total*100:.1f}%)",
            f"🔴 ไม่ผ่านเกณฑ์ / ค่าเบี่ยงเบน: <b>{fail_count}</b> สถานี",
            "──────────────────",
            "📊 <b>เกณฑ์มาตรฐานน้ำประปาดื่มได้ (กปภ.):</b>",
            f" • ค่าความเป็นกรด-ด่าง (pH): <b>{Config.PH_MIN} - {Config.PH_MAX}</b>",
            f" • ความขุ่น: <b>ไม่เกิน {Config.NTU_MAX} NTU</b>",
            f" • คลอรีนคงเหลือ: <b>{Config.CL_MIN} - {Config.CL_MAX} mg/L</b>",
            "",
            "🔍 ค้นหาสถานีเฉพาะจุด พิมพ์: <code>/quality &lt;ชื่อสถานีหรือจังหวัด&gt;</code>"
        ]
        self.notifier.send_message(chat_id, "\n".join(lines))

    def _cmd_subscribe(
        self,
        chat_id: str,
        username: Optional[str],
        first_name: str,
        branches_arg: str
    ) -> None:
        """Handler for /subscribe [branch1, branch2...] command."""
        if branches_arg == "*":
            branches = ["*"]
            desc = "ทุกสาขาทั่วประเทศ"
        else:
            branches = [b.strip() for b in branches_arg.split(",") if b.strip()]
            desc = ", ".join(branches)

        self.db.add_or_update_subscriber(chat_id, username, first_name, branches=branches)
        msg = (
            f"✅ <b>บันทึกการตั้งค่าแจ้งเตือนสำเร็จ!</b>\n\n"
            f"📍 <b>สาขาที่คุณติดตาม:</b> <code>{desc}</code>\n"
            "เมื่อมีประกาศหยุดจ่ายน้ำ ท่อแตก หรือสถานะซ่อมเสร็จ ระบบจะแจ้งเตือนมายังแชทนี้ทันที 🔔"
        )
        self.notifier.send_message(chat_id, msg)

    def _cmd_unsubscribe(self, chat_id: str) -> None:
        """Handler for /unsubscribe command."""
        self.db.set_subscriber_active(chat_id, False)
        msg = "🔕 <b>ปิดการแจ้งเตือนเรียบร้อยแล้ว</b>\nคุณสามารถกลับมาเปิดใหม่ได้ตลอดเวลาเพียงพิมพ์ <code>/start</code> ครับ"
        self.notifier.send_message(chat_id, msg)

    def _cmd_status(self, chat_id: str) -> None:
        """Handler for /status command."""
        sub_count = self.db.count_subscribers()
        outage_count = self.db.count_outages()
        sub_info = self.db.get_subscriber(chat_id)
        your_branches = ", ".join(sub_info.get("branches", ["*"])) if sub_info else "ยังไม่ได้ลงทะเบียน"

        lines = [
            "⚙️ <b>สถานะระบบแจ้งเตือนน้ำประปาส่วนภูมิภาค (กปภ.)</b>",
            "──────────────────",
            "🟢 <b>สถานะการทำงาน:</b> กำลังเฝ้าระวังแบบ Real-time",
            f"⏱️ <b>ความถี่การตรวจเช็ค:</b> ทุก {Config.CHECK_INTERVAL_SECONDS // 60} นาที",
            f"👥 <b>จำนวนผู้รับแจ้งเตือน:</b> {sub_count} คน",
            f"📦 <b>บันทึกประวัติการแจ้งเตือนแล้ว:</b> {outage_count} รายการ",
            f"🎯 <b>การตั้งค่าของคุณ:</b> <code>{your_branches}</code>",
            "──────────────────",
            "🌐 <b>ศูนย์ควบคุม Web Dashboard:</b> http://localhost:8787",
            "💧 <i>Provincial Waterworks Authority Alert Bot v1.0</i>"
        ]
        self.notifier.send_message(chat_id, "\n".join(lines))

    # ---------------- Callback Queries ----------------

    def _handle_callback_query(self, callback: dict[str, Any]) -> None:
        """Handles inline keyboard button clicks."""
        data = callback.get("data", "")
        message = callback.get("message", {})
        chat_id = str(message.get("chat", {}).get("id"))

        if data == "cmd_latest":
            self._cmd_latest(chat_id)
        elif data == "cmd_quality":
            self._cmd_quality(chat_id)
        elif data == "cmd_status":
            self._cmd_status(chat_id)
        elif data == "cmd_help":
            self._cmd_help(chat_id)
