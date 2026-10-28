# AQUA COMMAND Desktop 0.8.0 — G2 Option B preview

โปรแกรม Desktop แบบอ่านอย่างเดียวบน Fedora 44 ใช้หน้าต่าง GTK4 โดยตรง ไม่เปิดเว็บไซต์หรือเบราว์เซอร์

## ขอบเขต G2 ที่สร้างแล้ว

Native GTK Desktop แบบ B มี7หน้า: Overview, Network Topology, SCADA Sources, Monitored Items, Live Monitoring, Gateway & Delivery และ Alerts & Audit ใช้ข้อมูลจากระบบเดิม ไม่มี Backend/API/DB/IPC/consent implementation ใหม่

- Network แสดง configured loopback endpoints ของ Agent/Gateway/Central ที่อยู่เครื่องเดียว ไม่ใช่ NIC IP หรือทะเบียนคอมพิวเตอร์ใน LAN ไม่ใส่ Hostname ปลอมและไม่มีการสแกน
- Counters แยก snapshots / local pending events / Gateway pending events / Central accepted events พร้อม coverage และสถานะ cached ไม่ใช้ Delivered แทน Telegram
- Live Monitoring แยก RAW, normalized state, quality code, freshness และ observation time กรอง/ค้นหาเฉพาะหน้าจอได้ คลิก Tag เพื่อดูรายละเอียด/Read error
- พักการแสดงผลได้โดยการเก็บ/ส่งตามสิทธิ์ยังเดินต่อ แสดง CACHED ชัดเจนเมื่อพัก ภาพจะไม่คง CURRENT หาก Backend หยุดรายงาน
- Sources/Items แสดง capability และชื่อที่ตั้งค่าไว้ ปุ่ม OPC Browse, one-item test, Add/Disable rule, hot reload, per-event queue query และ audit export ยังปิดพร้อมเหตุผล เพราะต้องอนุมัติ G3–G5/backend scope แยก
- WinCC Runtime จริงยังไม่มี connector ที่ผ่าน LAB รุ่นนี้ไม่เปิด OPC UA ไม่แก้ WinCC และไม่อ้างว่าอ่าน Runtime ได้จากการอ่าน CSV

## พฤติกรรมเมื่อเปิดโปรแกรม

- ไม่เริ่มส่วนเก็บข้อมูล ไม่สร้างคิว ไม่อ่านต้นทาง ไม่ตรวจ Internet และไม่ส่งเอง
- แสดงแหล่งข้อมูล ที่เก็บข้อมูล และเครื่องรับที่เลือกอย่างชัดเจน
- เริ่มต้นที่ **WinCC Runtime จริง: ยังไม่พร้อม** ไม่มีช่องทางอ่าน Runtime ที่ตกลงและอนุญาตแล้ว จึงไม่สลับไปใช้ LAB หรือ CSV เอง
- ผู้ใช้ระบุว่าเครื่อง WinCC ยังไม่ได้เปิด OPC UA รุ่นนี้จะไม่เปิดบริการ ไม่แก้โครงการ ไม่ติดตั้งสคริปต์ และไม่แก้ WinCC/PLC ให้เอง

## วิธีใช้งานและสิทธิ์

1. เลือก **ตั้งค่าแหล่งข้อมูล** บันทึกอย่างเดียว ยังไม่เริ่มงาน มีทางเลือก WinCC Runtime (ยังไม่พร้อม), Runtime CSV ที่ส่งออกไว้แล้ว หรือ LAB ที่เลือกเอง
2. กด **เริ่มอ่านทุก 5 วินาที** ตรวจต้นทาง รายชื่อ Tag ช่วงเวลา และที่เก็บ แล้วอนุญาต การอ่านต่อเนื่องจนหยุด ไม่ถามทุก 5 วินาที
3. ข้อมูลเก็บในเครื่องก่อน การส่งยังปิด ต้องกด **อนุญาตส่งข้อมูล** และตรวจเครื่องรับ/ปลายทางแยกต่างหาก
4. ช่อง **ไม่ถามซ้ำ** จำเฉพาะแหล่งข้อมูลหรือปลายทางชุดนั้น ยังต้องกดเริ่มเองทุกครั้งที่เปิดโปรแกรม เปลี่ยนขอบเขตจะถามใหม่ ไม่มีกล่องเลือกที่ถูกติ๊กไว้ล่วงหน้า
5. หยุดอ่าน หยุดส่ง หรือ **หยุดงานทั้งหมด** ได้ กด **ถอนสิทธิ์ทั้งหมดและหยุดงาน** เพื่อล้างสิทธิ์ที่จำไว้ คิวเดิมยังอยู่

