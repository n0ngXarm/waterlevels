# Data Provenance, Verification, and Licensing Documentation
## AQUA COMMAND — Chiang Mai Water Operations Command Center

เอกสารระบุแหล่งที่มา สิทธิ์การใช้งาน และกระบวนการตรวจสอบความถูกต้องของข้อมูลภูมิศาสตร์และข้อมูลสถานีประปา

---

### 1. Geographic Information System (GIS) Data

#### 1.1 Chiang Mai Boundary & District Boundaries
- **Source:** OpenGISData-Thailand (`OpenGISData-Thailand/geodata-administrative-thailand`)
- **Origin Authority:** กรมการปกครอง กระทรวงมหาดไทย (Department of Provincial Administration - DOPA) ร่วมกับ สำนักงานพัฒนารัฐบาลดิจิทัล (องค์การมหาชน) (สพร. / DGA) ผ่านโครงการ Open Government Data of Thailand
- **License:** Open Government License / MIT Permissive Open Data License
- **Coverage:** ครอบคลุม 25 อำเภอในจังหวัดเชียงใหม่:
  1. เมืองเชียงใหม่ (`5001`)
  2. จอมทอง (`5002`)
  3. แม่แจ่ม (`5003`)
  4. เชียงดาว (`5004`)
  5. ดอยสะเก็ด (`5005`)
  6. แม่แตง (`5006`)
  7. แม่ริม (`5007`)
  8. สะเมิง (`5008`)
  9. ฝาง (`5009`)
  10. แม่อาย (`5010`)
  11. พร้าว (`5011`)
  12. สันป่าตอง (`5012`)
  13. สันกำแพง (`5013`)
  14. สันทราย (`5014`)
  15. หางดง (`5015`)
  16. ฮอด (`5016`)
  17. ดอยเต่า (`5017`)
  18. อมก๋อย (`5018`)
  19. สารภี (`5019`)
  20. เวียงแหง (`5020`)
  21. ไชยปราการ (`5021`)
  22. แม่วาง (`5022`)
  23. แม่ออน (`5023`)
  24. ดอยหล่อ (`5024`)
  25. กัลยาณิวัฒนา (`5025`)
- **Integrity Verification:** ตรวจสอบ Bounding Box ความสอดคล้องพิกัด WGS84:
  - Longitude: `98.08319` ถึง `99.59023`
  - Latitude: `17.24939` ถึง `20.15280`

---

### 2. Station Coordinates & Asset Location Verification

#### 2.1 Scope Delineation (ขอบเขตอำนาจหน้าที่ของสาขา)
- **PWA Branch 1004 (กปภ. สาขาเชียงใหม่ (ชั้นพิเศษ)):**
  - เป็นหน่วยงานบริการน้ำประปาในเขตเศรษฐกิจและอำเภอหลัก ได้แก่ เมืองเชียงใหม่, สันทราย, หางดง, สารภี
  - สถานีผลิตน้ำหลัก: ป่าตัน (`CM-01`), อุโมงค์ (`CM-02`), แม่กวง (`CM-03`), แม่แฝก (`CM-04`), หางดง (`CM-07`), สารภี (`CM-08`)
- **Autonomous Regional Branches (สาขาอิสระอื่นในจังหวัด):**
  - สาขาแม่ริม (`1005`), สาขาสันกำแพง (`1006`), สาขาแม่แตง (`1007`), สาขาจอมทอง (`1008`), สาขาฝาง (`1009`), สาขาฮอด (`1030`)
  - ถูกกำหนดสถานะใน Station Registry เป็น `OUT_OF_PILOT_SCOPE` เพื่อป้องกันการดึงหรือนำเสนอข้อมูลโดยไม่ได้รับอนุญาต

#### 2.2 Verification Methodology
1. **PWA Published Official Directory:** อ้างอิงประกาศสถานที่ตั้งและสำนักงานสาขาจากเว็บไซต์การประปาส่วนภูมิภาค เขต 9
2. **Satellite / Geolocation Cross-check:** ยืนยันตำแหน่งจุดสูบน้ำดิบและโรงกรองน้ำด้วยภาพถ่ายดาวเทียมเพื่อป้องกันการสมมติพิกัดเท็จ

---

### 3. Data Classification Policy (นโยบายการจัดหมวดหมู่ข้อมูล)

| Classification | Definition | Example in System |
|---|---|---|
| `AUTHORIZED_FIELD_TELEMETRY` | ข้อมูลจริงจากเซนเซอร์/PLC ที่รับผ่าน Edge Collector ที่มีกุญแจยืนยันตัวตน | ข้อมูลแรงดันและอัตราการไหลจากสถานีป่าตันที่ส่งผ่าน Zone A Edge Gateway |
| `PUBLIC_EXTERNAL` | ข้อมูลที่เปิดเผยต่อสาธารณะโดยหน่วยงานรัฐ | ข้อมูลระดับน้ำเขื่อนจากกรมชลประทาน, ข้อมูลประกาศหยุดจ่ายน้ำจากเว็บ กปภ. |
| `DEMO` | ข้อมูลที่สร้างขึ้นจำลองเพื่อการพัฒนาและทดสอบระบบ | ข้อมูลในโหมด DEMO_MODE=true หรือการกดจำลองเหตุการณ์ |

**ข้อกำหนดทางความปลอดภัย:** ห้ามแสดงข้อมูลหมวด `DEMO` หรือ `PUBLIC_EXTERNAL` โดยติดป้ายว่าเป็น `AUTHORIZED_FIELD_TELEMETRY` โดยเด็ดขาด
