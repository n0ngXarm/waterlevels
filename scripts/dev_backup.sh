#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Automated Backup Script
# Creates a compressed, checksummed tarball of databases and persistent state
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BASE_DIR}/backups"
TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
BACKUP_FILE="${BACKUP_DIR}/aqua_backup_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "==> [AQUA COMMAND] Initiating system state backup at ${TIMESTAMP}..."

# Ensure target directories exist before packaging
mkdir -p "${BASE_DIR}/data" "${BASE_DIR}/aqua-command/storage" "${BASE_DIR}/config"

# Archive data, storage, and config
tar -czf "${BACKUP_FILE}" \
    -C "${BASE_DIR}" \
    data \
    aqua-command/storage \
    config

# Generate SHA256 Checksum
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${BACKUP_FILE}" > "${BACKUP_FILE}.sha256"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${BACKUP_FILE}" > "${BACKUP_FILE}.sha256"
fi

SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
echo "==> [SUCCESS] Backup created successfully:"
echo "    Archive:  ${BACKUP_FILE} (${SIZE})"
if [ -f "${BACKUP_FILE}.sha256" ]; then
    echo "    Checksum: $(cat "${BACKUP_FILE}.sha256")"
fi