งานที่ส่งออกไปแล้วก่อนหยุดอาจตอบรับกลับมาได้ โปรแกรมรอให้งานที่เริ่มไปแล้วจบ แต่ไม่เริ่มคำขอส่งถัดไปหลังถอนสิทธิ์ การเปิดโปรแกรมครั้งถัดไปยังคงหยุดอยู่ แม้จำสิทธิ์ไว้

## ข้อมูลจริงกับสิ่งที่ทดสอบ

**ยังอ่าน WinCC Runtime โดยตรงไม่ได้** ต้องตกลงช่องทางอ่านที่ WinCC รองรับกับเจ้าของระบบและทดสอบใน LAB ก่อน ห้ามเปิด OPC UA หรือแก้ WinCC Production อัตโนมัติ ไฟล์ Tag Management เช่น Export all.txt เป็นรายชื่อ/การตั้งค่า ไม่ใช่ค่าปั๊มปัจจุบัน

CSV เป็นทางเลือกสำหรับไฟล์ค่าปัจจุบันที่ระบบอื่นส่งออกไว้แล้ว อ่านเฉพาะชื่อ Tag ที่ผู้ใช้เลือก ไม่แก้ไฟล์ต้นทาง ไม่แปลงข้อมูลเสีย/เก่าเป็น OFF ต้องยืนยันความหมาย 0/1 และ Quality ก่อนแสดงสถานะปั๊ม

LAB ใช้เครื่องส่ง เครื่องรับ และปลายทางทดสอบในเครื่องเดียว (loopback) ไม่มี Internet จริง Telegram เป็น dry-run ตัวเลขปลายทางยืนยันแล้วจึงไม่ใช่การส่ง Telegram จริง หน้าต่างยังตั้งเครื่องรับข้าม LAN ไม่ได้ ไม่มีการสแกนเครื่องอื่น

คิวรองรับ ACK/retry/idempotency และเปิดใหม่ต่อจากข้อมูลเดิมได้ แต่จะไม่อ่านหรือส่งต่อเองก่อนอนุญาตในแต่ละครั้งที่เริ่มงาน เปลี่ยนแหล่งข้อมูลจะหยุด session เดิมและเก็บโปรไฟล์/คิวเดิมไว้ เปิดแหล่งเดิมเพื่อทำงานต่อ

## ติดตั้ง

```sh
sudo dnf install ./aqua-command-desktop-0.8.0-1.fc44.noarch.rpm
```

เปิด **AQUA COMMAND** จากเมนูแอป ต้องมี Python3, PyGObject, GTK4 และ Node22.13+ ตาม dependency ใน RPM ไม่มีบริการเปิดอัตโนมัติ ไม่มี install scriptlets ไม่มี firewall/NAT/bridge/Internet sharing

การทดสอบนักพัฒนาใช้ payload ของ RPM ที่แตกลงโฟลเดอร์ส่วนตัวและเปิด launcher จริง ไม่ได้ติดตั้งทั่วระบบด้วย DNF ในเครื่องนี้ RPM ยังไม่ได้ลงลายเซ็น Windows .exe, WinCC Runtime จริง, LAN ข้ามสองเครื่อง, Telegram จริง และไฟดับจริง ยังไม่ผ่านการตรวจรับ

## ข้อกำหนดไฟล์ CSV เดิม

อ่านไฟล์ runtime_YYYYMMDD.csv ที่มีหัว timestamp_local;tag_name;raw_value;quality_code;read_error และ complete frame ตรงรายชื่อที่ตั้งค่าไว้ Source ปัจจุบันยังไม่ใช่ตัวเลือก subset จาก CSV ที่มี Tag อื่นปน ห้ามเข้าใจว่าการกรองตารางเป็นการเปลี่ยนรายการที่ collector อ่าน

## ตรวจสอบ / ถอนการติดตั้ง

```sh
npm test --prefix backend
python3 -B -m unittest discover -s desktop/tests -v
python3 -B desktop/ui_test.py  # ต้องมี native GTK display
bash packaging/build-rpm.sh /absolute/owned-build-directory
sudo dnf remove aqua-command-desktop
```

ถอนแพ็กเกจจะไม่ลบคิวส่วนตัว เก็บข้อมูลไว้จนกว่าจะตรวจสอบการส่งครบแล้ว [รายละเอียดการทดสอบและข้อจำกัด](VERIFICATION.md)

CSV ที่กดบันทึกเป็นข้อมูลล่าสุดที่ยังเก็บอยู่ จำกัด 2,000 events / 250 KB ของ payload ต่อครั้ง มีข้อความแจ้งเมื่อได้เพียงบางส่วน Source เก็บประวัติ ACK แล้วสูงสุด 2,000 events และ pending 10,000 events เมื่อ pending เต็มจะหยุดเก็บพร้อมแจ้งข้อผิดพลาดโดยไม่ลบข้อมูลที่ยังไม่ ACK ฐานข้อมูลมีเพดาน 64 MiB; ไม่ใช่คลังข้อมูลไม่จำกัด
