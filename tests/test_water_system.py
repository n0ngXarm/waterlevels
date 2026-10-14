"""Unit and integration tests for PWA Water Notification System."""

import tempfile
import unittest
from pathlib import Path
from src.database import Database
from src.pwa_client import PWAClient
from src.telegram_notifier import TelegramNotifier


class TestDatabase(unittest.TestCase):
    """Tests for SQLite database operations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_pwa.db"
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve_outage(self):
        outage = {
            "branch_name": "ทดสอบสาขาเมือง",
            "title": "ท่อแตกฉุกเฉิน",
            "cause": "รถบรรทุกชนท่อ",
            "affected_area": "ถนนเทศบาล 1",
            "start_date": "2026-10-14 10:00:00",
            "end_date": "2026-10-14 14:00:00",
            "working_status_name": "กำลังดำเนินการ",
            "link": "https://pwa.co.th/test_outage_1",
            "contact": "02-123-4567"
        }

        # First insert should succeed
        inserted = self.db.save_outage(outage, initial_status="กำลังดำเนินการ")
        self.assertTrue(inserted)

        # Duplicate insert with same link should be rejected by unique constraint
        duplicate = self.db.save_outage(outage, initial_status="กำลังดำเนินการ")
        self.assertFalse(duplicate)

        # Retrieve and verify
        key = self.db.generate_alert_key(outage)
        rec = self.db.get_outage(key)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["branch_name"], "ทดสอบสาขาเมือง")
        self.assertEqual(rec["last_status_alerted"], "กำลังดำเนินการ")

        # Update status
        self.db.update_outage_status(key, "ดำเนินการแล้วเสร็จ")
        updated = self.db.get_outage(key)
        self.assertEqual(updated["working_status_name"], "ดำเนินการแล้วเสร็จ")
        self.assertEqual(updated["last_status_alerted"], "ดำเนินการแล้วเสร็จ")

    def test_subscriber_management(self):
        chat_id = "12345678"
        self.db.add_or_update_subscriber(chat_id, username="somchai", first_name="Somchai", branches=["ชลบุรี"])

        sub = self.db.get_subscriber(chat_id)
        self.assertIsNotNone(sub)
        self.assertEqual(sub["branches"], ["ชลบุรี"])
        self.assertEqual(sub["username"], "somchai")

        # Update branches
        self.db.add_or_update_subscriber(chat_id, branches=["เชียงใหม่", "พัทยา"])
        sub_updated = self.db.get_subscriber(chat_id)
        self.assertEqual(sub_updated["branches"], ["เชียงใหม่", "พัทยา"])

        # Active subscribers list
        active_subs = self.db.get_active_subscribers()
        self.assertEqual(len(active_subs), 1)

        # Deactivate
        self.db.set_subscriber_active(chat_id, False)
        self.assertEqual(len(self.db.get_active_subscribers()), 0)


class TestPWAClient(unittest.TestCase):
    """Tests for PWA Client parsing and quality checking logic."""

    def setUp(self):
        self.client = PWAClient()

    def test_branch_lookup(self):
        found = self.client.find_branch("เชียงใหม่")
        self.assertIsNotNone(found)
        self.assertEqual(found.get("code"), "1004")

        found_code = self.client.find_branch("1012")
        self.assertIsNotNone(found_code)
        self.assertIn("ลำพูน", found_code.get("name"))

    def test_quality_standards(self):
        # 1. Normal station
        normal_st = {
            "plantname": "สถานี ก",
            "pH": "7.2",
            "NTU": "1.2",
            "Cl": "0.8",
            "pic": "pass"
        }
        is_normal, issues = self.client.check_station_quality(normal_st)
        self.assertTrue(is_normal)
        self.assertEqual(len(issues), 0)

        # 2. Acidic pH and high turbidity
        bad_st = {
            "plantname": "สถานี ข",
            "pH": "5.5",
            "NTU": "8.5",
            "Cl": "0.1",
            "pic": "fail"
        }
        is_normal, issues = self.client.check_station_quality(bad_st)
        self.assertFalse(is_normal)
        self.assertTrue(any("pH" in i for i in issues))
        self.assertTrue(any("ความขุ่น" in i for i in issues))
        self.assertTrue(any("คลอรีน" in i for i in issues))


class TestTelegramNotifier(unittest.TestCase):
    """Tests for Telegram message formatting."""

    def test_outage_formatting(self):
        outage = {
            "branch_name": "ภูเก็ต",
            "title": "ล้างบ่อตกตะกอน",
            "cause": "บำรุงรักษาประจำปี",
            "affected_area": "ต.กะทู้ ทั้งตำบล",
            "start_date": "2026-10-15 08:00:00",
            "end_date": "2026-10-15 16:00:00",
            "working_status_name": "กำลังดำเนินการ",
            "contact": "076-123456",
            "link": "https://pwa.co.th/poster.jpg"
        }

        html_msg = TelegramNotifier.format_outage_message(outage)
        self.assertIn("ภูเก็ต", html_msg)
        self.assertIn("ล้างบ่อตกตะกอน", html_msg)
        self.assertIn("ต.กะทู้", html_msg)
        self.assertIn("กำลังดำเนินการ", html_msg)

        # Test update message
        outage["working_status_name"] = "ดำเนินการแล้วเสร็จ"
        update_msg = TelegramNotifier.format_outage_message(outage, is_update=True)
        self.assertIn("ดำเนินการแล้วเสร็จ", update_msg)


if __name__ == "__main__":
    unittest.main()
