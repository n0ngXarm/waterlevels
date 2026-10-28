# AQUA COMMAND Desktop

Native GTK4 desktop application, distributed as RPM for Fedora44. No website, browser, embedded webview, dashboard HTTP listener or Docker is needed. The frontend controls only AQUA recording and local CSV export; WinCC/PLC access remains strictly read-only.

โปรแกรมเดสก์ท็อปสำหรับ Fedora 44: ติดตั้ง RPM แล้วเปิด **AQUA COMMAND** จากเมนูแอป เริ่มต้นเป็นข้อมูล LAB และ Telegram dry-run อ่านค่าอย่างเดียว ไม่สั่งงานปั๊มหรือเขียนกลับ WinCC/PLC

Install the RPM with the system package manager, then launch **AQUA COMMAND** from the applications menu:

```sh
sudo dnf install ./aqua-command-desktop-0.6.0-1.fc44.noarch.rpm
```

The default mode is labelled LAB data with Telegram dry-run. In **ตั้งค่าแหล่งข้อมูล**, select an approved runtime CSV directory and import a local tag-name file or WinCC Tag Management configuration export. Only Binary `.RUN_S` names are selected from configuration exports; addresses/commands are not imported. Actual names remain in private local settings, never in this public repository. CSV values must already be exported by WinCC; the app does not connect to or modify WinCC/PLC. Quality/mapping confirmation is required before asserting ON/OFF; missing/bad/stale values remain unknown.

Buttons: start/stop local collection, save CSV, open the saved-data folder. Changing source settings retains prior profiles/queues. State is under the user's local state directory, separate from the source. The reader retains existing cursor/transaction, quotas, ACK/retry/dedup and explicit-peer safeguards. Gateways are enrolled, not found by network-wide scanning. Internet checks/actual Telegram remain explicit approved test configuration; default traffic is loopback only.

**Save CSV exports recent retained snapshots**, bounded to 2,000 events / 250 KB of source payload per click. The window warns if retained records exceed the export view. This is not an unlimited archive: the source retains up to 2,000 ACKed events and 10,000 pending events; full pending storage stops capture with an error and retains unACKed records. The original runtime CSV folder is never changed. Changing profiles parks the previous profile's queues; reopen the same settings to resume them.

For a short demonstration: open the app, wait about 10 seconds for snapshots and local delivery, pause collection, resume it, save CSV, and open the output folder. The pause button only affects AQUA's local reader. Switching to approved runtime CSV requires tag names, the file timezone, and confirmation of value/quality mapping. A Tag Management configuration export supplies names only; it does not contain runtime snapshots and cannot replace the runtime CSV feed.

The native window currently runs a single-machine LAB profile with its enrolled loopback agent/Gateway/Central. It does not configure a second computer from the UI. Real LAN transport is covered by local socket tests; joining two physical machines and testing real internet egress require a separately approved LAB setup. No claim of automatic discovery of arbitrary internet-enabled PCs is made.

Linux dependencies are provided by RPM: Python3, PyGObject, GTK4 and Node22.13+. Backend code continues the tested CSV/SQLite/LAN implementation. Frontend-to-host communication is private stdin/stdout; only role transport endpoints use authenticated HTTP(S). The old web assets in `backend/public` are regression fixtures only and are excluded from the RPM, along with old web entry points.

Developer verification:

```sh
npm test --prefix backend
python3 -m unittest discover -s desktop/tests
bash packaging/build-rpm.sh /absolute/build-directory
```

Windows `.exe`, WinCC Runtime execution, two physical LAN hosts, actual Telegram and hardware power loss have not been verified by the Linux build. This release delivers an RPM; it does not claim a Windows executable was built. No production OT, firewall, routing/NAT/bridge or sharing configuration is touched.

The RPM is unsigned and targets Fedora 44. The developer check exercised its extracted payload and launcher in a private folder; a system-wide DNF installation transaction has not been performed. [Verification and rollback](VERIFICATION.md).
