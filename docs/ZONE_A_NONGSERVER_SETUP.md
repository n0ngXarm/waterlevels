# Zone A Deployment Guide: nongserver (Debian 13)

This document provides exact, verified instructions for running the **Zone A Simulated Edge Collector** on `nongserver` (Debian 13 Trixie) without touching or endangering existing production containers.

---

## 1. Safety Principles & Zero Production Impact

1. **Zero Docker Footprint:**
   - No Docker containers, images, volumes, or networks are created or modified on `nongserver`.
   - The Docker daemon and all 20 running production services are completely untouched.

2. **Zero Ingress / Outbound Only:**
   - Zone A collector operates exclusively as an outbound HTTP client.
   - It sends telemetry to Zone B (`http://100.103.145.101:8787/api/v1/ingest/telemetry`) over Tailscale WireGuard.
   - No ports are opened, forwarded, or bound on `nongserver`.

3. **Guaranteed Resource Budget:**
   - **Disk Space:** Code footprint is ~40 KB. The SQLite buffer (`zone_a_buffer.db`) has a hardcoded ceiling of 5 MB (ring buffer overwrite). Total disk impact: < 5.1 MB (< 0.02% of the 28 GB available).
   - **RAM Usage:** Runs inside Python 3.13 standard interpreter using ~15 MB RAM (0.07% of the 20 GB available).
   - **CPU Usage:** < 0.02% (sleeps between 5-second polling intervals).

4. **Credential Safety:**
   - Secrets (`GATEWAY_INGEST_KEY`) are read strictly from `.env` (file mode `0600`).
   - Tokens are **never** passed as CLI arguments, preventing credential leakage in `ps aux`, `top`, or `/proc/$PID/cmdline`.

---

## 2. Directory Structure on `nongserver`

When extracted into `/home/pisitpong/aqua-collector-lab`:

```
/home/pisitpong/aqua-collector-lab/
├── .env                (chmod 0600, gateway token and ingest URL)
├── .env.example        (reference template)
├── run_collector.sh    (launcher script sourcing .env and setting PYTHONPATH)
├── data/               (local SQLite store-and-forward buffer, max 5 MB)
│   └── zone_a_buffer.db
├── src/
│   ├── __init__.py
│   └── collector/
│       ├── __init__.py
│       ├── adapter.py
│       ├── buffer.py
│       ├── edge_agent.py
│       └── simulated_adapter.py
└── tools/
    └── simulated_edge_collector.py
```

---

## 3. Deployment Procedure (Pending Phase 2 Approval)

> [!NOTE]
> This procedure will only be executed AFTER Phase 2 is reviewed and formally approved.

### Step 1: Copy Standalone Archive to `nongserver`
From Fedora (Zone B):
```bash
scp dist/aqua_collector_zone_a.tar.gz 100.83.235.78:/home/pisitpong/
```

### Step 2: Extract in Dedicated Lab Directory
On `nongserver` (Zone A):
```bash
mkdir -p /home/pisitpong/aqua-collector-lab
cd /home/pisitpong/aqua-collector-lab
tar -xzf /home/pisitpong/aqua_collector_zone_a.tar.gz
rm -f /home/pisitpong/aqua_collector_zone_a.tar.gz
```

### Step 3: Configure Environment (`.env`)
```bash
cp .env.example .env
chmod 600 .env
```

Ensure `.env` contains:
```ini
ZONE_A_STATION_ID=CM-01
ZONE_A_COLLECTOR_ID=GW-CM01-NONGSERVER
ZONE_A_INGEST_URL=http://100.103.145.101:8787/api/v1/ingest/telemetry
GATEWAY_INGEST_KEY=YOUR_GATEWAY_INGEST_KEY_HERE
ZONE_A_POLL_INTERVAL=5
ZONE_A_BUFFER_DB=data/zone_a_buffer.db
DATA_CLASSIFICATION=SIMULATED_LAB
```

### Step 4: Run Collector in Foreground
```bash
./run_collector.sh
```
Observe live output:
```
==> [AQUA COMMAND] Starting Zone A Edge Collector on nongserver...
    Station:    CM-01
    Gateway ID: GW-CM01-NONGSERVER
    Ingest URL: http://100.103.145.101:8787/api/v1/ingest/telemetry
    Class:      SIMULATED_LAB
    Buffer DB:  data/zone_a_buffer.db
... [INFO] SimulatedCollector: Telemetry Step: DELIVERED (HTTP 200, Buffer Pending: 0)
```

---

## 4. Controlled Termination & Safe Quarantine

1. **Stopping the Process:**
   Press `Ctrl+C` in the terminal running `./run_collector.sh`. The agent cleanly disconnects and exits immediately.

2. **Safe Quarantine (No Destructive `rm -rf`):**
   If testing concludes and cleanup is requested:
   ```bash
   TIMESTAMP=$(date +'%Y%m%d_%H%M%S')
   mkdir -p /home/pisitpong/lab_quarantine
   mv /home/pisitpong/aqua-collector-lab "/home/pisitpong/lab_quarantine/aqua-collector-lab_${TIMESTAMP}"
   ```
   All test logs and buffers are safely preserved in quarantine for audit without leaving active processes.
