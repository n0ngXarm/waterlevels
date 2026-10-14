#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Safe Lab Data Reset Script
# Purges ephemeral simulation state while creating a safety backup first
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORCE="${1:-}"

if [ "${FORCE}" != "--force" ] && [ "${FORCE}" != "-f" ]; then
    echo "====================================================================="
    echo "  [WARNING] You are about to RESET all ephemeral lab data!"
    echo "  This will purge:"
    echo "    - Zone A Collector Buffer (data/*.db)"
    echo "    - Aqua Command State & Alert History (aqua-command/storage/state.json*)"
    echo "====================================================================="
    read -r -p "Are you sure you want to proceed? [y/N]: " CONFIRM
    case "${CONFIRM}" in
        [yY][eE][sS]|[yY])
            ;;
        *)
            echo "==> Reset cancelled by user."
            exit 0
            ;;
    esac
fi

echo "==> [1/3] Creating automatic pre-reset safety backup..."
"${BASE_DIR}/scripts/dev_backup.sh"

QUARANTINE_DIR="${BASE_DIR}/backups/quarantine_$(date +'%Y%m%d_%H%M%S')"
mkdir -p "${QUARANTINE_DIR}"

echo "==> [2/3] Quarantining simulation databases and state files to ${QUARANTINE_DIR}..."
for f in "${BASE_DIR}/data/zone_a_buffer.db"* "${BASE_DIR}/data/simulated_collector.db"* "${BASE_DIR}/aqua-command/storage/state.json"*; do
    if [ -f "${f}" ]; then
        mv "${f}" "${QUARANTINE_DIR}/"
    fi
done

echo "==> [3/3] Re-initializing empty storage structure..."
mkdir -p "${BASE_DIR}/data" "${BASE_DIR}/aqua-command/storage"
chmod -R u+rwx "${BASE_DIR}/data" "${BASE_DIR}/aqua-command/storage"

echo "==> [SUCCESS] Lab environment reset to clean baseline."
