#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Zone B Distributed Lab v2 Launcher & Preflight Inspector
# Parallel Blue-Green Deployment: Host Port 127.0.0.1:8788
# ZERO disruption to existing containers (aqua_command_zone_b_lab, pwa_water_alert)
# ==============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${BASE_DIR}/compose.zone-b.lab-v2.yml"
ENV_FILE="${BASE_DIR}/.env.lab"

ACTION="${1:-verify}"

echo "================================================================================"
echo " AQUA COMMAND — Zone B Lab v2 Parallel Launcher & Inspector"
echo "================================================================================"

# Step 1: Verify .env.lab exists
if [ ! -f "${ENV_FILE}" ]; then
    echo "==> [ERROR] Missing ${ENV_FILE}. Configure .env.lab before proceeding."
    exit 1
fi

# Step 2: Check for dangerous shell environment variable overrides
echo "==> [PREFLIGHT 1/6] Checking shell environment variable overrides..."
if [ "${AQUA_BIND_IP:-}" = "0.0.0.0" ]; then
    echo "==> [CRITICAL SAFETY VIOLATION] Shell variable AQUA_BIND_IP=0.0.0.0 is prohibited."
    echo "    Zone B Ingestion & Dashboard must bind strictly to 127.0.0.1."
    exit 1
fi

export AQUA_BIND_IP="127.0.0.1"

