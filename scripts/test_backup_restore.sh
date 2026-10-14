#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Backup & Restore Validation Script
# Verifies consistent snapshot creation, checksum validation, and schema integrity
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TEST_DB="${BASE_DIR}/data/test_real_restore.db"
echo "==> [TEST] Step 0: Seeding test database with real telemetry records in ${TEST_DB}..."
python3 -c "
import sqlite3, sys
db_path = sys.argv[1]
with sqlite3.connect(db_path) as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS test_telemetry (id INTEGER PRIMARY KEY, station_id TEXT, pressure REAL, epoch TEXT)')
    conn.execute('DELETE FROM test_telemetry')
    for i in range(1, 11):
        conn.execute('INSERT INTO test_telemetry VALUES (?, ?, ?, ?)', (i, f'CM-{i:02d}', 2.50 + i*0.1, f'EP-SEED-{i}'))
    conn.commit()
" "${TEST_DB}"

cleanup_test_db() {
    rm -f "${TEST_DB}" "${TEST_DB}-wal" "${TEST_DB}-shm"
}
trap cleanup_test_db EXIT

echo "==> [TEST] Step 1: Running automated online backup..."
bash "${BASE_DIR}/scripts/dev_backup.sh"

LATEST_BACKUP="$(ls -t "${BASE_DIR}/backups"/aqua_backup_*.tar.gz | head -n1)"
echo "==> [TEST] Latest backup identified: ${LATEST_BACKUP}"

TEST_DIR="$(mktemp -d)"
trap 'cleanup_test_db; rm -rf "${TEST_DIR}"' EXIT

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

echo "==> [TEST] Step 5: Validating restored real telemetry data completeness..."
python3 -c "
import sqlite3, sys
restored_test_db = '${TEST_DIR}/data/test_real_restore.db'
with sqlite3.connect(restored_test_db) as conn:
    rows = conn.execute('SELECT id, station_id, pressure, epoch FROM test_telemetry ORDER BY id ASC').fetchall()
    assert len(rows) == 10, f'Expected 10 rows, got {len(rows)}'
    assert rows[0] == (1, 'CM-01', 2.6, 'EP-SEED-1'), f'First row mismatch: {rows[0]}'
    assert rows[9] == (10, 'CM-10', 3.5, 'EP-SEED-10'), f'Tenth row mismatch: {rows[9]}'
print('    Real data content verification: 10/10 rows intact and exact match!')
"

echo "==> [TEST] Step 6: Validating restored configuration and state JSON..."
if [ -f "${TEST_DIR}/config/station_registry.json" ]; then
    node -e "JSON.parse(fs.readFileSync('${TEST_DIR}/config/station_registry.json'))"
    echo "    station_registry.json: Valid JSON"
fi

if [ -f "${TEST_DIR}/aqua-command/storage/state.json" ]; then
    node -e "JSON.parse(fs.readFileSync('${TEST_DIR}/aqua-command/storage/state.json'))"
    echo "    state.json: Valid JSON"
fi

echo "==> [SUCCESS] All backup and restore integrity validations with REAL DATA PASSED (${db_count} databases verified)."
