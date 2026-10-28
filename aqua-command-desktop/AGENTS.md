# AQUA native desktop scope

User-authorized rebuild: native desktop frontend and RPM delivery, not a website. Continue the existing read-only CSV/SQLite/authenticated-LAN backend. No browser/webview, no UI HTTP listener, no website deployment. GTK4 frontend talks to the private owned Node host over stdin/stdout.

WinCC/PLC access remains strictly READ ONLY. No tag writes, PLC commands, reverse-control channel, scans, routing/NAT/bridge/firewall changes, production access or actual Telegram sends during development. Local AQUA spool/config/export writes are allowed only in owned storage outside the source. Retain cursor/ACK/dedup/quality safeguards. Default labelled LAB fixture, Telegram dry-run, loopback transport. Real CSV input is explicitly selected and stays byte-for-byte unchanged.

This repository is public: no original SCADA samples, infrastructure addresses, credentials, generated enrollment, runtime databases, workstation paths or plant-specific tag names in commits/packages. Use generic LAB tags; import actual tag names only into private local configuration at runtime. No fabricated WinCC/Windows/physical-LAN verification claim.

Build and test on Linux first; create a real RPM and test its installed payload. .exe is not claimed built/tested on Linux. Existing web assets are regression fixtures only; exclude them and their entry points from the RPM.
