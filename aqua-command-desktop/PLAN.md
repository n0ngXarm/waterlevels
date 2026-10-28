# G2 — Native Option B UI foundations and existing bindings

User approval: “go to build program?” following the G1 recommendation for Option B and G2 only. Deliver a native RPM preview of approved UI foundations; do not implement G3–G5/backend gaps. WinCC/OPC/PLC/network access remains unapproved and unavailable.

**Architecture:** Keep existing manual-start app lifecycle and consent, private JSON-lines host, existing engine and all source/cursor/ACK behavior. Add a pure presentation adapter and a native seven-page console using only existing fields. Unknown capabilities are visibly unavailable. Package metadata changes only to deliver the new UI preview, with no dependency changes.

**Spec:** G1_DESIGN_PROPOSAL.md and DATA_BINDING_MATRIX.md in the task's outputs/aqua-uiux-v2.1-g0-g1; original v2.1 pack read during G0/G1.

## Constraints

- No backend/API/DB/config schema/IPC/consent implementation changes. Protected engine hashes captured under work/g2-build.
- No startup worker, read, scan or egress. Capture/send remain independent manual approvals; remembered scope never autoruns.
- Network page shows configured loopback endpoints, not invented NIC IP or hostname. One local Agent, Gateway and Central are logical roles on one host.
- Raw value, normalized state, source mode, quality and freshness are distinct. Central ACK is not Telegram delivery.
- Existing supported CSV/LAB source settings work; new item rules/browse/test-read/audit export stay disabled with reasons.

## Tasks

- [x] Write failing tests for idle/unknown, partial counts, stale reporter/egress, FILE provenance, BAD/stale/mapping, receipt semantics and secret exclusion. Implement desktop/presentation.py as pure data transformation.
- [x] Add desktop/console.py, integrate Option B seven-page shell into app.py and style.css. Retain lifecycle and permission methods. Add display-only filter/freeze and safe endpoint copy.
- [x] Exercise all seven pages, manual consent flow, freeze without stopping collection, revoke/source changes and desktop layouts. Preserve backend functional suite.
- [x] Review diff for read-only/scope regressions, fix serious findings, verify engine hashes.
- [x] Build version0.8 G2 preview RPM, test packaged payload and provide operator guide, screenshots and stage report. Stop before G3.

## Public delivery

No plant-specific samples/tags, secrets, generated enrollment/DBs or private workstation paths in commits/package. Keep work on existing codex/aqua-native-desktop-rpm feature branch; no main merge/production deploy. Reverting G2 must not delete user queues or change WinCC/source input.

G2 verification:50 backend tests,23 Python tests, installed-payload native workflow and56 actual native layout combinations passed. All38 protected engine files unchanged. G3–G5 remain unapproved; no Runtime/physical-LAN/Windows/real-Telegram acceptance claim.
