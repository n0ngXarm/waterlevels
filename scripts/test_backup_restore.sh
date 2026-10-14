#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Backup & Restore Validation Script
# Verifies consistent snapshot creation, checksum validation, and schema integrity
# Using 100% isolated sandbox directories to protect project data
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Step 0: Create isolated sandbox directory (Zero pollution of project data directory)
SANDBOX_DIR="$(mktemp -d)"
trap 'rm -rf "${SANDBOX_DIR}"' EXIT

SANDBOX_SRC_DATA="${SANDBOX_DIR}/src_data"
SANDBOX_SRC_STORAGE="${SANDBOX_DIR}/src_storage"
SANDBOX_SRC_CONFIG="${SANDBOX_DIR}/src_config"
SANDBOX_BACKUPS="${SANDBOX_DIR}/backups"
SANDBOX_RESTORE="${SANDBOX_DIR}/restore"

mkdir -p "${SANDBOX_SRC_DATA}" "${SANDBOX_SRC_STORAGE}" "${SANDBOX_SRC_CONFIG}" "${SANDBOX_BACKUPS}" "${SANDBOX_RESTORE}"

echo "==> [TEST] Step 0: Initializing isolated test sandbox at ${SANDBOX_DIR}..."
echo "    Project data directory (${BASE_DIR}/data) will remain untouched."

# Copy real config and state into sandbox
cp -a "${BASE_DIR}/config"/* "${SANDBOX_SRC_CONFIG}/" 2>/dev/null || true
if [ -f "${BASE_DIR}/aqua-command/storage/state.json" ]; then
    cp -a "${BASE_DIR}/aqua-command/storage/state.json" "${SANDBOX_SRC_STORAGE}/"
else
    echo '{"alerts":[],"queue":[]}' > "${SANDBOX_SRC_STORAGE}/state.json"
fi

# Seed test database with real telemetry records inside sandbox
SANDBOX_TEST_DB="${SANDBOX_SRC_DATA}/test_real_restore.db"
echo "    Seeding test database with real telemetry records: ${SANDBOX_TEST_DB}..."
python3 -c "
import sqlite3, sys
db_path = sys.argv[1]
with sqlite3.connect(db_path) as conn:
    conn.execute('CREATE TABLE test_telemetry (id INTEGER PRIMARY KEY, station_id TEXT, pressure REAL, epoch TEXT)')
    for i in range(1, 11):
        conn.execute('INSERT INTO test_telemetry VALUES (?, ?, ?, ?)', (i, f'CM-{i:02d}', 2.50 + i*0.1, f'EP-SEED-{i}'))
    conn.commit()
" "${SANDBOX_TEST_DB}"

# Step 1: Run automated online backup pointing strictly to sandbox
echo "==> [TEST] Step 1: Running automated online backup in isolated sandbox..."
AQUA_DATA_DIR="${SANDBOX_SRC_DATA}" \
AQUA_STORAGE_DIR="${SANDBOX_SRC_STORAGE}" \
AQUA_CONFIG_DIR="${SANDBOX_SRC_CONFIG}" \
AQUA_BACKUP_DIR="${SANDBOX_BACKUPS}" \
bash "${BASE_DIR}/scripts/dev_backup.sh"

LATEST_BACKUP="$(ls -t "${SANDBOX_BACKUPS}"/aqua_backup_*.tar.gz | head -n1)"
echo "==> [TEST] Generated sandbox backup: ${LATEST_BACKUP}"

# Step 2: Verify Checksum
echo "==> [TEST] Step 2: Verifying SHA256 checksum..."
if [ -f "${LATEST_BACKUP}.sha256" ]; then
    cd "${SANDBOX_BACKUPS}"
    sha256sum -c "$(basename "${LATEST_BACKUP}.sha256")"
    cd "${BASE_DIR}"
fi

# Step 3: Restore into isolated sandbox restore directory
echo "==> [TEST] Step 3: Restoring into isolated sandbox directory: ${SANDBOX_RESTORE}..."
tar -xzf "${LATEST_BACKUP}" -C "${SANDBOX_RESTORE}"

# Step 4: Validate SQLite Database Integrity
echo "==> [TEST] Step 4: Validating SQLite database integrity across all restored DBs..."
shopt -s nullglob
restored_dbs=("${SANDBOX_RESTORE}"/data/*.db "${SANDBOX_RESTORE}"/aqua-command/storage/*.db)
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

# Step 5: Validate Restored Real Telemetry Records
echo "==> [TEST] Step 5: Validating restored real telemetry data completeness..."
python3 -c "
import sqlite3, sys
restored_test_db = '${SANDBOX_RESTORE}/data/test_real_restore.db'
with sqlite3.connect(restored_test_db) as conn:
    rows = conn.execute('SELECT id, station_id, pressure, epoch FROM test_telemetry ORDER BY id ASC').fetchall()
    assert len(rows) == 10, f'Expected 10 rows, got {len(rows)}'
    assert rows[0] == (1, 'CM-01', 2.6, 'EP-SEED-1'), f'First row mismatch: {rows[0]}'
    assert rows[9] == (10, 'CM-10', 3.5, 'EP-SEED-10'), f'Tenth row mismatch: {rows[9]}'
print('    Real data content verification: 10/10 rows intact and exact match!')
"

# Step 6: Validate Restored Configuration and State JSON
echo "==> [TEST] Step 6: Validating restored configuration and state JSON..."
if [ -f "${SANDBOX_RESTORE}/config/station_registry.json" ]; then
    node -e "JSON.parse(fs.readFileSync('${SANDBOX_RESTORE}/config/station_registry.json'))"
    echo "    station_registry.json: Valid JSON"
fi

if [ -f "${SANDBOX_RESTORE}/aqua-command/storage/state.json" ]; then
    node -e "JSON.parse(fs.readFileSync('${SANDBOX_RESTORE}/aqua-command/storage/state.json'))"
    echo "    state.json: Valid JSON"
fi

echo "==> [SUCCESS] All backup and restore integrity validations in isolated sandbox PASSED (${db_count} databases verified)."
echo "    Sandbox successfully cleaned up. Project data directory untouched."
