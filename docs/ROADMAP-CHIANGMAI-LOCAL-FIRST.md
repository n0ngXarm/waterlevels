# AQUA COMMAND — Chiang Mai Local-First Roadmap

**Status:** PROPOSED — pending PWA Chiang Mai (Special Class) IT/OT approval  
**Repository:** https://github.com/n0ngXarm/waterlevels  
**Reviewed source:** main @ 9164258261f3b7d4dc3807b58058b099b0ceebbd (14 Oct 2026)  
**Scope:** only Chiang Mai branch stations/data specifically authorized by the owner; not every site in the province.  
**Main reference:** Two-zone diagram agreed in planning: Zone A → Tailscale VPN → Zone B → Dashboard, Alerts, optional CCTV.

This is a proposal for presenting to the organization and directing implementation. The repository is not proof of a live plant connection or official authorization.

## 1. Architecture — exactly 2 zones

| Zone | Components | Responsibility |
|---|---|---|
| **A — Existing station** | Existing SCADA/PLC, sensors, alarm state, optional existing NVR/CCTV; **approved read-only collector**; existing uplink or 4G/5G SIM router | Read permitted values from current equipment without changing plant controls. Buffer readings when connectivity is lost. |
| **Link — Tailscale** | Tailscale client on collector/gateway and central server, managed tailnet, restrictive grants/ACL | Encrypted access across SIM/Internet; connect only source to approved central ingest endpoint. Not a separate site or an air-gapped LAN. |
| **B — Central office / local server** | Ingestion/validation, persistent database, incident engine, Dashboard, backup, authorized outbound notification gateway | Receive and store site values, process abnormal conditions, show operations dashboards on LAN, notify designated staff. |

**Simplified data flow**

1. Zone A: Existing PLC/SCADA or approved export → read-only collector.
2. Zone A uplink: collector → 4G/5G SIM router if wired network is unavailable.
3. Secure transport: Tailscale connection from collector to Zone B server (Internet required).
4. Zone B ingest: validate station identity, point/units/time/quality; deduplicate; store locally.
5. Zone B logic: thresholds, incidents, acknowledgement, audit trail and alert queue.
6. Users: office LAN dashboard; approved remote users via Tailscale plus app authentication.
7. Telegram: Zone B sends outbound HTTPS only **if** IT/OT approves it; do not provide inbound public control routes.
8. CCTV: optional read-only NVR or approved snapshot/stream proxy; local viewing/storage; no automatic image exports.

**Why not install Tailscale repeatedly?** Install/enroll once on approved hosts and run it as an OS service. Router SIM supplies Internet; Tailscale on router is optional, not required when the collector runs it. LAN users usually do not need Tailscale. Restrict network reachability to minimum ports and peers.

**Important caveat:** Tailscale uses Internet transport and may use coordination/relay services. Local database storage does not mean every packet remains in local LAN. If the authority prohibits any third-party transport, consider organization-approved private APN/IPsec/MPLS and local-only notifications instead.

## 2. Repository reality check (before new implementation)

| Current file/module | Verified purpose | Next change |
|---|---|---|
| aqua-command/server.mjs, rules.mjs | Node dashboard, telemetry ingest, event/rule processing, SSE, demo stations | Preserve functions, harden authentication and adapt to authorized Chiang Mai station registry |
| aqua-command/public | Thai dashboard UI | Simplify overview; map only verified service areas/stations |
| src/pwa_client.py, src/monitor_service.py | Poll public-facing PWA outage and water quality feeds | Keep as clearly labeled OPTIONAL external feed; do not confuse with authorized station telemetry |
| src/aqua_bridge.py | Maps externally sourced RTU values to demonstration station IDs | Replace nationwide keyword-to-station mapping with owner-approved stable station/point IDs |
| src/telegram_bot.py, src/telegram_notifier.py | Telegram bot and notifications | Reuse; add local incident source and approved recipients |
| src/database.py | Python SQLite storage | Evaluate telemetry/history/incident schema and migrate safely |
| docker-compose.yml | Node dashboard + Python service | Add site-aware deployment profile, bounded LAN binding, backups and observability |
| tests/, aqua-command/tests | Test suites | Keep regression baseline and add end-to-end/field-replay tests |

There is no verified production PLC/SCADA collector, Tailscale field tunnel or CCTV/NVR feed yet in the reviewed snapshot. The current 12-node/nationwide demo and public web feeds are not an authorized Zone A implementation.

### Security hold — fix before connecting to real sites

