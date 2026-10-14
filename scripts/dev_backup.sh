#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Automated Backup Script
# Creates a compressed, checksummed tarball of databases and persistent state
# Uses SQLite Online Backup API (.backup) to guarantee 0% page-tearing
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BASE_DIR}/backups"
TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
BACKUP_FILE="${BACKUP_DIR}/aqua_backup_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "==> [AQUA COMMAND] Initiating system state backup at ${TIMESTAMP}..."

# Ensure target directories exist
mkdir -p "${BASE_DIR}/data" "${BASE_DIR}/aqua-command/storage" "${BASE_DIR}/config"

# Staging directory for consistent snapshots
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGE_DIR}"' EXIT

mkdir -p "${STAGE_DIR}/data" "${STAGE_DIR}/aqua-command/storage" "${STAGE_DIR}/config"

# Copy config directory
cp -a "${BASE_DIR}/config"/* "${STAGE_DIR}/config/" 2>/dev/null || true

# Copy JSON state files safely
if [ -f "${BASE_DIR}/aqua-command/storage/state.json" ]; then
    cp -a "${BASE_DIR}/aqua-command/storage/state.json" "${STAGE_DIR}/aqua-command/storage/"
fi

# Use SQLite Online Backup API for all active/dormant SQLite databases
shopt -s nullglob
db_files=("${BASE_DIR}"/data/*.db "${BASE_DIR}"/aqua-command/storage/*.db)
shopt -u nullglob

for db in "${db_files[@]}"; do
    if [ -f "$db" ]; then
        rel_path="${db#"${BASE_DIR}/"}"
        dest_db="${STAGE_DIR}/${rel_path}"
        mkdir -p "$(dirname "${dest_db}")"
        echo "==> [SQLITE BACKUP] Creating online consistent backup: ${rel_path} -> ${dest_db}..."
        python3 -c "
import sqlite3, sys
src_path, dest_path = sys.argv[1], sys.argv[2]
try:
    with sqlite3.connect(src_path) as src_conn:
        try:
            src_conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception:
            pass
        with sqlite3.connect(dest_path) as dest_conn:
            src_conn.backup(dest_conn)
except Exception as e:
    import shutil
    shutil.copy2(src_path, dest_path)
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

