# 💧 PWA AQUA COMMAND & TELEGRAM ALERT SYSTEM
### ระบบศูนย์ควบคุมการจ่ายน้ำประปาส่วนภูมิภาค (Web Dashboard) & แจ้งเตือนผ่าน Telegram แบบ 24/7

ระบบรวมศูนย์สั่งการและเฝ้าระวังน้ำประปาอัจฉริยะ ผสานพลังระหว่าง **AQUA COMMAND CENTER** (เว็บแดชบอร์ดศูนย์ควบคุมภาษาไทย) และ **PWA Live Alert Engine** (ระบบดึงข้อมูลสดจากการประปาส่วนภูมิภาค ส่งเข้า Telegram แบบ Real-time)

---

## 🏗️ สถาปัตยกรรมระบบแบบผสมผสาน (Integrated Architecture)

```text
       การประปาส่วนภูมิภาค (กปภ. / PWA Live APIs)
       ├── ข่าวหยุดจ่ายน้ำ / ท่อแตกฉุกเฉิน (api-mg.pwa.co.th)
       └── เซนเซอร์ตรวจวัดคุณภาพน้ำ RTU 666 สถานี (dmamas.pwa.co.th)
                         │
                         ▼
             [ PWA Live Agent & Bridge ]
        (สแครปข้อมูลสด, คัดกรอง, ตรวจจับสถานะซ่อมเสร็จ)
            │                               │
            │ (REST /api/telemetry)         │ (Telegram Bot API)
            ▼                               ▼
 [ AQUA COMMAND CENTER ]          [ TELEGRAM BOT ]
    🌐 Web Dashboard                 📱 @nongwater_agentbot
    พอร์ต 8787 (http://localhost:8787)   แจ้งเตือนท่อแตก/ซ่อมเสร็จทันที
    - แผนผังเครือข่ายสถานี 12 เขต         ส่งพร้อมภาพโปสเตอร์ประกาศทางการ
    - ค่าความดัน, ระดับถัง, Flow, NTU, Cl   ปุ่มกดโต้ตอบ /latest, /quality, /status
    - ตาราง Incident Response & Ack      ระบบ Anti-flood & Dedup 100%
```

---

## 🌟 จุดเด่นของระบบ (Key Highlights)

1. **🌐 ศูนย์ควบคุม AQUA COMMAND CENTER (พอร์ต 8787)**
   - เข้าใช้งานได้ผ่านเบราว์เซอร์ที่: **`http://localhost:8787`**
   - **Overview & KPI**: แสดงสถานะออนไลน์, แรงดันเฉลี่ย, ปริมาณน้ำสำรอง, คุณภาพน้ำ, และกราฟ Telemetry ย้อนหลัง 24 ชั่วโมง
   - **Network Map**: แผนผังจำลองสถานีหลัก กปภ. ทั่วประเทศ (เชียงใหม่, ลำพูน, ชลบุรี, ระยอง, ขอนแก่น, โคราช, สงขลา ฯลฯ)
   - **Live Ingest**: รับข้อมูลความขุ่น (NTU), คลอรีนคงเหลือ (Cl) สดจากเซนเซอร์ กปภ. แบบเรียลไทม์
   - **Incident Management**: บันทึกเหตุการณ์ท่อแตก/หยุดจ่ายน้ำ พร้อมระบบกดรับทราบ (Acknowledge) และ Export CSV

2. **🤖 ระบบแจ้งเตือนและบอทโต้ตอบบน Telegram (`@nongwater_agentbot`)**
   - ส่งภาพประกาศและรายละเอียดทันทีเมื่อ กปภ. ออกประกาศใหม่
   - **แจ้งเตือนความคืบหน้า**: เมื่อซ่อมท่อเสร็จสิ้น ระบบจะแจ้งเตือนทันทีว่า *"น้ำเริ่มกลับมาไหลปกติแล้ว"*
   - **คำสั่งโต้ตอบผ่านแชท**:
     - `/start` : เมนูหลักพร้อมปุ่มกดเปิด Web Dashboard ทันที
     - `/latest [สาขา]` : ดูประกาศหยุดจ่ายน้ำล่าสุด
     - `/branch <สาขา>` : ค้นหาข้อมูลสาขา กปภ.
     - `/quality [สถานี]` : ตรวจสอบคุณภาพน้ำประปา RTU
     - `/subscribe <สาขา>` : รับแจ้งเตือนเฉพาะพื้นที่ที่ต้องการ
     - `/status` : ดูสถานะการทำงานของระบบ

3. **🛡️ 24/7 Production Docker Setup**
   - รันผ่าน Docker Compose แยก 2 บริการอิสระ (`aqua-command` + `pwa-water-alert`)
   - นโยบาย `restart: always` สตาร์ตตัวเองอัตโนมัติตลอดเวลาแม้เซิร์ฟเวอร์รีบูต
   - มีระบบ Baseline Sync และ Anti-flood ป้องกันการส่งข้อความสแปมรัว

---

## 🚀 วิธีการใช้งาน (Usage Guide)

### 1. เข้าดูหน้าเว็บแดชบอร์ด
เปิดเว็บเบราว์เซอร์ไปที่:
👉 **[http://localhost:8787](http://localhost:8787)** *(หรือ `http://<IP-เครื่อง>:8787`)*

### 2. ตรวจสอบสถานะคอนเทนเนอร์
```bash
docker compose ps
```

### 3. ดู Log การทำงานแบบเรียลไทม์
```bash
docker compose logs -f
```

### 4. สั่งหยุด / สตาร์ตระบบ
```bash
# หยุดการทำงาน
docker compose stop

# เริ่มการทำงานใหม่
docker compose up -d
```

---

## 📁 โครงสร้างโปรเจกต์

```
project_water/
├── docker-compose.yml       # ตัวควบคุม Multi-Container (Web Dashboard + Python Agent)
├── Dockerfile               # Dockerfile สำหรับ PWA Python Agent
├── .env                     # ไฟล์เก็บ Token, Chat ID และ Admin API Key
├── data/
│   ├── pwa_alerts.db        # ฐานข้อมูล SQLite (ประวัติและสมาชิก Telegram)
│   └── branches.json        # ฐานข้อมูล 235 สาขา กปภ.
├── src/
│   ├── aqua_bridge.py       # สะพานเชื่อมข้อมูลสด กปภ. เข้าสู่ Aqua Command Web API
│   ├── monitor_service.py   # Background Worker เฝ้าระวังและส่งแจ้งเตือน
│   ├── telegram_bot.py      # Interactive Telegram Bot
│   ├── telegram_notifier.py # ตัวจัดรูปแบบข้อความ HTML/ภาพโปสเตอร์
│   ├── pwa_client.py        # Client สแครป API ข่าวหยุดจ่ายน้ำ และ RTU คุณภาพน้ำ
│   └── database.py          # SQLite Manager
└── aqua-command/            # Web Dashboard Application (Node.js)
    ├── server.mjs           # HTTP/SSE Server & REST API
    ├── rules.mjs            # กฎเกณฑ์เตือนภัยด้านวิศวกรรมน้ำ
    ├── public/              # ไฟล์เว็บ (HTML, CSS, JS Responsive Thai UI)
    ├── storage/             # จัดเก็บ state.json สำหรับหน้าเว็บ
    └── Dockerfile           # Dockerfile สำหรับ Web Dashboard
```