- A public tracked .env.example contains a token-shaped Telegram credential and chat ID. If these are real, rotate/revoke the bot token immediately, remove actual secrets from tracked files and address exposed Git history as appropriate. Never reuse a leaked secret.
- src/aqua_bridge.py contains a hardcoded fallback admin API key. Remove hardcoded defaults; fail closed without a secure configured key and rotate deployed matching values.
- Sensitive read endpoints, including /api/state and /api/stream, need authentication/authorization; current write-only API-key protection is insufficient for private operational data.
- Restrict dashboard port exposure to approved internal networks. Do not publish port 8787 to the general Internet.
- Engineering must approve per-site thresholds; demo threshold examples cannot be treated as official limits.

**Mandatory Gate S0:** Secrets remediated + written owner approval for read-only OT access and remote transport. No real-site network contact before that approval.

## 3. Eight-week pilot roadmap

Durations are planning estimates; adjust once actual site interfaces and permissions are confirmed. Start with **one station** rather than all Chiang Mai sites.

### Week 1 · P0 — On-site survey, access permissions, baseline
**Tasks:** Agree on one station; confirm vendor/models, existing PLC/SCADA/NVR network architecture, authorized read/export endpoint, sample measurement list, Internet/SIM availability, central-host ownership, staff permissions and escalation contacts. Inventory usable equipment before purchases. Baseline the repository and current tests.

**Deliverables:** signed scope, point/tag registry template (IDs, units, timestamps, sampling), network/permissions matrix, dependency and risk list, baseline test report.

**Gate G0:** Site IT and OT jointly approve read-only access path and the pilot point list.

### Week 2 · P1 — Zone A/B network proof of concept
**Tasks:** Set up the existing approved collector or industrial PC; use SIM router only where required; enroll collector + Zone B server in Tailscale; configure tailnet ACL/grants to ONLY the ingest service; MFA/admin ownership, boot auto-start, time sync, tunnel reconnect and device revocation. Test SIM CGNAT and coverage.

**Deliverables:** redacted network diagram, one approved field-to-center authenticated connection, firewall and identity rules, disconnect/reconnect evidence.

**Gate G1:** Collector reaches central ingest securely; no route or command access from center to plant controls.

### Week 3 · P2 — First real read-only telemetry
**Tasks:** Determine actual authorized protocol: OPC UA read subscription, vendor API/export, Modbus read-only registers, or other documented interface. Do not scan or write to production PLCs. Add adapter, local disk buffering, delivery IDs, provenance, timestamp, units and quality flags. Separate existing public PWA feed.

**Deliverables:** verified real reading from a pilot source, adapter contract, mapping table, replay test.

**Gate G2:** At least one authorized measurement on the local server matches the field reference value and unit at agreed sample time.

### Week 4 · P3 — Central data ingestion and dashboard
**Tasks:** Build persistent site/station/point registry and validated ingest; separate LIVE/DEMO; show freshness, unknown/stale/offline distinctly; add history and a simple station details view. Preserve working Node/Python features. Apply internal auth to reads and writes; backup and restore.

**Deliverables:** live Chiang Mai pilot dashboard (desktop/mobile), telemetry history, local storage, audit metadata.

**Gate G3:** Dashboard/API/database agree on values, timestamps, source and quality; no fake station counts in LIVE mode.

### Week 5 · P4 — Alarm engine and Telegram policy
**Tasks:** Get operator-approved per-point thresholds, hysteresis, debounce, offline/stale cases, maintenance windows, priority levels, ACK/resolve lifecycle, event dedup, durable notification queue, retries and delivery audit. Local alarm works without Telegram. Use Telegram only following approved outbound-Internet/data-sharing policy.

**Deliverables:** alarm matrix, incident timeline, notification templates, mock Telegram tests, restricted production test if approved.

**Gate G4:** Normal → Warning → Critical → Resolved transitions produce traceable incidents without flooding after process/tunnel restart.

### Week 6 · P5 — Optional CCTV integration
**Tasks:** Verify permission, NVR model, RTSP/ONVIF/vendor API and topology. Use authorized NVR read-only API or snapshot proxy with RBAC; prevent direct web client access to plant CCTV VLAN; define retention and privacy rules. Disable this module where permission is absent.

**Deliverables:** camera-to-station map and authorized view/snapshot demo (if feasible), bandwidth/cost estimate.

**Gate G5:** Authorized staff can view agreed footage or snapshot; unauthorized access denied; zero control-setting changes.

### Week 7 · P6 — Reliability, security and operator acceptance
**Tasks:** Verify loss of SIM, broken VPN, collector reboot, invalid timestamps, duplicate/out-of-order packets, disk full, local DB restore, telegram outage, role denial, stale sensor, and current application regression tests. Document maintenance, rollback and support.

**Deliverables:** signed test matrix, evidence/screenshots, security review, runbooks and restore drill.

