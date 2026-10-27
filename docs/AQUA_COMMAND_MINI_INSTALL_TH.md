# ติดตั้ง AQUA COMMAND Mini v0.1 บนเครื่องทดสอบ Windows

ใช้ชุด Portable ในโฟลเดอร์ `aqua-command-mini` ของ repository นี้

1. [ดาวน์โหลด Windows x64 ZIP](../aqua-command-mini/releases/v0.1/AQUA_COMMAND_Mini_v0.1_windows_x64.zip?raw=true)
2. แตก ZIP ทั้งโฟลเดอร์ไว้ใน Documents ของเครื่องทดสอบที่อนุมัติและแยกจาก WinCC/PLC
3. เปิด `Start.cmd` หรือ `AQUA_COMMAND_Mini.exe` โดยเก็บ `_internal` อยู่ด้วย ไม่ต้องติดตั้ง Python หรือใช้สิทธิ์ Administrator
4. กด **ข้อมูลจำลองใหม่** ต้องเห็น ON/OFF ของ DEMO แล้วลอง export CSV และบันทึก dry-run

อ่าน [คู่มือติดตั้งทีละขั้น](../aqua-command-mini/INSTALL_TH.md) และ [คู่มือกำหนด Tag/Telegram TEST](../aqua-command-mini/README.md)

ค่าเริ่มต้น dry-run ไม่มีการส่ง Telegram หรือเชื่อม WinCC/PLC รุ่นนี้เป็น PoC ที่ยังต้องตรวจรับบน Windows 11 จริง ไม่พร้อม Production
