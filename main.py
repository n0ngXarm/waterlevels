"""Unified entry point for PWA Water Notification System.
ระบบแจ้งเตือนน้ำประปาส่วนภูมิภาค (กปภ.) ไปยัง Telegram
"""

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from src.config import BASE_DIR, Config
from src.database import Database
from src.monitor_service import WaterMonitorService
from src.pwa_client import PWAClient
from src.telegram_bot import TelegramBot
from src.telegram_notifier import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("PWA_WaterSystem")


def cmd_test_fetch() -> None:
    """Tests fetching live data from PWA without sending Telegram messages."""
    print("=" * 60)
    print("💧 ทดสอบการดึงข้อมูลสดจากการประปาส่วนภูมิภาค (กปภ.)")
    print("=" * 60)

    client = PWAClient()

    # 1. Test Outage API
    print("\n[1/2] กำลังทดสอบดึงข้อมูลประกาศหยุดจ่ายน้ำ (PWA Outage API)...")
    outages = client.get_all_active_outages(limit=10)
    print(f"✅ ดึงข้อมูลสำเร็จ! พบประกาศที่กำลังเผยแพร่: {len(outages)} รายการ (สุ่มแสดง 3 รายการล่าสุด):")
    for idx, item in enumerate(outages[:3], 1):
        print(f"\n  --- รายการที่ {idx} ---")
        print(f"  🏢 สาขา: กปภ.สาขา {item.get('branch_name')}")
        print(f"  📌 หัวข้อ: {item.get('title')}")
        print(f"  ⚙️ สาเหตุ: {item.get('cause')}")
        print(f"  📍 พื้นที่: {item.get('affected_area')[:100]}...")
        print(f"  ⏱️ ระยะเวลา: {item.get('start_date')} ถึง {item.get('end_date')}")
        print(f"  📊 สถานะ: {item.get('working_status_name')}")
        print(f"  🖼️ โปสเตอร์: {item.get('link')}")

    # 2. Test RTU Water Quality
    print("\n[2/2] กำลังทดสอบดึงข้อมูลตรวจวัดคุณภาพน้ำประปา RTU (Sensors)...")
    stations = client.fetch_rtu_water_quality()
    print(f"✅ ดึงข้อมูลสำเร็จ! พบสถานีตรวจวัดทั้งหมด: {len(stations)} สถานี")

    # Sample standard analysis
    passed = [s for s in stations.values() if s.get("pic") == "pass"]
    failed = [s for s in stations.values() if s.get("pic") != "pass"]
    print(f"  🟢 สถานีผ่านเกณฑ์: {len(passed)} สถานี")
    print(f"  🔴 สถานีไม่ผ่านเกณฑ์ / ค่าเบี่ยงเบน: {len(failed)} สถานี")

    if failed:
        print("\n  ตัวอย่างสถานีที่ไม่ผ่านเกณฑ์มาตรฐาน กปภ.:")
        for s in failed[:3]:
            is_normal, issues = client.check_station_quality(s)
            print(f"  - {s.get('plantname')} (สังกัด: {s.get('wwcode_name') or s.get('divisionname')})")
            print(f"    pH: {s.get('pH')} | NTU: {s.get('NTU')} | Cl: {s.get('Cl')} | Issues: {', '.join(issues)}")

    print("\n" + "=" * 60)
    print("✨ การทดสอบดึงข้อมูลจาก กปภ. เสร็จสมบูรณ์ ข้อมูลพร้อมใช้งาน 100%!")
    print("=" * 60)


def cmd_test_telegram() -> None:
    """Tests sending a sample notification to configured Telegram Chat ID."""
    print("=" * 60)
    print("📲 ทดสอบการเชื่อมต่อและส่งข้อความไปยัง Telegram")
    print("=" * 60)

    notifier = TelegramNotifier()

    print(f"Bot Token: {'ตั้งค่าแล้ว (ความยาว ' + str(len(Config.TELEGRAM_BOT_TOKEN)) + ' ตัวอักษร)' if Config.is_telegram_configured() else '❌ ยังไม่ได้ตั้งค่า'}")
    print(f"Target Chat ID: {Config.TELEGRAM_CHAT_ID or '❌ ยังไม่ได้ตั้งค่า'}")

    ok, msg = notifier.test_connection()
    if not ok:
        print(f"\n❌ การเชื่อมต่อล้มเหลว: {msg}")
        print("💡 กรุณาตรวจสอบ TELEGRAM_BOT_TOKEN ในไฟล์ .env")
        return

    print(f"\n✅ {msg}")

    if not Config.TELEGRAM_CHAT_ID:
        print("\n⚠️ ยังไม่ได้ระบุ TELEGRAM_CHAT_ID ในไฟล์ .env")
        print("💡 คุณสามารถรับ Chat ID ได้โดยการทักบอท @userinfobot บน Telegram แล้วนำ ID มาใส่ใน .env")
        return

    print(f"\nกำลังส่งข้อความทดสอบไปยัง Chat ID: {Config.TELEGRAM_CHAT_ID}...")
    test_text = (
        "💧 <b>[ทดสอบระบบแจ้งเตือนน้ำประปาส่วนภูมิภาค]</b>\n"
        "──────────────────\n"
        "✅ บอทแจ้งเตือนของคุณเชื่อมต่อกับระบบสำเร็จเรียบร้อยแล้ว!\n\n"
        "พร้อมรับการแจ้งเตือนเมื่อมี:\n"
        " • 🚨 ประกาศหยุดจ่ายน้ำ / ท่อแตกฉุกเฉิน / ซ่อมท่อ\n"
        " • 🟢 อัปเดตเมื่อซ่อมเสร็จและน้ำเริ่มกลับมาไหลปกติ\n"
        " • 🧪 แจ้งเตือนเมื่อคุณภาพน้ำประปา RTU ผิดเกณฑ์มาตรฐาน\n"
        "──────────────────\n"
        "🔔 <i>PWA Water Alert System</i>"
    )

    sent = notifier.send_message(Config.TELEGRAM_CHAT_ID, test_text)
    if sent:
        print("🎉 ส่งข้อความสำเร็จ! กรุณาตรวจสอบแอปพลิเคชัน Telegram ของคุณ")
    else:
        print("❌ การส่งข้อความล้มเหลว กรุณาตรวจสอบว่าคุณได้กด 'Start' แชทกับบอทแล้วหรือยัง")