**Gate G6:** No unresolved critical safety/security failure; pilot owner approves documented acceptance criteria.

### Week 8 · P7 — Controlled pilot go-live and handover
**Tasks:** Schedule safe release; take verified backups; run supervised pilot and review incident count/false alarms/uptime; train operators; establish owner of SIM, tailnet, server, Bot credentials, backups and emergency escalation. Expand only by approved change.

**Deliverables:** release tag, pilot report, operational handover, next-station rollout backlog.

**Gate G7:** Formal pilot sign-off and named operational owners. Broader deployment needs separate authorization.

## 4. Data and Alert contracts (proposed)

**Telemetry payload:** station_id; point_id; observed_at; received_at; value; unit; quality; source_id; unique_sample_id; source_mode (LIVE/DEMO). Verify data range and tags against owner-approved registry. Do not replace missing data with zero or infer health from connectivity alone. Use durable at-least-once forwarding + deduplication and preserve the original reading time.

**Incident:** incident_id; station_id; point_id; rule_version; severity; opened_at; last_transition_at; ack_by/at; resolved_at; dedup_key; notification_delivery_status. Store event transitions append-only where practicable.

**Telegram:** minimum approved metadata only (station, event, severity, time, incident_id). Exclude sensitive topology, credentials, private LAN IPs and CCTV images by default. External phone users cannot open a LAN-only dashboard link without authorized VPN and app login.

## 5. Acceptance / verification checklist (all unverified until tested)

| Case | Expected evidence |
|---|---|
| Correct telemetry | 10 agreed points match field reference values, unit, source and observed timestamp |
| OT read-only | No PLC write/control ability from monitoring components; signed by OT representative |
| Link loss and recovery | Missing communication raises stale/offline; buffered samples replay without duplicate incidents |
| Alarm state change | Warning → Critical → Resolved with ACK and delivery audit; no spam storms |
| Telegram blocked | Local monitoring remains usable, queued delivery status is visible and retries bounded |
| Server restart | App and DB survive; queue persists; verified backup restore succeeds |
| Privacy/security | Unauthorized read APIs/SSE and camera stream blocked; revoked Tailscale peer denied |
| UI | Live/demo explicit; responsive desktop/mobile; shows no-data honestly |
| Optional CCTV | Authorized NVR read-only access only; retention reviewed by site |

Numeric latency, retention and availability SLOs must be agreed using measured on-site intervals and coverage; none can be claimed as met today.

## 6. Questions to resolve with PWA before the pilot

1. Which **one** station is the authorized pilot and who signs for the OT/IT change?
2. What data-export interface is already supported (vendor, version, endpoint, read-only tags)?
3. Is there an existing PC/gateway/uplink to reuse? Who owns the SIM if needed?
4. Does the IT/OT policy permit **Tailscale over Internet**, possibly via relay/coordination, or mandate private APN/IPsec?
5. Where will the Zone B local server, backup and monitoring operate? Who has accounts?
6. Which engineering alarm thresholds and recipients are approved?
7. Can Zone B send operational incident metadata to Telegram? What is permitted to leave the organization?
8. May the team access NVR streams/snapshots, and what are the privacy/retention rules?

## 7. GitHub/Gemini working agreement

- This document is a **docs-only change on a separate branch**; do NOT force-push or modify the main branch while Gemini is actively coding.
- Gemini should rebase/compare against current main, inspect existing tests and provide baseline test results before implementation. Work per phase on independent feature branches and draft PRs.
- Preserve existing features with regression tests. Separate optional public-outage feed from actual OT telemetry using explicit source/provenance labels.
- Do not mark a phase PASS based on mock data alone. Field acceptance requires field evidence and site sign-off.
- Each PR should include change summary, data flow impact, risk, tests, rollback, and affected interfaces.

### Candidate backlog (propose as issues only when owner approves)
SEC-01 Credential rotation + protect read APIs; SITE-01 survey and permission matrix; VPN-01 Tailscale/SIM proof; OT-01 read-only adapter; DATA-01 local persistence/buffering; UI-01 Chiang Mai site dashboard; ALERT-01 incidents and notification egress; CCTV-01 optional NVR; OPS-01 restore and acceptance.

## 8. Explicit out-of-scope for first deployment

No new automation of pumps or valves; no PLC writes or firmware changes; no replacement of existing plant controls; no bypassing PWA authentication; no assumption of all Chiang Mai stations having accessible data; no public Internet exposure of operational APIs or video.

**FIRST ACTION:** Request the approved point list and read-only connection method for one pilot station. The first meaningful milestone is one verifiable, actual plant measurement received into Zone B without affecting plant operations.
