#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Automated Backup Script
# Creates a compressed, checksummed tarball of databases and persistent state
# Uses SQLite Online Backup API (.backup) to guarantee 0% page-tearing
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${AQUA_BACKUP_DIR:-${BASE_DIR}/backups}"
DATA_DIR="${AQUA_DATA_DIR:-${BASE_DIR}/data}"
STORAGE_DIR="${AQUA_STORAGE_DIR:-${BASE_DIR}/aqua-command/storage}"
CONFIG_DIR="${AQUA_CONFIG_DIR:-${BASE_DIR}/config}"

TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
BACKUP_FILE="${BACKUP_DIR}/aqua_backup_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "==> [AQUA COMMAND] Initiating system state backup at ${TIMESTAMP}..."

# Ensure target directories exist
mkdir -p "${DATA_DIR}" "${STORAGE_DIR}" "${CONFIG_DIR}"

# Staging directory for consistent snapshots
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGE_DIR}"' EXIT

mkdir -p "${STAGE_DIR}/data" "${STAGE_DIR}/aqua-command/storage" "${STAGE_DIR}/config"

# Copy config directory
if [ -d "${CONFIG_DIR}" ]; then
    cp -a "${CONFIG_DIR}"/* "${STAGE_DIR}/config/" 2>/dev/null || true
fi

# Copy JSON state files safely
if [ -f "${STORAGE_DIR}/state.json" ]; then
    cp -a "${STORAGE_DIR}/state.json" "${STAGE_DIR}/aqua-command/storage/"
fi

# Use SQLite Online Backup API for all active/dormant SQLite databases
shopt -s nullglob
db_files=("${DATA_DIR}"/*.db "${STORAGE_DIR}"/*.db)
shopt -u nullglob

for db in "${db_files[@]}"; do
    if [ -f "$db" ]; then
        db_basename="$(basename "$db")"
        if [[ "$db" == "${DATA_DIR}"/* ]]; then
            dest_db="${STAGE_DIR}/data/${db_basename}"
        else
            dest_db="${STAGE_DIR}/aqua-command/storage/${db_basename}"
        fi
        mkdir -p "$(dirname "${dest_db}")"
        echo "==> [SQLITE BACKUP] Creating online consistent backup: ${db_basename} -> ${dest_db}..."
        python3 -c "
import sqlite3, sys
src_path, dest_path = sys.argv[1], sys.argv[2]
try:
    with sqlite3.connect(src_path) as src_conn:
        try:
            src_conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception as ce:
            print(f'==> [WARN] WAL checkpoint notice: {ce}', file=sys.stderr)
        with sqlite3.connect(dest_path) as dest_conn:
            src_conn.backup(dest_conn)
        with sqlite3.connect(dest_path) as chk_conn:
            res = chk_conn.execute('PRAGMA integrity_check').fetchall()
            if res != [('ok',)]:
                raise RuntimeError(f'Snapshot integrity check failed: {res}')
except Exception as e:
    print(f'==> [ERROR] SQLite Online Backup failed for {src_path}: {e}', file=sys.stderr)
    print(f'==> [FAIL-CLOSED] Refusing raw file copy fallback to prevent page-tearing and corrupted snapshots.', file=sys.stderr)
    sys.exit(1)
" "$db" "$dest_db"
    fi
done

# Archive from staging directory
tar -czf "${BACKUP_FILE}" \
    -C "${STAGE_DIR}" \
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

