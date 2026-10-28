# Native desktop build

Approved scope: native frontend + RPM, read-only WinCC/PLC, publish code/package to origin waterlevels.

- [x] Keep current read-only backend and genericize public fixtures. Run44-test baseline.
- [x] Add a headless status model and private JSON-lines desktop host; no HTTP UI listener. Test lifecycle, pause/export allowlist and source boundaries.
- [x] Build native GTK4 frontend, local input configuration and status/queue/tag/log views. Test UI model/actions and render native window.
- [x] Build relocatable RPM with verified Fedora dependencies, desktop launcher/icon and no web frontend payload. Extract and launch payload for smoke test; a system package transaction is unverified.
- [x] Review and audit public contents/secrets; provide concrete RPM and verification guide.
- Publication target: origin branch `codex/aqua-native-desktop-rpm`. Confirm delivery by comparing the local commit with that remote ref; do not modify production main.