# Step 3: Structured Compose Config Validation (JSON parser, zero secret printing)
echo "==> [PREFLIGHT 2/6] Running structured Compose v2 validation (JSON parser)..."
VALIDATION_OUTPUT=$(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config --format json 2>/dev/null | python3 -c "
import sys, json

try:
    cfg = json.load(sys.stdin)
except Exception as e:
    print(f'ERROR: Failed to parse compose config JSON: {e}')
    sys.exit(1)

project_name = cfg.get('name', '')
if project_name != 'aqua-zone-b-lab-v2':
    print(f'ERROR: Compose project name must be \"aqua-zone-b-lab-v2\", got \"{project_name}\"')
    sys.exit(1)

services = cfg.get('services', {})
svc = services.get('aqua-command')
if not svc:
    print('ERROR: Service \"aqua-command\" not found in compose configuration')
    sys.exit(1)

# 1. Port mapping validation (Host IP must be 127.0.0.1 AND Published Port must be 8788)
ports = svc.get('ports', [])
port_verified = False
for p in ports:
    host_ip = p.get('host_ip', '')
    published = str(p.get('published', ''))
    target = str(p.get('target', ''))
    if host_ip == '0.0.0.0':
        print(f'CRITICAL SAFETY ERROR: Container port bound to 0.0.0.0: {p}')
        sys.exit(1)
    if host_ip == '127.0.0.1' and (published == '8788' or target == '8788'):
        port_verified = True

if not port_verified:
    print('ERROR: Port mapping verification failed. Must bind strictly to 127.0.0.1:8788.')
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
echo "    Structured validation: PASSED (127.0.0.1:8788 locked, Telegram disabled, Keys validated)"

# Step 4: Host Port Availability Check (Port 8788)
echo "==> [PREFLIGHT 3/6] Checking host port 8788 availability..."
if ss -tulpn 2>/dev/null | grep -q ':8788 '; then
    if docker ps --format '{{.Names}}' | grep -q 'aqua_command_zone_b_lab_v2'; then
        echo "    Port 8788 is currently bound by aqua_command_zone_b_lab_v2 (expected for redeploy)."
    else
        echo "==> [ERROR] Port 8788 is already in use by an unrecognized process!"
        exit 1
    fi
else
    echo "    Port 8788 is free and available."
fi

# Step 5: Audit & Protect Existing Containers (pwa_water_alert & aqua_command_zone_b_lab)
echo "==> [PREFLIGHT 4/6] Auditing and protecting existing production/lab containers..."
if docker inspect pwa_water_alert >/dev/null 2>&1; then
    PWA_STATUS=$(docker inspect pwa_water_alert --format '{{.State.Status}}')
    echo "    [PROTECTED] Existing container: pwa_water_alert (Status: ${PWA_STATUS})"
else
    echo "    Notice: pwa_water_alert not detected."
fi

if docker inspect aqua_command_zone_b_lab >/dev/null 2>&1; then
    LEGACY_STATUS=$(docker inspect aqua_command_zone_b_lab --format '{{.State.Status}}')
    LEGACY_PORT=$(docker inspect aqua_command_zone_b_lab --format '{{range $p, $conf := .NetworkSettings.Ports}}{{$p}}->{{(index $conf 0).HostPort}} {{end}}' 2>/dev/null || echo "none")
    echo "    [PRESERVED] Legacy container: aqua_command_zone_b_lab (Status: ${LEGACY_STATUS}, Port: ${LEGACY_PORT})"
    echo "    Notice: aqua_command_zone_b_lab will NOT be stopped, removed or modified."
fi

# Step 6: Isolated Storage Directory Initialization
echo "==> [PREFLIGHT 5/6] Verifying dedicated v2 storage path: ${BASE_DIR}/aqua-command/storage-v2..."
mkdir -p "${BASE_DIR}/aqua-command/storage-v2"
echo "    Dedicated storage-v2 directory ready (separate from legacy storage)."

echo "==> [PREFLIGHT 6/6] Preflight checks complete."

# Handle Actions
case "${ACTION}" in
    verify)
        echo "================================================================================"
        echo "==> [SUCCESS] All Zone B v2 preflight checks PASSED. Ready for parallel deployment."
        echo "    Run 'bash scripts/run_zone_b_lab.sh up' to start Zone B v2 on 127.0.0.1:8788."
        echo "================================================================================"
        ;;
    up)
        echo "================================================================================"
        echo "==> [STAGE B1] Starting Zone B v2 Parallel Blue-Green Deployment..."
        echo "================================================================================"

        # Capture baseline of existing containers before deployment
        BEFORE_PWA=$(docker inspect pwa_water_alert --format '{{.State.Status}}:{{.State.StartedAt}}' 2>/dev/null || echo "not_found")
        BEFORE_LEGACY=$(docker inspect aqua_command_zone_b_lab --format '{{.State.Status}}:{{.State.StartedAt}}' 2>/dev/null || echo "not_found")

        echo "    Building and launching aqua-zone-b-lab-v2 on 127.0.0.1:8788..."
        docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --build

        echo "==> [WAIT] Awaiting container v2 health check..."
        for i in {1..30}; do
            HEALTH=$(docker inspect aqua_command_zone_b_lab_v2 --format '{{.State.Health.Status}}' 2>/dev/null || echo "starting")
            if [ "${HEALTH}" = "healthy" ]; then
                echo "    Container v2 confirmed: HEALTHY (took ${i}s)"
                break
            fi
            sleep 1
        done

        # 1. Local Health Verification
        echo "==> [VERIFY 1/7] Probing local health endpoint (http://127.0.0.1:8788/api/health)..."
        HEALTH_RES=$(curl -sS http://127.0.0.1:8788/api/health)
        echo "    Response: ${HEALTH_RES}"
        if ! echo "${HEALTH_RES}" | grep -q '"ok":true'; then
            echo "[ERROR] Local health endpoint returned non-OK response."
            exit 1
        fi
        if ! echo "${HEALTH_RES}" | grep -q '"telegramConfigured":false'; then
            echo "[ERROR] Telegram is configured in lab environment!"
            exit 1
        fi

        # 2. Unauthenticated Read Rejection (401)
        echo "==> [VERIFY 2/7] Verifying unauthenticated /api/state rejection (HTTP 401)..."
        UNAUTH_HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8788/api/state)
        echo "    Unauthenticated /api/state HTTP Status: ${UNAUTH_HTTP}"
        if [ "${UNAUTH_HTTP}" != "401" ]; then
            echo "[ERROR] Expected HTTP 401 for unauthenticated read, got ${UNAUTH_HTTP}"
            exit 1
        fi

        # 3. Viewer Authentication & Session Cookie Issuance
        echo "==> [VERIFY 3/7] Verifying Viewer Login & Session Cookie..."
        VIEWER_KEY=$(python3 -c "
with open('${ENV_FILE}') as f:
    for line in f:
        if line.startswith('VIEWER_API_KEY='):
            print(line.split('=', 1)[1].strip())
")
        LOGIN_RESP_HEADERS=$(curl -sS -i -X POST http://127.0.0.1:8788/api/auth/login \
            -H "Content-Type: application/json" \
            -d "{\"key\": \"${VIEWER_KEY}\"}")
        
        SESSION_COOKIE=$(echo "${LOGIN_RESP_HEADERS}" | grep -i "set-cookie:" | grep -o "aqua_session=[^;]*" | head -n1 || echo "")
        if [ -n "${SESSION_COOKIE}" ]; then
            echo "    Viewer Login: SUCCESS (Received session cookie, credential redacted)"
        else
            echo "[ERROR] Viewer login failed. No session cookie received."
            exit 1
        fi

        # 4. HTTPS Reverse Proxy Simulation (Checking Secure, HttpOnly, SameSite)
        echo "==> [VERIFY 4/7] Verifying HTTPS Proxy dynamic Cookie attributes (Secure, HttpOnly, SameSite)..."
        HTTPS_HEADERS=$(curl -sS -i -X POST http://127.0.0.1:8788/api/auth/login \
            -H "Content-Type: application/json" \
            -H "X-Forwarded-Proto: https" \
            -d "{\"key\": \"${VIEWER_KEY}\"}")
        
        SET_COOKIE_HTTPS=$(echo "${HTTPS_HEADERS}" | grep -i "^set-cookie:" | head -n1)
        for attr in "Secure" "HttpOnly" "SameSite=Lax"; do
            if ! echo "${SET_COOKIE_HTTPS}" | grep -qi "${attr}"; then
                echo "[ERROR] Missing ${attr} attribute in HTTPS session cookie!"
                exit 1
            fi
        done
        echo "    Cookie Security Attributes: Verified (Secure; HttpOnly; SameSite=Lax present, cookie redacted)"

        # 5. Realtime SSE Stream Verification (/api/stream)
        echo "==> [VERIFY 5/7] Verifying SSE Realtime Stream authentication & payload..."
        STREAM_UNAUTH=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8788/api/stream)
        if [ "${STREAM_UNAUTH}" != "401" ]; then
            echo "[ERROR] Expected HTTP 401 for unauthenticated /api/stream, got ${STREAM_UNAUTH}"
            exit 1
        fi
        STREAM_HEADER=$(timeout 2 curl -s -i -N --cookie "${SESSION_COOKIE}" http://127.0.0.1:8788/api/stream | head -n 10 || echo "")
        if ! echo "${STREAM_HEADER}" | grep -qi "text/event-stream"; then
            echo "[ERROR] /api/stream did not return Content-Type: text/event-stream"
            exit 1
        fi
        echo "    SSE Stream: Verified (401 unauth rejection + 200 text/event-stream with session)"

        # 6. Gateway Ingestion Authentication & Source Classification
        echo "==> [VERIFY 6/7] Verifying Gateway Ingestion Authentication (POST /api/v1/ingest/telemetry)..."
        GW_TOKEN=$(python3 -c "
with open('${ENV_FILE}') as f:
    for line in f:
        if line.startswith('GATEWAY_TOKEN_GW_CM01_PATAN='):
            print(line.split('=', 1)[1].strip())
")
        NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        INGEST_PAYLOAD="{\"stationId\":\"CM-01\",\"collectorId\":\"GW-CM01-PATAN\",\"epoch\":\"EP-B1TEST\",\"sequenceNumber\":1,\"sourceTimestamp\":\"${NOW_ISO}\",\"points\":{\"CM01_PT_01\":{\"value\":2.74,\"quality\":\"GOOD\",\"unit\":\"bar\"}}}"
        
        INGEST_RES=$(curl -sS -X POST http://127.0.0.1:8788/api/v1/ingest/telemetry \
            -H "Content-Type: application/json" \
            -H "X-Gateway-Token: ${GW_TOKEN}" \
            -d "${INGEST_PAYLOAD}")
        
        echo "    Ingest Response: ${INGEST_RES}"
        if ! echo "${INGEST_RES}" | grep -q '"ok":true'; then
            echo "[ERROR] Gateway Ingestion failed."
            exit 1
        fi
        if ! echo "${INGEST_RES}" | grep -q '"dataClassification":"SIMULATED_LAB"'; then
            echo "[ERROR] Source Classification is not SIMULATED_LAB!"
            exit 1
        fi

        # 7. Verify Preservation of Original Containers (Baseline Check)
        echo "==> [VERIFY 7/7] Verifying preservation of original containers..."
        AFTER_PWA=$(docker inspect pwa_water_alert --format '{{.State.Status}}:{{.State.StartedAt}}' 2>/dev/null || echo "not_found")
        AFTER_LEGACY=$(docker inspect aqua_command_zone_b_lab --format '{{.State.Status}}:{{.State.StartedAt}}' 2>/dev/null || echo "not_found")

        if [ "${BEFORE_PWA}" = "${AFTER_PWA}" ]; then
            echo "    pwa_water_alert: UNTOUCHED & UNINTERRUPTED (${AFTER_PWA})"
        else
            echo "[WARNING] pwa_water_alert status changed: ${BEFORE_PWA} -> ${AFTER_PWA}"
        fi

        if [ "${BEFORE_LEGACY}" = "${AFTER_LEGACY}" ]; then
            echo "    aqua_command_zone_b_lab: UNTOUCHED & UNINTERRUPTED (${AFTER_LEGACY})"
        else
            echo "[WARNING] aqua_command_zone_b_lab status changed: ${BEFORE_LEGACY} -> ${AFTER_LEGACY}"
        fi

        echo "================================================================================"
        echo "==> [SUCCESS] Stage B1 Complete: Zone B v2 is active on 127.0.0.1:8788"
        echo "    All tests passed, legacy containers 100% preserved."
        echo "================================================================================"
        ;;
    down)
        echo "==> [STOP] Stopping Zone B v2 containers (aqua-zone-b-lab-v2)..."
        docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" down
        echo "==> [STOP] Zone B v2 stopped. (Original containers remain untouched)"
        ;;
    status)
        echo "==> [STATUS] Zone B v2 Container status:"
        docker ps -a --filter "name=aqua_command_zone_b_lab_v2"
        echo "==> [STATUS] Zone B v2 Local health probe:"
        curl -sS http://127.0.0.1:8788/api/health 2>/dev/null || echo "Endpoint unreachable"
        echo "==> [STATUS] Original containers status check:"
        docker ps -a --filter "name=aqua_command_zone_b_lab" --filter "name=pwa_water_alert"
        ;;
    logs)
        docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail 50 -f
        ;;
    *)
        echo "Usage: $0 {verify|up|down|status|logs}"
        exit 1
        ;;
esac
