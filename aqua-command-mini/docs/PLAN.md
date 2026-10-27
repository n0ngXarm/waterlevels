# AQUA COMMAND Mini Implementation Plan

**Goal:** โปรแกรม Windows PoC ที่อ่านไฟล์อย่างปลอดภัย แสดง ON/OFF ตาม policy และส่งเฉพาะ Telegram TEST ที่ผ่านการอนุมัติ

**Architecture:** Python standard library แยกหน้าจอออกจาก importer/policy/ledger/export/notification ทั้งหมด ขอบเขตตาม DESIGN.md ที่มาจากคำสั่งผู้ใช้

**Tech Stack:** Python 3.12+, Tkinter, unittest, SQLite, urllib, PyInstaller สำหรับ Windows

**Spec:** DESIGN.md

## Tasks และ acceptance checks

- [x] 1. เขียน tests importer/config ก่อน implementation แล้วรันให้เห็น failure: `python -m unittest tests.test_importer tests.test_config -v`
  สร้าง `aqua_command/config.py`, `importer.py`; interface `load_profile(path=None)`, `import_bytes(data, name, source_path=None)`, `import_file(path)`
  ครอบคลุม BOM/UTF16 LE/BE, delimiters ทั้งสาม, metadata ก่อน runtime, duplicate columns, malformed CSV, binary/oversize, JSON duplicate/invalid allowlist
- [x] 2. เขียน tests gating/ledger/export ก่อน implementation: `python -m unittest tests.test_policy tests.test_ledger tests.test_exporter -v`
  สร้าง `policy.py`, `ledger.py`, `exporter.py`; `evaluate(imported, profile, now)`, `Ledger.plan(rows, policy_id)`, `Ledger.commit_dry_run(rows, policy_id)`, `export_csv(imported, rows, target)`
  ตรวจ ON/OFF เฉพาะ explicit mapping, UNKNOWN ทุก gate, latest/conflict/duplicate/high-water mark, transaction/concurrent dry-run, source hash/ไม่ overwrite/formula escape
- [x] 3. เขียน Telegram tests ด้วย transport จำลองก่อน implementation: `python -m unittest tests.test_telegram -v`
  สร้าง `telegram_test.py`; `run_test(profile, ledger, send=False, confirmed=False)`
  ตรวจ dry-run ไม่มี network, gates ทุกชั้น, fixed synthetic payload, redirect refusal, timeout sanitization และ durable reservation ก่อนส่ง
- [x] 4. CLI และ GUI: `python -m unittest tests.test_cli -v`
  สร้าง `cli.py`, `gui.py`, `__main__.py`, `launcher.py`; commands `demo`, `preview`, `dry-run`, `telegram-test`, `machine-id`, `gui`
  อ่านไฟล์ครั้งเดียวเมื่อเจ้าหน้าที่เลือก preview ไม่เปลี่ยน history; demo สร้าง timestamp ปัจจุบันตามเวลาจำลองใน tests
- [x] 5. ส่งมอบ: README ภาษาไทย, samples จำลองหลาย encoding, Start.cmd, build_windows.ps1 และ Windows workflow
  รัน `python -m unittest discover -v`, CLI demo -> preview -> export -> dry-run ซ้ำ, ตรวจไฟล์แนบจริงเป็น configuration โดยบันทึกผลสรุปเท่านั้น
  บันทึกหลักฐานทดสอบและข้อจำกัด Windows/GUI/Telegram จริง จากนั้นจัด ZIP เฉพาะ source/sample/evidence ไม่มี secret และไม่มีไฟล์จริงของสถานี
