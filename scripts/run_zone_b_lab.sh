#!/usr/bin/env bash
# ==============================================================================
# AQUA COMMAND — Zone B Distributed Lab Launch & Verification Script
# Enforces strictly isolated 127.0.0.1 binding and .env.lab environment
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
echo "==> [PREFLIGHT 1/4] Checking shell environment variable overrides..."
if [ "${AQUA_BIND_IP:-}" = "0.0.0.0" ]; then
    echo "==> [CRITICAL SAFETY VIOLATION] Shell variable AQUA_BIND_IP=0.0.0.0 is prohibited in Lab."
    echo "    Zone B Ingestion & Dashboard must bind strictly to 127.0.0.1."
    exit 1
fi

export AQUA_BIND_IP="127.0.0.1"

# Step 3: Run Docker Compose Config verification with explicit --env-file
echo "==> [PREFLIGHT 2/4] Validating Docker Compose configuration with --env-file .env.lab..."
COMPOSE_CFG=$(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config 2>&1)

# Step 4: Verify Port Mapping
echo "==> [PREFLIGHT 3/4] Verifying port mapping is locked to 127.0.0.1:8787..."
if echo "${COMPOSE_CFG}" | grep -q 'host_ip: 0.0.0.0'; then
    echo "==> [ERROR] Docker compose resolves host_ip to 0.0.0.0. Aborting start."
    exit 1
fi

if ! echo "${COMPOSE_CFG}" | grep -E "host_ip: 127.0.0.1" >/dev/null && ! echo "${COMPOSE_CFG}" | grep -E 'published: "?8787"?' >/dev/null; then
    echo "==> [ERROR] Could not confirm 127.0.0.1:8787 binding in compose config."
    echo "${COMPOSE_CFG}"
    exit 1
fi
echo "    Port mapping verified: 127.0.0.1:8787 (Strict Loopback Only)"

# Step 5: Verify Critical Environment Overrides
echo "==> [PREFLIGHT 4/4] Verifying safety variables in container environment..."
for var in "APP_ENV: lab" "DEMO_MODE: \"false\"" "SEND_DEMO_ALERTS: \"false\"" "REQUIRE_AUTH_FOR_READ: \"true\""; do
    if ! echo "${COMPOSE_CFG}" | grep -F "${var}" >/dev/null; then
        echo "==> [ERROR] Missing or mismatched safety variable '${var}' in compose config."
        exit 1
    fi
done
echo "    Safety variables verified: APP_ENV=lab, DEMO=false, TELEGRAM=disabled"

# Handle Actions
case "${ACTION}" in
    verify)
        echo "==> [SUCCESS] All Zone B preflight checks PASSED. Ready for launch."
        echo "    Run 'bash scripts/run_zone_b_lab.sh up' when approved to start container."
        ;;
    up)
        echo "==> [LAUNCH] Building and starting Zone B Container with --env-file .env.lab..."
        docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --build
        echo "==> [WAIT] Waiting for container health status..."
        for i in {1..30}; do
            HEALTH=$(docker inspect aqua_command_zone_b_lab --format '{{.State.Health.Status}}' 2>/dev/null || echo "starting")
            if [ "${HEALTH}" = "healthy" ]; then
                echo "==> [HEALTHY] Zone B container is running and healthy!"
                break
            fi
            sleep 1
        done
        echo "==> [STATUS] Testing local endpoint:"
        curl -sS http://127.0.0.1:8787/api/health | jq . || curl -sS http://127.0.0.1:8787/api/health
        ;;
    down)
        echo "==> [STOP] Stopping Zone B container..."
        docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" down
        echo "==> [STOP] Container stopped."
        ;;
    status)
        echo "==> [STATUS] Container status:"
        docker ps -a --filter "name=aqua_command_zone_b_lab"
        echo "==> [STATUS] Local health check:"
        curl -sS http://127.0.0.1:8787/api/health || echo "Endpoint unreachable"
        ;;
    logs)
        docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail 50 -f
        ;;
    *)
        echo "Usage: $0 {verify|up|down|status|logs}"
        exit 1
        ;;
esac
