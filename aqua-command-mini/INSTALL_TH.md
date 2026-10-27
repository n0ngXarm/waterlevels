# วิธีติดตั้ง AQUA COMMAND Mini v0.1 ให้เพื่อนทดสอบ

รุ่นนี้เป็น **Portable สำหรับ Windows 11 x64** แตก ZIP แล้วเปิดได้ ไม่ต้องติดตั้ง Python, Docker หรือใช้สิทธิ์ Administrator ใช้เฉพาะเครื่องทดสอบที่ได้รับอนุมัติและแยกจาก WinCC/PLC

## 1. ดาวน์โหลดชุดโปรแกรม

เปิด [ดาวน์โหลด AQUA COMMAND Mini สำหรับ Windows x64](https://github.com/n0ngXarm/waterlevels/raw/refs/heads/codex/aqua-command-mini-v0.1/aqua-command-mini/releases/v0.1/AQUA_COMMAND_Mini_v0.1_windows_x64.zip)

ไฟล์ที่ได้ชื่อ `AQUA_COMMAND_Mini_v0.1_windows_x64.zip` ภายในมี executable พร้อมส่วนประกอบและคู่มือครบ ผู้ส่งสามารถดาวน์โหลด ZIP นี้แล้วส่งให้เพื่อนได้ทั้งไฟล์

ตรวจความถูกต้องได้ด้วย [SHA256SUMS.txt](https://github.com/n0ngXarm/waterlevels/blob/codex/aqua-command-mini-v0.1/aqua-command-mini/releases/v0.1/SHA256SUMS.txt) หากต้องการตรวจบน Windows ให้เปิด PowerShell ในโฟลเดอร์ที่ดาวน์โหลดแล้วใช้:

```powershell
Get-FileHash .\AQUA_COMMAND_Mini_v0.1_windows_x64.zip -Algorithm SHA256
```

เทียบผลกับบรรทัดชื่อไฟล์เดียวกันใน SHA256SUMS.txt โดยไม่สนตัวพิมพ์ใหญ่/เล็ก

## 2. แตก ZIP และเปิดโปรแกรม

1. คลิกขวา ZIP → **Extract All / แยกทั้งหมด**
2. เลือกพื้นที่ของผู้ใช้ เช่น `Documents\AQUA-Mini-Test`
3. เปิดโฟลเดอร์ที่แตกแล้ว ภายในต้องเห็น `Start.cmd`, `AQUA_COMMAND_Mini.exe` และโฟลเดอร์ `_internal`
4. ดับเบิลคลิก **Start.cmd** หรือ **AQUA_COMMAND_Mini.exe**
5. ต้องเห็นหน้าต่าง AQUA COMMAND Mini v0.1 พร้อมคำว่า **PoC / DRY-RUN**

เปิดจากโฟลเดอร์ที่แตกแล้ว และเก็บ `_internal` อยู่กับ executable ตลอด ห้ามนำไปติดตั้งบนเครื่อง WinCC หรือเชื่อมต่อเครือข่าย OT

หาก Windows แจ้งเตือนหรือองค์กรบล็อก executable ซึ่งยังไม่ลงลายเซ็น ให้ผู้ดูแลตรวจ checksum และอนุมัติตามนโยบายหน่วยงาน

## 3. ทดสอบครั้งแรกด้วยข้อมูลจำลอง

1. กด **ข้อมูลจำลองใหม่** ควรเห็น `DEMO_PUMP_01 = ON` และ `DEMO_VALVE_01 = OFF`
2. กด **Export structured CSV** ตั้งชื่อใหม่ เช่น `demo-result-01.csv` แล้วตรวจว่ามี state, reason และ `DRY_RUN`
3. กด **บันทึกประวัติ dry-run** แล้วกด **ตรวจเกณฑ์อีกครั้ง** ต้องพบรายการซ้ำกับประวัติ ไม่มีการส่ง Telegram
4. กด **เลือก TXT / CSV** แล้วเลือก `examples\tag_configuration_synthetic.txt` ต้องขึ้น **Tag Configuration เท่านั้น** ไม่มี ON/OFF และไม่เปิดให้ export สถานะ
5. ปิดอินเทอร์เน็ตแล้วลองข้อมูลจำลองและ export ซ้ำได้

ใช้ปุ่ม **ข้อมูลจำลองใหม่** เพื่อให้ timestamp เป็นเวลาปัจจุบัน ไฟล์ runtime ตัวอย่างที่บันทึกเวลาคงที่อาจแสดง STALE ตามกติกา freshness

## 4. ใช้ไฟล์ที่เจ้าหน้าที่อนุญาตส่งออก

หลังผ่านข้อมูลจำลอง ให้ผู้รับผิดชอบยืนยันรูปแบบไฟล์, Tag allowlist, mapping 0/1, timezone, freshness และ quality ก่อนตั้งโปรไฟล์ตาม [README ภาษาไทย](README.md)

คัดลอกไฟล์ที่อนุญาตลงดิสก์ในเครื่องแล้วเลือกผ่านโปรแกรม ไม่อ่านผ่าน UNC share และไม่เชื่อม WinCC/PLC โดยตรง ไฟล์ `Export all(1).txt` ที่ขึ้นต้น DmTag/Tags/Tag เป็น configuration จึงไม่ใช้สรุปสถานะจริง

ค่าที่ไม่ผ่านเกณฑ์เป็น UNKNOWN/ERROR ให้ดูเหตุผลในตาราง ไม่แก้ค่าให้ดูเหมือน ON/OFF เพื่อให้ผ่านการทดสอบ

## 5. Telegram TEST

ค่าเริ่มต้นเป็น dry-run **ไม่ต้องใส่ token เพื่อทดสอบหน้าจอและ CSV**

การส่งจริงต้องได้รับอนุมัติเครื่องทดสอบ ผู้รับ และการออกอินเทอร์เน็ตก่อน จากนั้นกำหนด Machine ID, recipient hash และเลขอ้างอิงอนุมัติในโปรไฟล์ พร้อมตั้ง token/chat ID ผ่าน environment ตาม README และยืนยัน TEST ครั้งนั้น โปรแกรมส่งได้เฉพาะข้อความจำลองคงที่ ไม่มีข้อมูลจากไฟล์ในข้อความ

ห้ามใส่ token ใน Git, JSON profile, ZIP หรือภาพหน้าจอ

## 6. ส่งผลทดสอบกลับ

บันทึก Windows version, ภาพหน้าจอ DEMO, ผล export จำลอง และข้อความผิดพลาดถ้ามี ใช้ [แบบตรวจรับ Windows 11](docs/WINDOWS11_ACCEPTANCE.md) ประกอบ ส่งกลับเฉพาะข้อมูลจำลองและผลที่ได้รับอนุญาต

รุ่นนี้ผ่าน source tests และตรวจ executable ผ่าน Wine บน Linux **ยังไม่ได้ตรวจรับบน Windows 11 จริง และไม่พร้อม Production** ดู [หลักฐานทดสอบ](evidence/TEST_REPORT_TH.md)

## สำหรับผู้พัฒนาที่ต้องการใช้ Git

```powershell
git clone --branch codex/aqua-command-mini-v0.1 --single-branch https://github.com/n0ngXarm/waterlevels.git
cd waterlevels\aqua-command-mini
py -3.13 -m aqua_command gui
```

วิธีนี้ต้องมี Git และ Python 3.13 x64 พร้อม Tcl/Tk ส่วนผู้ทดสอบทั่วไปใช้ Windows ZIP ตามขั้นตอน 1–3 ได้เลย
