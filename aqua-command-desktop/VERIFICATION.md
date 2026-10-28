# 0.7.0 permission and UX increment

This increment addresses operator permission before any work, separate collection/transfer permission, explicit unavailable WinCC Runtime, and a clearer native workflow. It does not implement a direct WinCC driver or authorize production changes.

| Gate | Changed files | Evidence | Risk / rollback |
| --- | --- | --- | --- |
| G0 audit | Existing desktop and service entry points | Identified constructor auto-start, unguarded sampling and forwarding; repository clean at 3763d2a before changes | Prior RPM auto-start behavior superseded; original v0.3 untouched |
| G1 permission boundary | services.js, config.js, supervisor.js, host.mjs | New regression first failed on auto-start. Capture and transfer require explicit approval; every role restart resets its permissions | Existing requests may finish; generation checks prevent the next request after revocation. Revert source only for investigation, not as a safe deployment |
| G2 native UX | app.py, style.css, consent.py, tests | Initial window has no worker and creates no state files. Cancel starts nothing. Read approval creates a local queue without delivery; separate send approval drains it | Runtime unavailable stays blocked; no automatic LAB substitution. Stop/close keeps queues |
| G3 regression | backend/tests/desktop.test.js, desktop/tests, ui_test.py | Local socket/process tests, permission scope/cancel/remember/revoke/relaunch, CSV immutability and unknown quality. Test commands below | WinCC, Windows, physical LAN and actual external sends unverified |
| G4 package | version0.7 RPM spec/launcher/payload | Native integration supports --installed-root to exercise actual packaged files. No web assets, startup service or scriptlets | Private payload deployment, not a system DNF transaction; unsigned Fedora44 LAB build |
| G5 review/delivery | README, release binary/checksum | Independent review found revoke-during-request and delayed fixture-restart races; regression tests reproduce both before fixes | Publish on dedicated feature branch; remote commit comparison and concrete result counts recorded in delivery report |

Tests:

```sh
npm test --prefix backend
python3 -B -m unittest discover -s desktop/tests -v
desktop-file-validate packaging/org.aquacommand.Desktop.desktop
python3 -B desktop/ui_test.py
```

Remembered grants are hashes of source mode/settings/tag mapping/interval/storage and exact loopback destination identity/URLs/dry-run mode. They suppress the review dialog only after a manual start click. Capture and transfer grants are separate. Invalid/missing/old consent files deny permission. No record of consent grants runtime access through an unavailable driver.

The tests use owned LAB data, local sockets and a deferred fake Telegram probe for the revocation race. No actual Telegram request, source/PLC write, production connection, network scan, service enablement or network configuration change is used. Uploaded SCADA samples and real tag names remain outside this public repository.

Rollback after an actual install: close AQUA, then `sudo dnf remove aqua-command-desktop`. Retain user state and queues. Original inputs are untouched. Reinstalling an old auto-starting version is not the recommended rollback.

# Historical 0.6.0 LAB verification (superseded startup UX)

Scope: native GTK4 frontend and Fedora 44 RPM, continuing the read-only CSV/SQLite/LAN backend. The original v0.3 checkout and the repository's existing production web services were not modified or run. Root README only adds the native application entry point.

These gates describe this native desktop increment. They do not certify Windows, WinCC Runtime or physical-LAN acceptance.

| Gate | Changed files | Test results and evidence | Risks / remaining work | Rollback |
| --- | --- | --- | --- | --- |
| G0 audit | No original source changes; isolated `backend/` copy with generic LAB fixtures | Existing 44-test baseline passed before native changes; original scripts and source inspected | No production or Windows baseline executed | Discard the new subtree |
| G1 private backend host | `desktop/host.mjs`, backend headless dashboard/config/supervisor, desktop tests | Headless status and real local child-process/socket tests pass; UI port refuses connection; unsupported pump/path commands rejected | LAN role HTTP endpoints remain authenticated local transports | Revert native host changes |
| G2 native frontend | `desktop/app.py`, `client.py`, `model.py`, `style.css`, Python tests | Four model tests pass: private profiles, tag import immutability, source alias rejection, stale/bad values unknown | Tag configuration is names only; approved runtime CSV feed still required | Remove the native app; original UI remains in history |
| G3 local integration | Existing CSV/LAN regression fixtures plus native export-boundary test | Final backend suite: 47 passed, 0 failed, 0 skipped. Covers restart, durable cursor, ACK/retry/idempotency, bad input and bounded export metadata | Local sockets/processes are tested; two physical machines, real egress and actual Telegram are unverified | Close AQUA; retain source files and private queues |
| G4 RPM / native controls | `packaging/`, icon and desktop launcher | RPM builds; dependencies present on Fedora 44; desktop file validates; extracted RPM launcher reports 0.6.0; GTK test clicks pause/resume/export, reads CSV and waits for owned backend exit | Private RPM DB transaction failed with permission denied in this environment. Payload deployment and launch passed; system DNF installation is not claimed. RPM unsigned | `sudo dnf remove aqua-command-desktop` after an actual install; user state is retained |
| G5 delivery review | `README.md`, `PLAN.md`, this report, `releases/` | Independent read-only review: no unresolved critical/important findings. New public files checked for plant samples, private paths, enrollment and runtime data. Binary SHA256 supplied | Branch publication is verified separately by comparing local and origin commit IDs; release is a LAB build | Revert the feature commit; no force push or production deployment required |

## Reproduce

```sh
npm test --prefix backend
python3 -B -m unittest discover -s desktop/tests -v
desktop-file-validate packaging/org.aquacommand.Desktop.desktop
bash packaging/build-rpm.sh /absolute/owned-build-directory
# A working native GTK display is required for this test:
python3 -B desktop/ui_test.py
```

Native integration assertions: GTK4 widgets, five generic LAB tags, real backend process, received snapshot, acknowledged local delivery, pause and resume, private CSV file, read-only status, no UI HTTP listener, owned process cleanup. Source/input tests verify byte and modification-time preservation.

## Read-only boundary and limitations

Only AQUA-owned local state, spool, settings and export files are writable. WinCC/PLC source content is read-only. No tag-write API, physical pump controls, scans, Internet sharing, firewall/NAT/bridge changes or production access were used. Default fixture and Telegram sink stay labelled LAB/dry-run. Generic disabled WinCC script is an unexecuted source template, not a verified WinCC integration.

CSV export is a recent retained-history view, capped at 2,000 events / 250 KB of payload. Partial views are explicitly reported. Source retains up to 2,000 ACKed events and 10,000 pending events; pending quota errors preserve unACKed records. The 64 MiB database quota and finite Gateway/Central ledgers are LAB limits. Physical power-loss behavior has not been tested.

Changing input settings switches to a separate profile without deleting the previous profile. Previous pending records resume when reopening that profile. Removing the RPM does not delete these queues; never delete them as a routine rollback. No `.exe` or Windows 11 installation is claimed.
