#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Zone B Distributed Lab Launcher & Preflight Inspector
# Enforces strictly isolated 127.0.0.1 binding, structured validation,
# and zero-secret logging.
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${BASE_DIR}/compose.zone-b.lab.yml"
ENV_FILE="${BASE_DIR}/.env.lab"

ACTION="${1:-verify}"

echo "================================================================================"
echo " AQUA COMMAND — Zone B Lab Launcher & Preflight Inspector"
echo "================================================================================"

# Step 1: Verify .env.lab exists
if [ ! -f "${ENV_FILE}" ]; then
    echo "==> [ERROR] Missing ${ENV_FILE}. Copy .env.lab.example to .env.lab and configure."
    exit 1
fi

# Step 2: Check for dangerous shell environment variable overrides
echo "==> [PREFLIGHT 1/5] Checking shell environment variable overrides..."
if [ "${AQUA_BIND_IP:-}" = "0.0.0.0" ]; then
    echo "==> [CRITICAL SAFETY VIOLATION] Shell variable AQUA_BIND_IP=0.0.0.0 is prohibited in Lab."
    echo "    Zone B Ingestion & Dashboard must bind strictly to 127.0.0.1."
    exit 1
fi

export AQUA_BIND_IP="127.0.0.1"

# Step 3: Structured Compose Config Validation (Without leaking secrets to logs)
echo "==> [PREFLIGHT 2/5] Running structured Compose config validation (JSON parser)..."
VALIDATION_OUTPUT=$(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config --format json 2>/dev/null | python3 -c "
import sys, json

try:
    cfg = json.load(sys.stdin)
except Exception as e:
    print(f'ERROR: Failed to parse compose config JSON: {e}')
    sys.exit(1)

# Check top-level project name
project_name = cfg.get('name', '')
if project_name != 'aqua-zone-b-lab':
    print(f'ERROR: Compose project name must be \"aqua-zone-b-lab\", got \"{project_name}\"')
    sys.exit(1)

services = cfg.get('services', {})
svc = services.get('aqua-command')
if not svc:
    print('ERROR: Service \"aqua-command\" not found in compose configuration')
    sys.exit(1)

# 1. Port mapping validation (Host IP must be 127.0.0.1 AND Published Port must be 8787)
ports = svc.get('ports', [])
port_verified = False
for p in ports:
    host_ip = p.get('host_ip', '')
    published = str(p.get('published', ''))
    target = str(p.get('target', ''))
    if host_ip == '0.0.0.0':
        print(f'CRITICAL SAFETY ERROR: Container port bound to 0.0.0.0: {p}')
        sys.exit(1)
    if host_ip == '127.0.0.1' and (published == '8787' or target == '8787'):
        port_verified = True

if not port_verified:
    print('ERROR: Port mapping verification failed. Must bind strictly to 127.0.0.1:8787.')
    sys.exit(1)

# 2. Safety Environment Variables validation
env = svc.get('environment', {})
expected_env = {
    'APP_ENV': 'lab',
    'DEMO_MODE': 'false',
    'SEND_DEMO_ALERTS': 'false',
    'REQUIRE_AUTH_FOR_READ': 'true',
    'TELEGRAM_BOT_TOKEN': '',
    'TELEGRAM_CHAT_ID': ''
}

for k, expected_v in expected_env.items():
    actual_v = str(env.get(k, ''))
    if actual_v != expected_v:
        print(f'ERROR: Safety variable mismatch for {k}: expected \"{expected_v}\", got \"{actual_v}\"')
        sys.exit(1)

# 3. Credential presence and length validation (WITHOUT printing secret values)
required_secrets = [
    'ADMIN_API_KEY',
    'VIEWER_API_KEY',
    'GATEWAY_TOKEN_GW_CM01_PATAN',
    'GATEWAY_TOKEN_GW_CM01_NONGSERVER'
]

for sec in required_secrets:
    val = env.get(sec, '')
    if not val or len(val) < 24:
        print(f'ERROR: Secret variable {sec} is missing or shorter than 24 characters')
        sys.exit(1)

print('STRUCTURED_VALIDATION_PASSED')
" 2>&1)

if ! echo "${VALIDATION_OUTPUT}" | grep -q "STRUCTURED_VALIDATION_PASSED"; then
    echo "==> [ERROR] Structured compose validation failed:"
    echo "${VALIDATION_OUTPUT}"
    exit 1
fi
echo "    Structured validation: PASSED (127.0.0.1:8787 locked, Telegram disabled, Keys validated)"

# Step 4: Existing Container & Service Audit
echo "==> [PREFLIGHT 3/5] Auditing existing containers and project namespace..."
if docker inspect pwa_water_alert >/dev/null 2>&1; then
    PWA_ALERT_NET=$(docker inspect pwa_water_alert --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} {{end}}' 2>/dev/null || echo "")
    echo "    Detected independent service: pwa_water_alert (Network: ${PWA_ALERT_NET})"
    echo "    Protection: pwa_water_alert belongs to separate project and will NOT be touched."
fi

# Step 5: Container Name Collision Detection
echo "==> [PREFLIGHT 4/5] Checking container name collision for aqua_command_zone_b_lab..."
if docker inspect aqua_command_zone_b_lab >/dev/null 2>&1; then
    OLD_PROJECT=$(docker inspect aqua_command_zone_b_lab --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || echo "unknown")
    OLD_STATUS=$(docker inspect aqua_command_zone_b_lab --format '{{.State.Status}}' 2>/dev/null || echo "unknown")
    echo "    Found existing container: aqua_command_zone_b_lab (Status: ${OLD_STATUS}, Project: ${OLD_PROJECT})"
    if [ "${OLD_PROJECT}" != "aqua-zone-b-lab" ]; then
        echo "    Notice: Existing container belongs to legacy project \"${OLD_PROJECT}\"."
        echo "    It will be safely replaced under project \"aqua-zone-b-lab\" during 'up'."
    fi
else
    echo "    No existing container collision detected."
fi

echo "==> [PREFLIGHT 5/5] Preflight checks complete."

# Handle Actions
case "${ACTION}" in
    verify)
        echo "================================================================================"
        echo "==> [SUCCESS] All Zone B preflight checks PASSED. Ready for launch."
        echo "    Run 'bash scripts/run_zone_b_lab.sh up' when approved to start container."
        echo "================================================================================"
        ;;
    up)
        echo "==> [STAGE B1] Initiating controlled launch for Zone B Lab..."
        # Backup storage before proceeding
        if [ -d "${BASE_DIR}/aqua-command/storage" ]; then
            BACKUP_STAMP="$(date +'%Y%m%d_%H%M%S')"
            mkdir -p "${BASE_DIR}/backups"
            cp -a "${BASE_DIR}/aqua-command/storage" "${BASE_DIR}/backups/storage_pre_launch_${BACKUP_STAMP}"
            echo "    State snapshot saved to backups/storage_pre_launch_${BACKUP_STAMP}"
        fi

        # Gracefully stop and remove legacy container if needed
        if docker inspect aqua_command_zone_b_lab >/dev/null 2>&1; then
            echo "    Stopping and replacing prior aqua_command_zone_b_lab container..."
            docker rm -f aqua_command_zone_b_lab >/dev/null
        fi

        echo "    Building and starting aqua-zone-b-lab with --env-file .env.lab..."
        docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --build

        echo "==> [WAIT] Awaiting container health check..."
        for i in {1..30}; do
            HEALTH=$(docker inspect aqua_command_zone_b_lab --format '{{.State.Health.Status}}' 2>/dev/null || echo "starting")
            if [ "${HEALTH}" = "healthy" ]; then
                echo "    Container health confirmed: HEALTHY (took ${i}s)"
                break
            fi
            sleep 1
        done

        # Local Health & Authentication Verification
        echo "==> [VERIFY] Verifying local health endpoint:"
        HEALTH_RES=$(curl -sS http://127.0.0.1:8787/api/health)
        echo "    Health Response: ${HEALTH_RES}"
        if ! echo "${HEALTH_RES}" | grep -q '"ok":true'; then
            echo "[ERROR] Local health endpoint returned non-OK response."
            exit 1
        fi

        echo "==> [VERIFY] Verifying Viewer Authentication:"
        VIEWER_KEY=$(python3 -c "
with open('${ENV_FILE}') as f:
    for line in f:
        if line.startswith('VIEWER_API_KEY='):
            print(line.split('=', 1)[1].strip())
")
        AUTH_HEADER=$(curl -sS -i -X POST http://127.0.0.1:8787/api/auth/login \
            -H "Content-Type: application/json" \
            -d "{\"key\": \"${VIEWER_KEY}\"}")
        
        if echo "${AUTH_HEADER}" | grep -q "aqua_session="; then
            echo "    Authentication check: SUCCESS (Set-Cookie received)"
        else
            echo "[ERROR] Authentication test failed. Did not receive session cookie."
            exit 1
        fi
        echo "================================================================================"
        echo "==> [SUCCESS] Zone B Lab Container successfully deployed and verified!"
        echo "================================================================================"
        ;;
    down)
        echo "==> [STOP] Stopping Zone B Lab containers..."
        docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" down
        echo "==> [STOP] Zone B Lab stopped."
        ;;
    status)
        echo "==> [STATUS] Zone B Lab container status:"
        docker ps -a --filter "name=aqua_command_zone_b_lab"
        echo "==> [STATUS] Local health probe:"
        curl -sS http://127.0.0.1:8787/api/health 2>/dev/null || echo "Endpoint unreachable"
        ;;
    logs)
        docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail 50 -f
        ;;
    *)
        echo "Usage: $0 {verify|up|down|status|logs}"
        exit 1
        ;;
esac
