Name: aqua-command-desktop
Version: 0.6.0
Release: 1%{?dist}
Summary: Native read-only AQUA snapshot collector and LAN relay
License: MIT
URL: https://github.com/n0ngXarm/waterlevels
Source0: %{name}-%{version}.tar.gz
BuildArch: noarch
Prefix: /usr
Requires: python3 >= 3.11
Requires: python3-gobject >= 3.42
Requires: gtk4 >= 4.10
Requires: nodejs22-bin >= 22.13
Requires: hicolor-icon-theme
%global debug_package %{nil}
%global _build_id_links none
%description
Native GTK4 desktop frontend for read-only local runtime CSV collection,
durable queues and authenticated forwarding through explicitly enrolled
LAB gateways. No browser, webview or dashboard HTTP listener is launched.
WinCC/PLC writes are not supported. Default LAB fixture and Telegram dry-run.
%prep
%setup -q
%build
# Python/JavaScript source uses distribution runtimes; no native compilation.
%install
mkdir -p %{buildroot}%{_datadir}/%{name}/desktop
mkdir -p %{buildroot}%{_datadir}/%{name}/backend/bin
mkdir -p %{buildroot}%{_bindir} %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
mkdir -p %{buildroot}%{_datadir}/%{name}/backend/src
cp -a backend/src/lan %{buildroot}%{_datadir}/%{name}/backend/src/
install -m 644 backend/package.json %{buildroot}%{_datadir}/%{name}/backend/
# Service location is fixed by the supervisor; do not install old web entry points.
install -m 644 backend/bin/aqua-service.js %{buildroot}%{_datadir}/%{name}/backend/bin/
install -m 644 desktop/app.py desktop/client.py desktop/model.py desktop/host.mjs desktop/style.css %{buildroot}%{_datadir}/%{name}/desktop/
install -m 755 packaging/aqua-command %{buildroot}%{_bindir}/aqua-command
install -m 644 packaging/org.aquacommand.Desktop.desktop %{buildroot}%{_datadir}/applications/
install -m 644 packaging/icons/org.aquacommand.Desktop.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/
%files
%license LICENSE
%doc README.md VERIFICATION.md
%{_bindir}/aqua-command
%{_datadir}/%{name}
%{_datadir}/applications/org.aquacommand.Desktop.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.aquacommand.Desktop.svg
%changelog
* Wed Oct 28 2026 AQUA COMMAND contributors - 0.6.0-1
- Native GTK4 frontend with private IPC, strict read-only input and RPM launcher.
