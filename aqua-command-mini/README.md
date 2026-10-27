# AQUA COMMAND Mini v0.1

**สำหรับเพื่อนที่จะทดสอบ:** [ดาวน์โหลดโปรแกรม Windows x64](https://github.com/n0ngXarm/waterlevels/raw/refs/heads/codex/aqua-command-mini-v0.1/aqua-command-mini/releases/v0.1/AQUA_COMMAND_Mini_v0.1_windows_x64.zip) · [วิธีติดตั้งทีละขั้น](INSTALL_TH.md)

โปรแกรม PoC สำหรับเครื่องทดสอบ Windows 11 x64 ที่แยกจาก WinCC/PLC ของสถานีห้วยแก้ว รับไฟล์ TXT/CSV ในเครื่อง หรือข้อมูลจำลอง แสดงผลตามกติกาที่กำหนด และ export structured CSV ได้ ค่าเริ่มต้นเป็น **DRY-RUN** เสมอ **ไม่พร้อม Production**

## เริ่มทดสอบแบบไม่เชื่อมต่อระบบ

1. ใช้เครื่องทดสอบที่ผู้รับผิดชอบอนุญาตและแยกจากเครือข่าย OT ห้ามติดตั้งบนเครื่อง WinCC
2. แตก ZIP รุ่น Windows ทั้งโฟลเดอร์ไว้ในพื้นที่ของผู้ใช้ เช่น Documents ห้ามนำเฉพาะ `.exe` ออกจากโฟลเดอร์ `_internal`
3. ดับเบิลคลิก `Start.cmd` หรือ `AQUA_COMMAND_Mini.exe` ไม่ต้องใช้สิทธิ์ administrator และไม่ต้องติดตั้ง Python สำหรับรุ่น portable
4. กด **ข้อมูลจำลองใหม่** ควรเห็น `DEMO_PUMP_01 = ON` และ `DEMO_VALVE_01 = OFF` พร้อมข้อความ DRY-RUN ข้อมูลจำลองใช้เวลาปัจจุบันของเครื่อง
5. กด **Export structured CSV** ตั้งชื่อไฟล์ใหม่ แล้วเปิดดูคอลัมน์ state, reason และ notification_decision ไฟล์มี UTF-8 BOM เพื่อเปิดภาษาไทยใน Excel
6. กด **บันทึกประวัติ dry-run** แล้วกด **ตรวจเกณฑ์อีกครั้ง** รายการเดิมควรแสดงว่าซ้ำกับประวัติ ไม่มี Telegram ถูกส่ง
7. เลือก `examples/tag_configuration_synthetic.txt` ต้องขึ้น **Tag Configuration เท่านั้น** ไม่มี ON/OFF และปุ่ม export สถานะถูกปิด
8. ปิดอินเทอร์เน็ตแล้วทำขั้นตอน 3–7 ซ้ำได้ ส่วน Telegram TEST เท่านั้นที่ต้องใช้อินเทอร์เน็ตเมื่ออนุมัติให้ส่งจริง

รุ่น executable ในการส่งมอบนี้สร้างด้วย Python สำหรับ Windows ผ่าน Wine บน Linux ดูผลจริงใน `evidence/TEST_REPORT_TH.md` การผ่าน Wine ไม่เท่ากับผ่าน Windows 11 จริง ให้ตรวจตาม `docs/WINDOWS11_ACCEPTANCE.md` ก่อนส่งให้ผู้ทดสอบใช้กับไฟล์ที่อนุญาต

ไฟล์ executable เป็น build สำหรับ PoC ที่ยังไม่ลงลายเซ็น หากนโยบายเครื่องบล็อก ให้ผู้ดูแลตรวจ checksum และจัดการอนุมัติตามนโยบายหน่วยงาน

## ใช้รุ่น source

ใช้ Python 3.13 x64 แบบปกติที่มี Tcl/Tk บนเครื่องพัฒนาหรือทดสอบแยก รุ่น source ไม่ต้องติดตั้งไลบรารีจาก pip เพื่อใช้งานหรือรัน tests

```powershell
py -3.13 -m aqua_command gui
```

หรือดับเบิลคลิก `Start.cmd` ในโฟลเดอร์ source แกนโปรแกรมใช้ Python 3.12 ขึ้นไปได้ แต่ launcher และขั้นตอน build ที่ให้มาเลือก Python 3.13

คำสั่งด้านล่างรันในโฟลเดอร์ source หากใช้ portable ให้แทน `py -3.13 -m aqua_command` ด้วย `.\AQUA_COMMAND_Mini_CLI.exe`

```powershell
py -3.13 -m aqua_command demo --output demo-new.csv
py -3.13 -m aqua_command preview demo-new.csv --data-dir .\local-test-state --export structured-new.csv
py -3.13 -m aqua_command dry-run demo-new.csv --data-dir .\local-test-state --json
py -3.13 -m aqua_command dry-run demo-new.csv --data-dir .\local-test-state --json
py -3.13 -m aqua_command telegram-test --json
```

คำสั่ง `preview` ไม่ consume ประวัติ; `dry-run` บันทึกประวัติในเครื่องและไม่ส่ง Telegram ทุกคำสั่งสร้างไฟล์ใหม่จะปฏิเสธชื่อที่มีอยู่แล้ว ให้เปลี่ยนชื่อไฟล์เมื่อลองซ้ำ

## ขอบเขตที่บังคับในโปรแกรม

- อ่านไฟล์ที่เลือกด้วยมือ ไม่มี live polling, directory watcher, WinCC REST, PLC driver หรือ network scanner
- WinCC REST เป็น OFF ไม่มีจุดเปิด REST ใน config และไม่ต้องใช้ license ของ WinCC
- ไม่แก้ configuration/runtime ไม่เขียนไฟล์ต้นฉบับ และไม่ส่งข้อมูลจากไฟล์ออกอินเทอร์เน็ต
- ไม่รับ UNC share, URL หรือ mapped network drive ของ Windows ต้องคัดลอกไฟล์ที่อนุญาตลงดิสก์ในเครื่องก่อน ไม่ได้ตรวจจับ network filesystem ทุกชนิดบนระบบปฏิบัติการอื่น
- ไม่ยืนยันสิทธิ์ของผู้ส่งออกไฟล์โดยอัตโนมัติ เจ้าหน้าที่ต้องใช้กระบวนการอนุมัติของหน่วยงาน
- ส่งออกเฉพาะ structured CSV ในเครื่อง การเปิดหรือส่งต่อ CSV เป็นการดำเนินการของผู้ใช้

## แยก Tag Configuration ออกจาก Runtime / Archive

ไฟล์ที่เริ่มด้วย `DmTag` / `Tags` / `Tag` หรือมี metadata เช่น `[NAME][100]` และ `[TYPE][101]` จัดเป็น `tag_configuration` แม้จะมีหัวตารางคล้าย runtime ต่อท้าย ไม่ถือว่า StartValue, Address หรือข้อมูลตั้งค่าเป็นค่าการทำงานจริง

ส่วนหัวของไฟล์อ้างอิง `Export all(1).txt` เป็นลักษณะนี้ จึงต้องใช้เป็น configuration เท่านั้น ไฟล์ต้นฉบับและชื่อ Tag จริงของสถานีไม่ได้รวมในชุดแจกจ่าย

โปรแกรมจะอ่าน Runtime Process Value / Archive เฉพาะ schema ที่ประกาศด้านล่าง ไม่ได้รองรับ export ทุกเวอร์ชันของ WinCC รูปแบบอื่นเป็น `unknown` หรือให้แถวเป็น UNKNOWN พร้อมเหตุผล ต้องให้ผู้รับผิดชอบยืนยันรูปแบบก่อนแปลงสำเนาแบบ offline โดยรักษาต้นฉบับ

## รูปแบบไฟล์ที่รองรับ

UTF-8, UTF-8 BOM, UTF-16 LE/BE พร้อม BOM และ UTF-16 ไม่มี BOM เฉพาะกรณีที่รูปแบบ NUL ของหัวตาราง ASCII ชัดเจน ไม่เดา ANSI/Windows-874; decoding ผิดจะหยุด ไม่แทนตัวอักษรที่อ่านไม่ได้

delimiter เป็น Tab, semicolon หรือ comma ตรวจจากหัวตาราง ไม่เดาตำแหน่ง column CSV ที่ quote ถูกต้องรองรับได้ ต้องมี semantic column ทั้งสี่อย่างละหนึ่งเท่านั้น ชื่อหัวตารางไม่แยกตัวพิมพ์ใหญ่/เล็ก:

| ความหมาย | หัวตารางที่รับ |
|---|---|
| tag | `tag`, `TagName`, `tag_name`, `VariableName`, `VarName` |
| timestamp | `timestamp`, `DateTime`, `date_time`, `TimeString`, `time_stamp` |
| value | `value`, `ProcessValue`, `RealValue`, `VarValue` |
| quality | `quality`, `QualityCode`, `quality_code`, `Validity` |

ตัวอย่างนี้เป็นข้อมูลจำลอง:

```csv
tag,timestamp,value,quality
DEMO_PUMP_01,2026-10-27T10:00:00+07:00,1,GOOD
DEMO_VALVE_01,2026-10-27T10:00:00+07:00,0,GOOD
```

Timestamp รับ ISO 8601 แบบ `YYYY-MM-DDTHH:MM:SS[.fraction]Z` หรือ `+07:00` เป็นต้น ใช้ space แทน T ได้ precision สูงสุด 6 ตำแหน่ง ไม่เดา DD/MM กับ MM/DD ถ้าไม่มี timezone ต้องตั้ง `source_utc_offset` ในโปรไฟล์อย่างชัดเจน หากยังเป็น `null` จะเป็น UNKNOWN

`Validity` เป็นเพียง alias ของชื่อ column โปรแกรมไม่อนุมานความหมายของรหัส quality ค่าตัวเลข `192`, `0`, `1` ต้องตรวจความหมายตาม export และเวอร์ชันจริง แล้วเพิ่มใน `good_quality` โดยผู้รับผิดชอบเท่านั้น

จำกัดไฟล์ 10 MiB, 50,000 data rows, 64 columns และ 8,192 ตัวอักษรต่อ field ตารางหน้าจอแสดง 2,000 แถวแรก; CSV และ JSON export ครบทุกแถว CSV quote ผิดจะหยุดทั้งไฟล์ จำนวน column ไม่ตรงจะเก็บแถวเป็น ERROR

ไฟล์ runtime ตัวอย่างใน `examples` ใช้เวลาคงที่ จึงอาจขึ้น STALE เมื่อเปิดภายหลัง ใช้ **ข้อมูลจำลองใหม่** เพื่อทดสอบค่าที่ fresh

## กำหนด Tag และกติกา ON/OFF

ค่าเริ่มต้นมีเฉพาะ `DEMO_PUMP_01` และ `DEMO_VALVE_01` ซึ่งเป็นชื่อจำลอง ไม่มี Tag ของสถานีที่ได้รับอนุญาตโดยปริยาย

1. คัดลอก `examples/profile.empty.json` เป็น `profile.local.json` ในเครื่องทดสอบ
2. ให้ผู้รับผิดชอบระบุ Tag ที่อนุญาตแบบตรงตัว แยกตัวพิมพ์ใหญ่/เล็ก โปรแกรม trim whitespace รอบ field ก่อนเทียบ
3. แต่ละ Tag ต้องมี mapping ของ string `0` และ `1` ไป ON/OFF อย่างละหนึ่ง และรายการ good quality ที่ยืนยันแล้ว เช่น:

```json
"tags": {
  "DEMO_PUMP_01": {
    "mapping": {"0": "OFF", "1": "ON"},
    "good_quality": ["GOOD"]
  }
}
```

4. ค่า `1.0`, `true`, `ON`, ค่าว่าง, NaN และค่าที่ไม่มี mapping จะเป็น UNKNOWN ไม่ใช้ truthy/falsey หากกระบวนการจริงมี mapping กลับด้าน ต้องตั้งกลับด้านอย่างชัดเจน
5. ค่าเริ่มต้น `freshness_seconds = 300` และ `future_tolerance_seconds = 5` นาฬิกาเครื่องต้องถูกต้อง ไม่มีการ sync กับระบบสถานี
6. `source_utc_offset = null` บังคับ timezone ในแต่ละ timestamp หากยืนยันว่าต้นทางใช้เวลาประเทศไทยโดยไม่มี timezone จึงตั้ง `"+07:00"` ได้
7. เลือกโปรไฟล์ผ่านปุ่ม **เลือกโปรไฟล์ JSON** แล้วเลือกไฟล์ใหม่ หรือใช้ `--config profile.local.json` ต้องเลือกโปรไฟล์ใหม่ทุกครั้งที่เปิด GUI; โปรแกรมไม่เปิด profile.local หรือเปิดส่ง Telegram อัตโนมัติ

โปรไฟล์ไม่รับ field ที่ไม่รู้จัก ไม่รับ JSON key ซ้ำ และไม่รับ token/chat ID แบบ plaintext ในโปรไฟล์ การแก้โปรไฟล์สร้าง policy fingerprint ใหม่ จึงใช้ประวัติ dry-run คนละชุดกับกติกาเดิม

## UNKNOWN, ERROR และการกันซ้ำ

| เหตุผล / ผล | พฤติกรรม |
|---|---|
| `TAG_NOT_ALLOWED` | UNKNOWN, ไม่เป็น candidate |
| `VALUE_NOT_MAPPED` | UNKNOWN, ไม่เดา ON/OFF |
| `QUALITY_NOT_ACCEPTED` | UNKNOWN, ไม่ใช้ค่าที่ quality ไม่ผ่าน |
| `STALE` / `FUTURE_TIMESTAMP` | UNKNOWN ตามอายุหรือเวลาอนาคต |
| `TIMEZONE_REQUIRED` / เวลาไม่ถูกต้อง | UNKNOWN ไม่เดา timezone/วันที่ |
| `COLUMN_COUNT` | ERROR พร้อมข้อมูลที่อ่านได้จากแถวนั้น |
| `CONFLICTING_SAMPLES` | sample เวลาเดียวกันแต่ค่าหรือ quality ขัดกันเป็น UNKNOWN |
| `UNORDERED_SAMPLE` | Tag มี sample ที่เรียงเวลาไม่ได้ จึงระงับทั้ง Tag ในไฟล์นั้น |
| `SUPERSEDED` | มี sample ใหม่กว่าในไฟล์ ไม่ใช้เป็น candidate แม้แถวนั้นผ่านเกณฑ์ |
| `DUPLICATE_IN_FILE` / `DUPLICATE_HISTORY` | ไม่สร้าง candidate ซ้ำ |
| `UNCHANGED` | เวลาใหม่แต่สถานะเดิม ไม่สร้าง candidate; บันทึก high-water time เมื่อกด dry-run |
| `OUT_OF_ORDER` / `HISTORY_CONFLICT` | ไม่ย้อนสถานะจากประวัติเดิม ไม่ยอมรับค่าขัดกันที่ timestamp เดิม |

พิจารณาเฉพาะ sample ล่าสุดต่อ Tag หากล่าสุด quality ไม่ผ่าน จะไม่ย้อนใช้ sample ก่อนหน้าเป็น candidate ค่า UNKNOWN/ERROR ไม่เปลี่ยน baseline ที่ยืนยันแล้ว `CANDIDATE` หมายถึงเข้าเกณฑ์จำลองในเครื่อง ไม่มีการส่งค่าจากไฟล์ไป Telegram ใน v0.1

ประวัติเก็บใน `%LOCALAPPDATA%\AQUA_COMMAND_Mini\history.sqlite3` หรือ directory ที่ระบุด้วย `--data-dir` ใช้ transaction กันการบันทึกซ้ำพร้อมกัน ประวัติเสียหาย/ล็อกจะหยุด ไม่ลบหรือเริ่มใหม่เงียบ ๆ การลบหรือเปลี่ยน directory ประวัติทำให้จำรายการซ้ำไม่ได้ ให้เก็บประวัติตลอดช่วง PoC

หน้าจอแสดงผล **ณ เวลาประเมินที่ระบุ** ไม่มีการอ่าน live หรือ refresh อัตโนมัติ เมื่อกดตรวจเกณฑ์, export หรือบันทึก dry-run จะตรวจ freshness ของ snapshot เดิมใหม่ ไม่เปิด source ไปอ่านเองอีกครั้ง

## Structured CSV และต้นฉบับ

เก็บ source name, SHA-256 ของ bytes ที่นำเข้า, encoding, delimiter, source row, raw tag/time/value/quality, normalized UTC timestamp, state, reason, decision และ `mode=DRY_RUN` ไม่ export สถานะจาก configuration/unknown

สร้างไฟล์ใหม่เท่านั้น ไม่ overwrite เป้าหมายที่มีอยู่ รวมถึง source, symlink และ hardlink ที่มีอยู่ Cells ที่อาจเป็น spreadsheet formula จะเติม `'` หน้าเพื่อไม่ให้ Excel รันสูตร raw columns ใน structured CSV จึงอาจมี apostrophe เพิ่ม ไฟล์ต้นฉบับยังคง bytes เดิม ใช้ต้นฉบับกับ SHA-256 เพื่ออ้างอิง raw bytes ไม่ใช้ structured CSV เป็น replacement ของต้นฉบับ

## Telegram TEST หลังอนุมัติเท่านั้น

v0.1 ส่งได้เฉพาะข้อความคงที่:

```text
[TEST] AQUA COMMAND Mini v0.1
SIMULATED DATA ONLY
DEMO_PUMP_01: ON
DEMO_VALVE_01: OFF
No plant data included. File import does not send notifications.
```

ไม่มีชื่อสถานี, Tag จริง, ชื่อไฟล์, ค่า, timestamp หรือ hash จากไฟล์ในข้อความนี้ โปรแกรมไม่มีช่องข้อความอิสระสำหรับส่งข้อมูล การส่ง TEST ยังเปิดเผยต่อ Telegram ตามการเชื่อมต่อปกติ เช่น IP เครื่องทดสอบและผู้รับ จึงต้องอนุมัติการเชื่อมต่อนี้ก่อน

1. ให้ผู้รับผิดชอบอนุมัติเครื่องทดสอบ Windows, ผู้รับ Telegram และการออกอินเทอร์เน็ต เก็บเลขอ้างอิงการอนุมัติ ไม่ใช้เครื่อง WinCC
2. อ่าน Machine ID ด้วย `py -3.13 -m aqua_command machine-id` หรือดูแท็บ Telegram TEST ค่านี้เป็น hash ของ OS identity ในเครื่อง ไม่ใช่การค้นหา MAC/เครือข่าย
3. ตั้ง environment ใน PowerShell ของเครื่องทดสอบอย่างปลอดภัย ตัวอย่างนี้ไม่พิมพ์ token ลงประวัติคำสั่ง:

```powershell
$aquaSecret = Read-Host "Telegram bot token" -AsSecureString
$aquaPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($aquaSecret)
try {
    $env:AQUA_TELEGRAM_BOT_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($aquaPointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($aquaPointer)
}
$env:AQUA_TELEGRAM_CHAT_ID = Read-Host "Approved numeric test chat ID"
py -3.13 -m aqua_command recipient-hash
```

Environment เป็น plaintext ในหน่วยความจำ process; ไม่ใช่ encrypted vault ห้ามแชร์ shell/session, เปิด transcript ที่บันทึก environment หรือใส่ token ใน source, CLI arguments, JSON, screenshot, Git หรือชุด ZIP โปรแกรมไม่อ่าน `.env` เอง หาก token รั่ว ให้ผู้ดูแล revoke/rotate ผ่านกระบวนการที่อนุมัติ

4. ในโปรไฟล์ท้องถิ่นตั้ง `telegram.enabled` เป็น `true`, ใส่ Machine ID ใน `approved_machine_ids`, เลขอนุมัติใน `approval_reference` และผลคำสั่ง recipient-hash ใน `approved_chat_id_sha256` ห้ามใส่ token หรือ chat ID ตรง ๆ ใน JSON
5. เปิด GUI จาก PowerShell เดิมเพื่อให้รับ environment: `py -3.13 -m aqua_command gui --config profile.local.json` หรือ `.\AQUA_COMMAND_Mini.exe gui --config profile.local.json` การดับเบิลคลิกจาก Explorer จะไม่รับตัวแปรที่เพิ่งตั้งเฉพาะใน shell นี้
6. กดตรวจเงื่อนไข ต้องไม่มีเหตุผลที่ยังไม่ผ่าน ตรวจข้อความจำลอง แล้วติ๊กยืนยัน TEST ครั้งนี้ก่อนกดส่ง หรือใช้คำสั่งต่อไปนี้เมื่อได้รับอนุมัติแล้ว:

```powershell
py -3.13 -m aqua_command telegram-test --config profile.local.json --send --confirm-test --json
```

7. `SENT` หมายถึง API ตอบว่าส่งสำเร็จ ไม่ยืนยันว่าผู้รับอ่านแล้ว ถ้า timeout/response กำกวมจะเป็น `FAILED_UNKNOWN` และไม่ retry อัตโนมัติ ตรวจห้อง TEST ก่อน ห้ามลบประวัติเพื่อกดส่งซ้ำ
8. กันซ้ำด้วยการ reserve ลง SQLite **ก่อนเรียกเครือข่าย** ส่ง TEST ได้ไม่เกินหนึ่งครั้งต่อวัน UTC ต่อ directory ประวัติ แม้ปิด/เปิดแอปใหม่ การเปลี่ยนเครื่อง/ประวัติทำให้ขอบเขตการกันซ้ำเปลี่ยน ไม่ใช่บริการส่วนกลาง
9. หลังทดสอบ ปิดแอป แล้วล้าง environment ใน PowerShell นั้น:

```powershell
Remove-Item Env:AQUA_TELEGRAM_BOT_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:AQUA_TELEGRAM_CHAT_ID -ErrorAction SilentlyContinue
Remove-Variable aquaSecret, aquaPointer -ErrorAction SilentlyContinue
```

มีเฉพาะ HTTPS host `api.telegram.org`, ตรวจ certificate ตาม OS trust store, ไม่ตาม redirect, ไม่อ่าน proxy จาก environment และไม่เก็บ API response/URL ที่มี token ใน logs หากเครือข่ายบังคับ proxy จะส่งไม่ได้ใน v0.1 การอนุมัติผ่าน local profile เป็นมาตรการดำเนินงานสำหรับ PoC ผู้ที่แก้ source/config/ประวัติได้สามารถเปลี่ยนกติกาได้ จึงไม่ใช่ระบบ access control สำหรับ Production

## รัน tests และ build ใหม่บน Windows

```powershell
$env:AQUA_RUN_GUI_TESTS = "1"
$env:PYTHONUTF8 = "1"
py -3.13 -m unittest discover -v
.\scripts\build_windows.ps1
```

หรือใช้ `Test_Offline.cmd` ใน source Tests ทั้งหมดใช้ข้อมูลจำลองและแทนเฉพาะขอบเขต HTTP ของ Telegram ไม่ต้องใช้ bot จริง Build ต้องดาวน์โหลดเครื่องมือจาก PyPI บนเครื่องพัฒนาที่อนุญาต; ไม่ทำบนเครื่องสถานี

สคริปต์ build สร้าง venv แยก รัน tests สร้าง GUI/CLI executable ทดสอบ bundle ด้วยข้อมูลจำลอง สร้าง SHA256SUMS และ ZIP ที่ `dist/AQUA_COMMAND_Mini_v0.1_windows_x64.zip` ไม่ overwrite directory ผลลัพธ์เดิม หากมีอยู่ให้เก็บ archive แล้วใช้สำเนา source ใหม่

ใน repository `waterlevels` มี workflow ที่ `../.github/workflows/aqua-command-mini-windows.yml` สำหรับกด `workflow_dispatch` เอง ส่วน `.github/workflows/windows-build.yml` ภายในโฟลเดอร์ Mini เป็น template สำหรับ source แบบ standalone ใช้เฉพาะ source และข้อมูลจำลอง ห้ามอัปโหลดไฟล์สถานี, profile.local, token หรือประวัติขึ้น repository Workflow นี้ยังไม่ได้ถูกรันจาก workspace นี้

## หลักฐานและข้อจำกัด

ดู `evidence/TEST_REPORT_TH.md`, logs, bundle smoke result และภาพหน้าจอที่ให้มา แยกผล Linux, Windows runtime ผ่าน Wine และรายการที่ยังต้องตรวจบน Windows 11 จริงอย่างชัดเจน

ยังไม่ส่ง Telegram จริง ไม่มี credentials หรือรายการเครื่อง/ผู้รับที่อนุมัติรวมในชุดแจก ไม่ยืนยันชื่อ Tag, ความหมาย 0/1, quality code หรือ timezone จริงของสถานี และไม่ได้ทดสอบเชื่อม WinCC/PLC เพราะอยู่นอกขอบเขตที่อนุญาต

## เอกสารทางการที่ใช้

- [Telegram Bot API: requests และ sendMessage](https://core.telegram.org/bots/api#sendmessage)
- [PyInstaller: วิธี bundle และข้อจำกัดตามระบบปฏิบัติการ](https://pyinstaller.org/en/stable/operating-mode.html)
- [Python สำหรับ Windows](https://www.python.org/downloads/windows/)
