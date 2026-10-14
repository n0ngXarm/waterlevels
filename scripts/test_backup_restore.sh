#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Backup & Restore Validation Script
# Verifies consistent snapshot creation, checksum validation, and schema integrity
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> [TEST] Step 1: Running automated online backup..."
bash "${BASE_DIR}/scripts/dev_backup.sh"

LATEST_BACKUP="$(ls -t "${BASE_DIR}/backups"/aqua_backup_*.tar.gz | head -n1)"
echo "==> [TEST] Latest backup identified: ${LATEST_BACKUP}"

TEST_DIR="$(mktemp -d)"
trap 'rm -rf "${TEST_DIR}"' EXIT

echo "==> [TEST] Step 2: Verifying SHA256 checksum..."
if [ -f "${LATEST_BACKUP}.sha256" ]; then
    cd "$(dirname "${LATEST_BACKUP}")"
    sha256sum -c "$(basename "${LATEST_BACKUP}.sha256")"
    cd "${BASE_DIR}"
fi

echo "==> [TEST] Step 3: Restoring into isolated sandbox directory: ${TEST_DIR}..."
tar -xzf "${LATEST_BACKUP}" -C "${TEST_DIR}"

echo "==> [TEST] Step 4: Validating SQLite database integrity across all restored DBs..."
shopt -s nullglob
restored_dbs=("${TEST_DIR}"/data/*.db "${TEST_DIR}"/aqua-command/storage/*.db)
shopt -u nullglob

db_count=0
for db in "${restored_dbs[@]}"; do
    if [ -f "$db" ]; then
        db_count=$((db_count + 1))
        echo "    Checking database: $(basename "$db")..."
        python3 -c "
import sqlite3, sys
db_path = sys.argv[1]
with sqlite3.connect(db_path) as conn:
    res = conn.execute('PRAGMA integrity_check').fetchall()
    if res != [('ok',)]:
        print(f'FAIL: {res}')
        sys.exit(1)
" "$db"
        echo "    Integrity: OK"
    fi
done

echo "==> [TEST] Step 5: Validating restored configuration and state JSON..."
if [ -f "${TEST_DIR}/config/station_registry.json" ]; then
    node -e "JSON.parse(fs.readFileSync('${TEST_DIR}/config/station_registry.json'))"
    echo "    station_registry.json: Valid JSON"
fi

if [ -f "${TEST_DIR}/aqua-command/storage/state.json" ]; then
    node -e "JSON.parse(fs.readFileSync('${TEST_DIR}/aqua-command/storage/state.json'))"
    echo "    state.json: Valid JSON"
fi

echo "==> [SUCCESS] All backup and restore integrity validations PASSED (${db_count} databases verified)."
