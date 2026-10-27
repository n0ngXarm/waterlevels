# ผลทดสอบ AQUA COMMAND Mini v0.1

วันที่ 27 ตุลาคม 2026 (Asia/Bangkok) — PoC ไม่พร้อม Production

## สิ่งที่ส่งมอบและทดสอบได้จริง

มี source ที่รันได้ด้วย Python standard library, หน้าจอภาษาไทย, CLI, tests, ตัวอย่างจำลอง และ executable Windows x64 ทั้ง GUI/CLI สร้างด้วย CPython 3.13.13 สำหรับ Windows และ PyInstaller 6.22.3 ภายใน Wine 11.0 บน Linux

| การตรวจ | ผลจริง | หลักฐาน |
|---|---|---|
| ชุดทดสอบ source สุดท้ายบน Linux / Python 3.14.8 | **60 ผ่าน, 0 fail/error, 0 ข้าม** | `linux-release-tests.json`, `.txt` |
| ตรวจ source ใน repository ก่อน push พร้อมคู่มือติดตั้ง | **60 ผ่าน, 0 fail/error, 0 ข้าม** | `git-publish-tests.json`, `.txt` |
| ชุดทดสอบหลักบน Windows runtime ผ่าน Wine / Python 3.13.13 | **59 ผ่าน, 0 fail/error, 0 ข้าม** รวม Tk callbacks และ layout | `windows-wine-core-tests.json`, `.txt` |
| CLI หลังเพิ่มการบังคับ UTF-8 สำหรับ console/pipe | **9 ผ่าน** รวมกรณีภาษาไทยบน console ที่ตั้ง ASCII | `windows-wine-cli-release-tests.txt` |
| Build executable GUI และ CLI จาก source รุ่นสุดท้าย | สำเร็จทั้งคู่ เป็น Windows PE32+ x64 | `windows-wine-build-gui.txt`, `windows-wine-build-cli.txt` |
| ตรวจ executable bundle จริง | **7 checks ผ่าน** ด้วยข้อมูลจำลอง | `windows-wine-bundle-smoke.json`, `.txt` |
| ไฟล์แนบอ้างอิงเดิม | UTF-16 LE BOM → `tag_configuration`, process value rows = 0, bytes ต้นฉบับคงเดิม | `reference-classification.json` |
| การส่ง Telegram จริง | **ไม่ได้ดำเนินการ** | ไม่มี token หรือรายการอนุมัติรวมในชุดส่งมอบ |
| Windows 11 บนเครื่องจริง | **ยังไม่ได้ตรวจรับ** | ใช้ `docs/WINDOWS11_ACCEPTANCE.md` |

59 รายการในชุด Windows/Wine เป็น suite ก่อนเพิ่ม regression test UTF-8 อีก 1 รายการ หลังแก้ console ได้รัน CLI ทั้ง 9 รายการใหม่ จึงครอบคลุมกรณีทั้ง 60 รายการ โดยไม่ได้อ้างว่าเป็น full-suite run 60 รายการบน Windows 11

ในรอบตรวจแบบ socket guard บันทึก Python outbound connection attempts = 0 ทั้ง Linux และ Windows/Wine ส่วน HTTP boundary ของ Telegram ถูกแทนด้วยตัวรับจำลอง การตรวจนี้ไม่ใช่ packet capture หรือการรับรองระบบเครือข่าย โปรแกรมมี network entry point เฉพาะ Telegram TEST ที่ผ่าน gate เท่านั้น

## 7 checks ของ bundle

1. รัน CLI executable และอ่าน version 0.1.0 ได้
2. สร้างไฟล์จำลองเวลาปัจจุบันแล้ว preview เป็น ON/OFF ตาม explicit mapping
3. Export structured CSV จาก executable ได้
4. SHA-256 ของไฟล์ต้นฉบับก่อน/หลัง export เท่ากัน
5. บันทึก dry-run ครั้งแรกเป็น CANDIDATE ครั้งถัดไปเป็น DUPLICATE_HISTORY หลังเปิด process ใหม่
6. Telegram command ของ executable เป็น DRY_RUN และ network_attempted = false
7. เปิด GUI executable ได้และ process ทำงานอยู่ตลอดช่วงสังเกต 3 วินาที แล้วปิดเฉพาะ process ที่ทดสอบ

