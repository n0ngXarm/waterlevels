# AQUA COMMAND · Water Operations & Telegram Alert Center

> **Prototype / not an official Provincial Waterworks Authority system.**
> A responsive, Thai-language Command Center for water distribution telemetry, operations incidents, and Telegram alert delivery.
>
> **สำคัญ:** สถานีและตัวเลขที่มากับโปรเจกต์เป็น **ข้อมูลจำลองทั้งหมด** ไม่ได้ดึงข้อมูลภายในของ กปภ. และไม่ได้รับรองว่าเกณฑ์วัดคุณภาพน้ำในโปรเจกต์เป็นเกณฑ์มาตรฐานทางกฎหมาย

## มีอะไรบ้าง

| Module | ความสามารถ |
|---|---|
| Overview | KPI ออนไลน์, แรงดันเฉลี่ย, ระดับถัง, สถานีเสี่ยง, กราฟ, สรุปคุณภาพน้ำ |
| Network Map | แผนผังเครือข่ายเชิงสัญลักษณ์พร้อมสถานะ 12 จุด, คลิกสถานีเพื่อดูรายละเอียด |
| Stations | ตาราง Telemetry แรงดัน, ระดับถัง, อัตราการไหล, ความขุ่น, คลอรีนอิสระ, สถานะออนไลน์ |
| Alerts | Warning, Critical, Resolved, Acknowledgement, Search/Filter, CSV Export |
| Analytics | กราฟย้อนหลังจากข้อมูลที่รับ, ข้อมูลคุณภาพน้ำ, สถิติเหตุการณ์ |
| Telegram | Bot API `sendMessage`, retry/backoff, คิวบันทึกลงดิสก์, status, ทดสอบข้อความ, retry failed |
| Telemetry API | รับค่าจริงที่ได้รับอนุญาตผ่าน JSON + API key, ตรวจความถูกต้อง, ไม่รับเลขนอกช่วง |
| Reliability | ตรวจ stale telemetry (สำหรับ live), แจ้งเตือนตอน severity เปลี่ยน, suppression/reminder |
| DevOps | Zero runtime npm dependencies, Dockerfile, Compose, healthcheck, Node tests |

### สถาปัตยกรรม

```text
  SCADA / PLC / RTU / Data Logger / Authorized Integration
                        |
                  Secure Adapter
                        |
                 HTTPS / VPN / mTLS
                        |
                POST /api/telemetry
                        |
      +-----------------+------------------+
      | Auth + Validation + Station Registry|
      +-----------------+------------------+
                        |
       +----------------+----------------+
       |                                 |
  Telemetry Snapshot                 Alert Rules
       |                                 |
  Server-Sent Events              Severity Change
       |                          Dedup / Cooldown
  Web Dashboard                         |
                                 Persistent Queue
                                        |
                                Telegram Bot API
                                        |
                                Telegram Chat/Group
```

**ปัจจุบันโปรเจกต์เป็นต้นแบบ single-node** ซึ่งรองรับการสาธิตและการพัฒนาต่อยอด ไม่ใช่ SCADA / OT ระบบผลิตจริงสำหรับโรงประปา และไม่ได้มีระบบควบคุมวาล์วหรือปั๊มจากระยะไกล

## วิธีเริ่มใช้งานอย่างรวดเร็ว (Node.js 20+)

```bash
unzip aqua-command-center-v1.0.0.zip
cd pwa-aqua-command
cp .env.example .env
# แก้ ADMIN_API_KEY ใน .env ให้เป็นค่าสุ่มความยาว >= 24 ตัวอักษร
npm start
```

เปิด `http://127.0.0.1:8787`

- ใช้ได้ทันทีใน **DEMO_MODE=true** โดยไม่ต้องมี Telegram Token
- กด **สร้างเหตุการณ์จำลอง** แล้วเลือกสถานี/ประเภทเหตุการณ์
- กด **รีเซ็ตการจำลอง** เพื่อนำสถานีกลับสู่สภาพปกติ
- ข้อมูลและ event history จะอยู่ใน `storage/state.json` (ยกเว้นเวลา/กราฟที่สร้างใหม่ระหว่างการเริ่มเซิร์ฟเวอร์)
- ไม่มี `npm install` ที่ต้องดึง dependencies จากอินเทอร์เน็ต

### Docker Compose (แนะนำสำหรับเครื่อง Server)

```bash
cp .env.example .env
# ตั้งค่า ADMIN_API_KEY/TELEGRAM... ใน .env ก่อน
sudo docker compose up -d --build
sudo docker compose ps
curl -s http://127.0.0.1:8787/api/health
```

Compose bind พอร์ตที่ localhost เท่านั้นโดยตั้งใจ เพื่อป้องกันไม่ให้ Telemetry หรือหน้าจัดการเหตุถูกเปิดสาธารณะโดยไม่ผ่านระบบ authentication. ถ้าต้องใช้จากเครื่องอื่น ใช้ VPN หรือ reverse proxy ที่มี TLS + SSO/RBAC.

