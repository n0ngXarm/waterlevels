# Operator permission / UX correction

User requirement: actual WinCC Runtime pump tags, strictly read-only. OPC UA is not enabled; do not enable services or modify WinCC. No auto-start or silent LAB substitution. The unimplemented direct Runtime connection stays explicitly unavailable.

- [x] Reproduce auto-start and add independent backend capture/transfer gates.
- [x] Replace startup UX with source/storage/destination review, separate approvals, scoped remember and revoke controls; always require manual start.
- [x] Test idle/cancel/no state writes, queued local capture, separate delivery, revocation and relaunch. Fix review-discovered request/restart races with regressions.
- [x] Build and exercise version0.7 RPM payload; 50 backend tests, 7 Python tests and native installed-payload consent integration pass.
- Delivery target: origin `codex/aqua-native-desktop-rpm`; confirm publication using the remote commit and delivery report.

Real Runtime integration remains a separate pending LAB gate: agree an approved supported read channel, then validate against WinCC V8.1. Do not claim it works from CSV/LAB evidence.