ข้อ 7 เป็นการตรวจ startup ของ bundle; การกดปุ่มและ layout ตรวจด้วย Tk widget/callback tests ของ source ทั้ง Linux และ Windows runtime ผ่าน Wine ไม่ใช่การตรวจรับโดยเจ้าหน้าที่บน Windows 11

## ขอบเขต tests ที่สำคัญ

- UTF-8/UTF-16 LE/BE, BOM และไม่มี BOM ที่ตรวจรูปแบบได้, Tab/semicolon/comma, ภาษาไทย และ quoted delimiter
- DmTag/Tags/Tag, metadata และ XML configuration มีลำดับเหนือ runtime header ไม่เกิดสถานะจาก config
- schema ไม่รู้จัก, column ซ้ำ, CSV quote ผิด, จำนวน column ผิด, binary, ขนาดไฟล์/field เกินกำหนด และ UNC path
- allowlist แยกตัวพิมพ์, mapping ปกติ/กลับด้าน, ปฏิเสธ 1.0/true/ON/NaN, quality ที่ไม่ได้อนุญาต
- timezone ต้องชัดเจน, timestamp ผิดรูป, freshness/future boundaries, newest quality ไม่ผ่านไม่ย้อนใช้ค่าเก่า
- conflicting samples, sample เรียงเวลาไม่ได้, ซ้ำในไฟล์, restart, สถานะเดิมเวลาใหม่, high-water mark, concurrent commits และ ledger เสียหาย
- ไม่ overwrite ไฟล์ที่มีอยู่, ป้องกันสูตร spreadsheet และคง raw source bytes
- Telegram dry-run ไม่ reserve/ไม่เรียก HTTP, gate ทุกชั้น, Windows requirement, explicit confirmation, recipient hash, fixed synthetic payload
- reserve ก่อนส่ง, duplicate หลัง restart, timeout ไม่ retry, error ไม่เผย token, ไม่ตาม redirect และไม่เปลี่ยนผู้รับหลังตรวจอนุมัติ
- หน้าจอเปิด demo/export/config ได้ ปุ่ม export มองเห็นในขนาดเริ่มต้น และปุ่ม TEST ไม่หลุดจากหน้าต่างขนาดต่ำสุด

ภาพ `gui-synthetic-linux.png` เป็นภาพหน้าจอ Tk ที่รันจริงบนจอจำลอง Linux ใช้เฉพาะ DEMO ไม่ใช่ภาพ Windows 11 และไม่ใช่ข้อมูลสถานี

## สิ่งที่ยังต้องทำบนเครื่องที่อนุมัติ

1. ผู้ทดสอบตรวจ checksum และทำรายการตรวจรับ Windows 11 จริง รวมภาษาไทย, DPI, policy การรัน executable และการเปิดไฟล์จากดิสก์ในเครื่อง
2. ผู้รับผิดชอบตรวจความหมาย Tag, mapping, timestamp/timezone และ quality ก่อนตั้ง allowlist ของไฟล์ที่อนุญาต
3. ถ้าอนุมัติให้ทดสอบ Telegram จึงตั้ง environment, machine/recipient allowlist และเลขอนุมัติตาม README แล้วส่งเฉพาะข้อความ TEST จำลอง

ไม่มีการติดตั้งบน WinCC, เชื่อม PLC, scan OT, ใช้ WinCC REST, เปลี่ยน configuration/runtime หรือ polling live ระหว่างงานนี้ ไฟล์ต้นฉบับของสถานีและข้อมูลลับไม่ได้รวมใน ZIP
