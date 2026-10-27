# AQUA COMMAND Mini v0.1 — ขอบเขตและแบบพัฒนา

โปรแกรม PoC สำหรับเครื่องทดสอบ Windows 11 แยกขาดจาก WinCC/PLC ของสถานีห้วยแก้ว
รับเฉพาะ TXT/CSV ในเครื่องที่เจ้าหน้าที่ได้รับอนุญาตส่งออกมา หรือข้อมูลจำลอง
ไม่ติดตั้งบน WinCC ไม่เชื่อม PLC ไม่ scan ไม่ใช้ WinCC REST ไม่แก้ configuration/runtime
ไม่มี live polling และไม่มีการส่งข้อมูลที่นำเข้าออกอินเทอร์เน็ต

## แบบที่เลือก

Python 3.12+ standard library + Tkinter: ทำงาน offline และทดสอบ parser/policy โดยไม่ต้องมีหน้าจอ
เทียบกับ Electron แล้วชุดโปรแกรมเล็กกว่าและมี dependency น้อยกว่า; เทียบกับ CLI อย่างเดียวแล้วเจ้าหน้าที่ดูตารางก่อน export ได้
แยก importer, policy, SQLite ledger, CSV exporter, Telegram TEST, CLI และ GUI
เก็บ source ใน workspace ใหม่เฉพาะงานนี้ ไม่แก้ checkout หรือระบบเดิม

## สัญญาข้อมูล

ไฟล์มีหัวตาราง tag,timestamp,value,quality หรือ aliases ที่ระบุใน README
รองรับ UTF-8/BOM และ UTF-16 LE/BE (BOM หรือรูปแบบ NUL ของหัวตาราง ASCII ชัดเจน)
delimiter tab/semicolon/comma; ambiguous/unsupported schema ปฏิเสธ ไม่เดา column
เครื่องหมาย DmTag/Tags/Tag และ metadata WinCC มีลำดับความสำคัญเหนือ runtime schema
Tag Configuration และ unknown format ไม่มีแถวสถานะหรือ notification candidate
เก็บ hash SHA-256 และอ่าน source เท่านั้น จำกัดขนาดและจำนวนแถว

## Policy

Tag ต้องอยู่ใน allowlist แบบตรงตัว แต่ละ Tag ระบุ mapping 0/1 -> ON/OFF ชัดเจน
ไม่แปลง 1.0, true, ค่าข้อความ หรือ quality code เป็น good โดยอัตโนมัติ
timestamp ต้องเป็น ISO 8601 พร้อม timezone; timestamp ไม่มี timezone ใช้ offset ที่ผู้รับผิดชอบกำหนดชัดเจนเท่านั้น
ต้องผ่าน freshness, future tolerance และ quality allowlist; ไม่ผ่านเป็น UNKNOWN/ERROR พร้อมเหตุผล
พิจารณา candidate เฉพาะ sample ใหม่สุดของ Tag; conflicting timestamp หรือ sample เรียงเวลาไม่ได้จะ block Tag นั้น
preview ไม่ consume ledger; ปุ่มบันทึก dry-run จึงบันทึก high-water mark และ state ลง SQLite
ซ้ำในไฟล์/ข้าม import, state เดิม, timestamp ย้อนกลับ ไม่สร้าง candidate ใหม่
ledger เสียหาย/ล็อกให้หยุด ไม่เริ่ม history ใหม่เงียบ ๆ

## Telegram และข้อมูลลับ

ค่าเริ่มต้น dry-run ไม่มี network call ทุกเส้นทางอ่านไฟล์และ export เป็น local เท่านั้น
Telegram รับข้อความ TEST จำลองคงที่ ไม่รับ argument เป็นค่าจากไฟล์
การส่งจริงต้อง Windows + enabled + machine ID อยู่ใน allowlist + approval reference + recipient hash ตรงกัน + ยืนยัน TEST ครั้งนั้น
token/chat ID มาจาก environment เท่านั้น ไม่มีช่องใส่ token ใน profile หรือ source
HTTPS ไป api.telegram.org เท่านั้น ไม่ตาม redirects ไม่ใช้ proxy อัตโนมัติ ไม่มี retry อัตโนมัติ
reserve ledger ก่อนส่ง ป้องกัน duplicate TEST ในวัน UTC เดียวกัน; response/timeout กำกวมไม่ retry
การตั้งค่าอนุมัติเป็นมาตรการดำเนินงานในเครื่อง ไม่ใช่ระบบ authorization ป้องกันผู้แก้ไฟล์ config ได้

## Export และการแจกจ่าย

UTF-8 BOM structured CSV พร้อมเหตุผลการ gate, decision, source hash และ DRY_RUN
escape spreadsheet formula; source คงเดิม ไม่ overwrite ไฟล์ที่มีอยู่
ส่งมอบ source, sample จำลอง, tests, README ภาษาไทย, launcher และ Windows build script
PyInstaller ต้อง build ใน Windows; หากไม่มี Windows จริงจะไม่อ้างว่า executable ผ่าน Windows 11 แล้ว
ไม่ถือว่าพร้อม Production และไม่ยืนยัน semantic ของ Tag/quality/timezone จนผู้รับผิดชอบตรวจสอบ