def cmd_setup() -> None:
    """Interactive wizard to configure .env settings."""
    env_file = BASE_DIR / ".env"
    print("=" * 60)
    print("🛠️ ระบบช่วยตั้งค่า (Setup Wizard) แจ้งเตือนน้ำประปา กปภ.")
    print("=" * 60)

    token = input(f"ระบุ Telegram Bot Token [{Config.TELEGRAM_BOT_TOKEN or 'ยังไม่มี'}]: ").strip()
    if not token and Config.TELEGRAM_BOT_TOKEN:
        token = Config.TELEGRAM_BOT_TOKEN

    chat_id = input(f"ระบุ Telegram Chat ID ผู้รับหลัก [{Config.TELEGRAM_CHAT_ID or 'ยังไม่มี'}]: ").strip()
    if not chat_id and Config.TELEGRAM_CHAT_ID:
        chat_id = Config.TELEGRAM_CHAT_ID

    branches = input("ระบุสาขา กปภ. ที่ต้องการติดตาม (คั่นด้วยจุลภาค เช่น ชลบุรี, เชียงใหม่ หรือ * สำหรับทุกสาขา) [*]: ").strip()
    if not branches:
        branches = "*"

    interval = input("ความถี่ในการตรวจเช็คข้อมูลใหม่ (วินาที) [300]: ").strip()
    if not interval:
        interval = "300"

    env_content = (
        f"# Telegram Configuration\n"
        f"TELEGRAM_BOT_TOKEN={token}\n"
        f"TELEGRAM_CHAT_ID={chat_id}\n\n"
        f"# Monitoring Configuration\n"
        f"CHECK_INTERVAL_SECONDS={interval}\n"
        f"ENABLE_OUTAGE_ALERT=true\n"
        f"ENABLE_QUALITY_ALERT=true\n\n"
        f"# Monitored branches (* for all)\n"
        f"MONITOR_BRANCHES={branches}\n\n"
        f"# Quality threshold\n"
        f"PH_MIN=6.5\n"
        f"PH_MAX=8.5\n"
        f"NTU_MAX=5.0\n"
        f"CL_MIN=0.2\n"
        f"CL_MAX=2.0\n"
    )

    with open(env_file, "w", encoding="utf-8") as f:
        f.write(env_content)

    print(f"\n✅ บันทึกการตั้งค่าลงใน {env_file} เรียบร้อยแล้ว!")
    print("คุณสามารถทดสอบการทำงานได้ด้วยคำสั่ง: python main.py test-telegram")


def cmd_run(mode: str = "all") -> None:
    """Runs the water alert system (monitor, bot, or both)."""
    db = Database()
    pwa = PWAClient()
    notifier = TelegramNotifier()

    if not notifier.is_configured:
        logger.warning("=" * 60)
        logger.warning("⚠️ คำเตือน: ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN ในไฟล์ .env")
        logger.warning("คุณสามารถรัน 'python main.py setup' เพื่อตั้งค่า หรือกรอกใน .env ได้เลย")
        logger.warning("=" * 60)

    monitor = WaterMonitorService(db=db, pwa=pwa, notifier=notifier)
    bot = TelegramBot(db=db, pwa=pwa, notifier=notifier)

    threads: list[threading.Thread] = []

    def handle_exit(sig, frame):
        logger.info("Shutdown signal received. Stopping services...")
        monitor.stop()
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    if mode in ("all", "monitor"):
        t_monitor = threading.Thread(target=monitor.run_loop, name="PWA-MonitorThread", daemon=True)
        t_monitor.start()
        threads.append(t_monitor)
        logger.info("Background PWA Monitor service started.")

    if mode in ("all", "bot"):
        if notifier.is_configured:
            t_bot = threading.Thread(target=bot.start_polling, name="PWA-BotThread", daemon=True)
            t_bot.start()
            threads.append(t_bot)
            logger.info("Interactive Telegram Bot polling started.")
        else:
            logger.warning("Telegram Bot polling skipped because Bot Token is not configured.")

    logger.info("System is active. Press Ctrl+C to terminate.")

    # Keep main thread alive
    try:
        while True:
            signal.pause()
    except (KeyboardInterrupt, SystemExit, AttributeError):
        import time
        while True:
            time.sleep(1)


def main() -> None:
    """CLI Argument parser."""
    parser = argparse.ArgumentParser(
        description="ระบบแจ้งเตือนน้ำประปาส่วนภูมิภาค (กปภ.) ไปยัง Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "command",
        choices=["run", "monitor", "bot", "test-fetch", "test-telegram", "setup"],
        nargs="?",
        default="run",
        help="คำสั่งที่ต้องการทำงาน (default: run)"
    )

    args = parser.parse_args()

    if args.command == "test-fetch":
        cmd_test_fetch()
    elif args.command == "test-telegram":
        cmd_test_telegram()
    elif args.command == "setup":
        cmd_setup()
    elif args.command == "monitor":
        cmd_run("monitor")
    elif args.command == "bot":
        cmd_run("bot")
    elif args.command == "run":
        cmd_run("all")


if __name__ == "__main__":
    main()
