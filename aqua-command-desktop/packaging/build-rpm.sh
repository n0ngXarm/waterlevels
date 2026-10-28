#!/bin/sh
set -eu
aqua_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
aqua_build=${1:?Usage: build-rpm.sh /absolute/build-directory}
mkdir -p "$aqua_build/tmp" "$aqua_build/SOURCES" "$aqua_build/SPECS" "$aqua_build/RPMS" "$aqua_build/SRPMS" "$aqua_build/BUILD" "$aqua_build/BUILDROOT"
aqua_build=$(CDPATH= cd -- "$aqua_build" && pwd)
tar --exclude=.git --exclude=__pycache__ --exclude='*.pyc' --exclude='*.rpm' --exclude=build --exclude=local-data --exclude=node_modules --transform='s,^,aqua-command-desktop-0.8.0/,' -czf "$aqua_build/SOURCES/aqua-command-desktop-0.8.0.tar.gz" -C "$aqua_root" LICENSE README.md VERIFICATION.md backend desktop packaging
cp "$aqua_root/packaging/aqua-command-desktop.spec" "$aqua_build/SPECS/"
rpmbuild --define "_topdir $aqua_build" --define "_tmppath $aqua_build/tmp" -bb "$aqua_build/SPECS/aqua-command-desktop.spec"
