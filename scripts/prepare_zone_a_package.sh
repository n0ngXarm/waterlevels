#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Zone A Standalone Package Creator
# Packages strictly necessary Python collector files for nongserver without Docker
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${BASE_DIR}/dist"
STAGE_DIR="${DIST_DIR}/zone_a_stage"

mkdir -p "${STAGE_DIR}"

echo "==> [1/4] Assembling Zone A collector package structure..."
rm -rf "${STAGE_DIR:?}"/*
mkdir -p "${STAGE_DIR}/src/collector" "${STAGE_DIR}/tools" "${STAGE_DIR}/data"

# Copy python package files
cp "${BASE_DIR}/src/__init__.py" "${STAGE_DIR}/src/"
cp "${BASE_DIR}/src/collector/__init__.py" "${STAGE_DIR}/src/collector/"
cp "${BASE_DIR}/src/collector/adapter.py" "${STAGE_DIR}/src/collector/"
cp "${BASE_DIR}/src/collector/buffer.py" "${STAGE_DIR}/src/collector/"
cp "${BASE_DIR}/src/collector/edge_agent.py" "${STAGE_DIR}/src/collector/"
cp "${BASE_DIR}/src/collector/simulated_adapter.py" "${STAGE_DIR}/src/collector/"
cp "${BASE_DIR}/tools/simulated_edge_collector.py" "${STAGE_DIR}/tools/"

# Create environment template (no credentials embedded in code or CLI)
cat << 'EOF' > "${STAGE_DIR}/.env.example"
# ==============================================================================
# AQUA COMMAND — Zone A Collector Configuration (nongserver Debian 13)
# ==============================================================================
ZONE_A_STATION_ID=CM-01
ZONE_A_COLLECTOR_ID=GW-CM01-NONGSERVER
ZONE_A_INGEST_URL=http://100.103.145.101:8787/api/v1/ingest/telemetry
GATEWAY_TOKEN_GW_CM01_NONGSERVER=YOUR_GATEWAY_TOKEN_GW_CM01_NONGSERVER_HERE
ZONE_A_POLL_INTERVAL=5
ZONE_A_BUFFER_DB=data/zone_a_buffer.db
DATA_CLASSIFICATION=SIMULATED_LAB
EOF

# Create secure launcher script (sources env, protects ps aux visibility)
cat << 'EOF' > "${STAGE_DIR}/run_collector.sh"
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [ ! -f .env ]; then
    echo "[ERROR] .env file not found. Copy .env.example to .env and configure keys."
    exit 1
fi

# Load variables safely into environment
set -a
# shellcheck disable=SC1091
source .env
set +a

export PYTHONPATH="${SCRIPT_DIR}"

echo "==> [AQUA COMMAND] Starting Zone A Edge Collector on nongserver..."
echo "    Station:    ${ZONE_A_STATION_ID}"
echo "    Gateway ID: ${ZONE_A_COLLECTOR_ID}"
echo "    Ingest URL: ${ZONE_A_INGEST_URL}"
echo "    Class:      ${DATA_CLASSIFICATION}"
echo "    Buffer DB:  ${ZONE_A_BUFFER_DB}"

# Run collector without passing secrets on commandline (read from env)
exec python3 tools/simulated_edge_collector.py "$@"
EOF
chmod +x "${STAGE_DIR}/run_collector.sh"

echo "==> [2/4] Packaging into archive..."
ARCHIVE="${DIST_DIR}/aqua_collector_zone_a.tar.gz"
tar -czf "${ARCHIVE}" -C "${STAGE_DIR}" .

echo "==> [3/4] Generating checksum..."
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${ARCHIVE}" > "${ARCHIVE}.sha256"
fi

SIZE="$(du -h "${ARCHIVE}" | cut -f1)"
echo "==> [4/4] Package ready for review:"
echo "    Archive:  ${ARCHIVE} (${SIZE})"
if [ -f "${ARCHIVE}.sha256" ]; then
    echo "    SHA256:   $(cat "${ARCHIVE}.sha256")"
fi

rm -rf "${STAGE_DIR}"
