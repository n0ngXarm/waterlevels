# ==============================================================================
# AQUA COMMAND — Developer Workflow Makefile (Fedora & Debian Compatible)
#
# Usage:
#   make dev-up      - Build & start Zone A Simulator and Zone B Monitoring
#   make dev-down    - Stop containers gracefully, preserving persistent data
#   make dev-status  - View live status, health checks and metrics
#   make dev-logs    - Follow live container logs
#   make dev-test    - Execute full Python and Node.js test suites
#   make dev-backup  - Create timestamped backup of SQLite databases and state
#   make dev-restore - Restore state from backup archive
#   make dev-reset   - Safely reset lab test data (with automated pre-backup)
# ==============================================================================

SHELL := /bin/bash
COMPOSE_FILE := compose.dev.yml
ENV_DEV_FILE := .env.dev

# Detect Docker Compose / Podman Compose on Fedora & Debian
COMPOSE_CMD := $(shell if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then echo "docker compose"; elif command -v podman-compose >/dev/null 2>&1; then echo "podman-compose"; else echo "docker-compose"; fi)

PYTHON_BIN := $(shell if [ -f ".venv/bin/python" ]; then echo ".venv/bin/python"; else echo "python3"; fi)

.PHONY: help dev-up dev-down dev-status dev-logs dev-test dev-backup dev-restore dev-reset dev-fault

help:
	@echo "======================================================================"
	@echo "  AQUA COMMAND — Chiang Mai Water Operations Monitoring System"
	@echo "  Fedora Single-Machine Development Lab"
	@echo "======================================================================"
	@echo "  make dev-up       Start Zone A Simulator + Zone B Monitoring (Docker)"
	@echo "  make dev-down     Stop all dev containers (preserves data)"
	@echo "  make dev-status   Check health, running containers, and live metrics"
	@echo "  make dev-logs     View container logs (Ctrl+C to exit)"
	@echo "  make dev-test     Run complete automated test suites (Python + Node)"
	@echo "  make dev-backup   Create verified tarball backup of all databases"
	@echo "  make dev-restore  Restore from backup (Usage: make dev-restore [FILE=...])"
	@echo "  make dev-reset    Reset lab test databases to clean baseline"
	@echo "  make dev-fault    Inject sensor fault (e.g. make dev-fault FAULT=pressure-low)"
	@echo "======================================================================"

$(ENV_DEV_FILE):
	@if [ ! -f "$(ENV_DEV_FILE)" ]; then \
		echo "==> Creating $(ENV_DEV_FILE) from .env.dev.example..."; \
		cp .env.dev.example $(ENV_DEV_FILE); \
	fi

dev-up: $(ENV_DEV_FILE)
	@echo "==> [AQUA COMMAND] Starting Fedora Dev Lab via $(COMPOSE_CMD)..."
	@mkdir -p data aqua-command/storage backups
	$(COMPOSE_CMD) -f $(COMPOSE_FILE) up -d --build
	@echo "==> Waiting for Zone B Command Center to become healthy..."
	@for i in {1..30}; do \
		if curl -s http://127.0.0.1:8787/api/health | grep -q '"ok":true'; then \
			echo "==> [SUCCESS] AQUA COMMAND Center is online!"; \
			echo "    Dashboard:  http://127.0.0.1:8787"; \
			echo "    Ingestion:  http://127.0.0.1:8787/api/v1/ingest/telemetry"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "==> [WARN] Timed out waiting for container health. Check 'make dev-logs'."

dev-down:
	@echo "==> [AQUA COMMAND] Stopping dev containers..."
	$(COMPOSE_CMD) -f $(COMPOSE_FILE) down
	@echo "==> [SUCCESS] Dev containers stopped. Persistent storage preserved."

dev-status:
	@echo "==> Container Status:"
	@$(COMPOSE_CMD) -f $(COMPOSE_FILE) ps
	@echo ""
	@echo "==> Zone B Health Endpoint:"
	@curl -s http://127.0.0.1:8787/api/health || echo "Zone B offline"
	@echo ""
	@echo "==> Zone B Metrics Snapshot:"
	@curl -s http://127.0.0.1:8787/api/state | $(PYTHON_BIN) -c 'import sys, json; data=json.load(sys.stdin); print("Mode:", data.get("mode")); print("Online Stations:", data.get("metrics", {}).get("online"), "/", data.get("metrics", {}).get("total")); print("Active Alerts:", data.get("metrics", {}).get("activeAlertCount")); print("Pressure Avg:", data.get("metrics", {}).get("pressure"), "bar"); print("Flow Avg:", data.get("metrics", {}).get("flow"), "m3/h")' 2>/dev/null || echo "Unable to fetch state"

dev-logs:
	$(COMPOSE_CMD) -f $(COMPOSE_FILE) logs -f --tail=100

dev-test:
	@echo "======================================================================"
	@echo "  RUNNING PYTHON UNIT & E2E INTEGRATION TEST SUITES"
	@echo "======================================================================"
	$(PYTHON_BIN) -m unittest discover tests
	@echo ""
	@echo "======================================================================"
	@echo "  RUNNING NODE.JS INGESTION, RULES & UI TEST SUITES"
	@echo "======================================================================"
	node --test aqua-command/tests/*.test.mjs

dev-backup:
	@./scripts/dev_backup.sh

dev-restore:
	@./scripts/dev_restore.sh $(FILE)

dev-reset:
	@./scripts/dev_reset.sh

dev-fault:
	@if [ -z "$(FAULT)" ]; then \
		echo "Usage: make dev-fault FAULT=<pressure-low|turbidity-high|tank-low|sensor-bad>"; \
		exit 1; \
	fi
	@echo "==> Injecting fault $(FAULT) into Zone A simulator..."
	$(PYTHON_BIN) tools/simulated_edge_collector.py --station CM-01 --once --fault $(FAULT) --ingest-url http://127.0.0.1:8787/api/v1/ingest/telemetry --token dev-gateway-key-32-chars-long-local-simulation
	@echo "==> Fault injected. Check Dashboard at http://127.0.0.1:8787"

package-zone-a:
	@./scripts/prepare_zone_a_package.sh

