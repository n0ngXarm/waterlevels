#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Automated Restore Script
# Restores databases and state from a verified backup archive
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BASE_DIR}/backups"

BACKUP_ARCHIVE="${1:-}"

if [ -z "${BACKUP_ARCHIVE}" ]; then
    # Find latest backup
    LATEST="$(ls -t "${BACKUP_DIR}"/aqua_backup_*.tar.gz 2>/dev/null | head -n 1 || true)"
    if [ -z "${LATEST}" ]; then
        echo "==> [ERROR] No backup archive specified and no backups found in ${BACKUP_DIR}"
        echo "    Usage: $0 [path/to/aqua_backup_YYYYMMDD_HHMMSS.tar.gz]"
        exit 1
    fi
    BACKUP_ARCHIVE="${LATEST}"
fi

if [ ! -f "${BACKUP_ARCHIVE}" ]; then
    echo "==> [ERROR] Archive file not found: ${BACKUP_ARCHIVE}"
    exit 1
fi

echo "==> [AQUA COMMAND] Restoring system from archive: ${BACKUP_ARCHIVE}"

# Verify SHA256 Checksum if .sha256 file exists
CHECKSUM_FILE="${BACKUP_ARCHIVE}.sha256"
if [ -f "${CHECKSUM_FILE}" ]; then
    echo "==> Verifying SHA256 integrity..."
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -c "${CHECKSUM_FILE}"
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -c "${CHECKSUM_FILE}"
    fi
    echo "==> [OK] Checksum verified."
else
    echo "==> [WARN] No .sha256 file found. Skipping checksum verification."
fi

# Extract into BASE_DIR
echo "==> Extracting files..."
tar -xzf "${BACKUP_ARCHIVE}" -C "${BASE_DIR}"

# Ensure write permissions
chmod -R u+rw "${BASE_DIR}/data" "${BASE_DIR}/aqua-command/storage" 2>/dev/null || true

echo "==> [SUCCESS] Restore completed successfully."