## ตั้งค่า Telegram

1. คุยกับ **@BotFather** บน Telegram แล้วสร้าง Bot ใหม่ด้วย `/newbot`
2. คัดลอก Bot Token ไปใส่ `TELEGRAM_BOT_TOKEN` ใน `.env` (ห้ามเก็บใน client JS, Git, screenshot หรือ log)
3. เปิดแชตกับ Bot แล้วกด **Start** หรือเชิญ Bot เข้ากลุ่มและส่งข้อความในกลุ่ม
4. ดึง Chat ID ด้วย `getUpdates` ที่ฝั่ง Terminal ที่เชื่อถือได้ (เพื่อไม่ให้ token ปรากฏใน address bar):

   ```bash
   # หลังจากตั้ง .env และ restart/เปิด shell ใหม่
   set -a; source .env; set +a
   curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates" \
     | python3 -m json.tool
   # มองหาค่า result[].message.chat.id
   ```

5. ใส่ ID ลงใน `TELEGRAM_CHAT_ID` ของ `.env` (กลุ่มมักเป็นเลขติดลบ)
6. Restart Backend แล้วเข้า **ตั้งค่าระบบ → Admin API key → ส่งข้อความทดสอบจริง**
7. เช็ก **สถานะคิว** ว่าเป็น `SENT` ไม่ใช่แค่ว่า `QUEUED` (ข้อความที่ถูกเพิ่มเข้าคิวไม่ได้แปลว่า Telegram ได้รับแล้ว)

```ini
TELEGRAM_BOT_TOKEN=123456789:example_token_not_real
TELEGRAM_CHAT_ID=-1001234567890
ADMIN_API_KEY=put-a-real-random-secret-32-characters
SEND_DEMO_ALERTS=false
```

**นโยบายส่ง Telegram:** warning/critical ใหม่, ระดับเหตุเปลี่ยน, resolved, และ reminder เมื่อเหตุยังค้างเกินเวลาที่กำหนด; ข้อมูล telemetry ทุกแพ็กเก็ต **ไม่ได้** ถูกส่ง Telegram เพราะจะกลายเป็น spam. ค่าเริ่มต้นไม่ส่งเหตุการณ์ DEMO อัตโนมัติ (`SEND_DEMO_ALERTS=false`). ถ้าต้องการทดสอบส่งจริงจากการจำลอง เปลี่ยนเป็น `true` โดยตั้งใจและใช้กลุ่มทดสอบเท่านั้น

### Retry / reliability

- Persist queue ลง `storage/state.json` แบบเขียน temp แล้ว rename
- จำกัดอัตราการส่งไม่ถี่กว่า `TELEGRAM_MIN_GAP_MS` (default 1400ms)
- ส่งซ้ำด้วย exponential backoff เมื่อ Telegram/network error; สูงสุด 6 attempts แล้วเปลี่ยนเป็น `FAILED`
- ในหน้า Settings มี **Retry Failed Alerts** ใช้ API key สำหรับนำรายการล้มเหลวกลับเข้าคิว
- เป็นรูปแบบ **at-least-once**: ถ้า Telegram รับข้อความแล้วแต่คำตอบ timeout อาจส่งซ้ำได้ ไม่มีการรับรอง exactly-once
- สำหรับ production scale-out จำเป็นต้องใช้ database + queue ที่รองรับ multi-worker, monitoring, DLQ และ idempotency downstream

## เชื่อมต่อ Telemetry จริง

ปิดโหมดจำลองและตั้งค่า API key ก่อน:

```ini
DEMO_MODE=false
ADMIN_API_KEY=your-long-random-admin-key
STALE_AFTER_SECONDS=120
```

ตัวอย่าง HTTP request:

```bash
curl -X POST http://127.0.0.1:8787/api/telemetry \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: ${ADMIN_API_KEY}" \
  -d '{
    "stationId": "CM-01",
    "pressureBar": 2.68,
    "tankLevelPct": 75.5,
    "flowM3h": 2700,
    "turbidityNtu": 0.35,
    "chlorineMgL": 0.48,
    "online": true
  }'
```

- รหัสสถานีตัวอย่างอยู่ใน `stations` ภายใน `server.mjs` ต้องเปลี่ยนเป็น **Station Registry ที่ได้รับอนุมัติ** ก่อน production
- `DEMO_MODE=false`: สถานีเริ่มสถานะ `รอข้อมูล` (unknown) จนกว่าจะมี Telemetry จริง ไม่ปลอมค่าตัวเลขว่าสถานียัง online
- `STALE_AFTER_SECONDS`: เมื่อไม่รับค่าใหม่จากสถานีนานเกินกำหนด เปลี่ยน offline และสร้าง critical event
- API key ปกป้องการเปลี่ยนข้อมูล, การรับทราบเหตุ, Export CSV และปุ่มทดสอบส่ง Telegram
- พารามิเตอร์ตัวเลขที่ไม่ส่งมาจะคงค่าเดิมไว้; ข้อมูลเพิ่งเข้าระบบครั้งแรก field อื่นยังไม่มีค่า

ตัวอย่าง sensor event ที่ทำให้แรงดันอยู่ระดับ Critical:

```json
{"stationId":"CM-01","pressureBar":0.6}
```

ตัวอย่างคืนสภาพปกติ:

```json
{"stationId":"CM-01","pressureBar":2.7}
```

> ระบบนี้ไม่ดึงข้อมูลจากหน้า PWA portal แบบหลบ authentication. ต้องรับข้อมูลจากเจ้าของระบบหรือ API ที่ได้รับอนุญาตผ่าน Integration Adapter.

## Example Alert Rules (เพื่อ DEMO เท่านั้น)

| Rule | WARNING | CRITICAL |
|---|---:|---:|
| แรงดันต่ำ | < 1.5 bar | < 0.9 bar |
| แรงดันสูง | > 5.0 bar | > 5.8 bar |
| ถังเก็บน้ำต่ำ | < 35% | < 20% |
| ความขุ่น | > 1.0 NTU | > 4.0 NTU |
| คลอรีนอิสระต่ำ | < 0.2 mg/L | < 0.1 mg/L |
| Station offline | — | Offline / Stale |

**ไม่ใช่เกณฑ์อ้างอิงคุณภาพน้ำตามกฎหมายหรือข้อกำหนด กปภ.** ต้องให้วิศวกรประปาและทีมคุณภาพน้ำอนุมัติเกณฑ์ตามจุดติดตั้ง ลักษณะสถานี และเครื่องมือวัดก่อนนำไปใช้งานจริง. แก้ได้ที่ `rules.mjs`.

## REST Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/health` | — | Readiness response |
| GET | `/api/state` | — | Dashboard snapshot (ต้องเข้าผ่าน VPN/SSO เมื่อ production) |
| GET | `/api/stream` | — | SSE status push |
| POST | `/api/telemetry` | API key | Authorized sensor data |
| POST | `/api/demo/incident` | localhost or API key | Simulate event if DEMO mode |
| POST | `/api/demo/reset` | localhost or API key | Reset simulated network |
| POST | `/api/test-telegram` | API key | Queue a real Telegram test message |
| POST | `/api/queue/retry-failed` | API key | Retry all failed jobs |
| POST | `/api/alerts/:id/ack` | API key | Mark incident acknowledged |
| GET | `/api/export/alerts` | API key | CSV export |

## Run automated tests

```bash
npm test
```

Tests cover: thresholds, offline and high readings, message format, clean live-mode startup, auth, payload validation, deduplication, severity transitions, recovery, export, and demo endpoint isolation.

## Production acceptance checklist

Prototype แสดง UX/แนวทาง orchestration ได้ แต่ยังไม่ใช่ production-grade PWA infrastructure. ก่อนปล่อยสู่ระบบจริงต้องเพิ่มอย่างน้อย:

- **Identity:** SSO/OIDC + RBAC แยก operator, supervisor, admin; protected read APIs; immutable audit trail
- **OT boundary:** read-only OT gateway/DMZ, mTLS, per-station identity, anti-replay, timestamp validation, no direct inbound access to PLC
- **Data quality:** calibration, stale/error handling, unit and timestamp standardization, approved branch/station registry
- **Durability:** PostgreSQL/TimescaleDB + durable queue (Redis Streams/RabbitMQ/Kafka) + offsite backup/restore drills
- **Alert engineering:** approved thresholds per station, hysteresis, maintenance windows, correlation, SLA/escalation and on-call routing
- **Resilience:** failover, multi-zone storage, distributed worker locks, Telegram 429 Retry-After support, external monitoring
- **Security:** HTTPS, private network, CSP hardening, secrets manager, rate limiting, audit logging, penetration test, threat model
- **Observability:** Prometheus/OpenTelemetry, application logs, ingestion lag, queue age, dropped messages, SLO burn rate alerts
- **Governance:** written authorization from PWA/data owners, PDPA assessment, official brand/legal clearance if public-facing

### Project layout

```text
pwa-aqua-command/
├── public/
│   ├── index.html           Responsive app shell
│   ├── app.js               Interactive dashboard and SSE client
│   ├── style.css            Dark Command Center design system
│   └── favicon.svg
├── server.mjs               Node HTTP + SSE + Telegram worker
├── rules.mjs                Alert threshold engine
├── tests/                   Unit + integration tests
├── storage/                 Persistent JSON (excluded from git)
├── Dockerfile
├── compose.yaml
├── .env.example
└── README.md
```

## Reference documentation

- PWA public service statistics: https://www.pwa.co.th/support-units/service
- PWA official station info: https://www.pwa.co.th/province/
- PWA Data Logger & SIM portal (authenticated): https://dmasim.pwa.co.th/
- Telegram Bot API `sendMessage`: https://core.telegram.org/bots/api#sendmessage

Prototype source is supplied as a private project starter. No rights to official PWA trademarks, system data or internal APIs are claimed.
