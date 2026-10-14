# Tailscale Secure Overlay Network Architecture: Zone A & Zone B

This document specifies the secure communication topology and network controls connecting field Edge Gateways (**Zone A: Operational / Station Level**) with the Provincial Command Center (**Zone B: Centralized Management / Ingestion**).

---

## 1. Architectural Overview & Security Boundary

```
+-----------------------------------------------------------------------------------------+
|                               ZONE A: STATION / FIELD GATEWAY                           |
|                                                                                         |
|  +--------------------+         Read-Only Poll         +-----------------------------+  |
|  | Station RTU / PLC  | <============================ | Edge Collector Agent        |  |
|  | (Modbus/Analog)    |   (Strictly isolated subnet)  | (src/collector/edge_agent)  |  |
|  +--------------------+                               +--------------+--------------+  |
|                                                                      |                  |
|                                                          FIFO Store  | (Offline Buffer) |
|                                                          & Forward   v                  |
|                                                       +-----------------------------+  |
|                                                       | SQLite Collector Buffer     |  |
|                                                       | (data/collector_buffer.db)  |  |
|                                                       +--------------+--------------+  |
|                                                                      |                  |
|                                                       Outbound Only  | WireGuard Tunnel |
+----------------------------------------------------------------------|------------------+
                                                                       | (Encrypted UDP)
                                                                       | Tailscale Overlay
                                                                       v
+-----------------------------------------------------------------------------------------+
|                         ZONE B: PROVINCIAL COMMAND CENTER (CLOUD / HQ)                  |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | Ingestion Server (aqua-command/server.mjs)                                        |  |
|  | - Port 8787 bound to Tailscale IP (e.g., 100.64.0.10:8787) or localhost proxy     |  |
|  | - Strict Gateway Token Validation (`X-Gateway-Token: ...`)                        |  |
|  | - Out-of-bounds telemetry validation & sequence checking                          |  |
|  | - Historical replay timestamp categorization                                      |  |
|  +-------------------------+---------------------------------+-----------------------+  |
|                            |                                 |                          |
|                            v                                 v                          |
|                 +--------------------+            +--------------------+                |
|                 | State Store (JSON/ |            | Alert Engine       |                |
|                 | SQLite DB)         |            | (Threshold checks) |                |
|                 +--------------------+            +----------+---------+                |
|                                                              |                          |
|                                                              v                          |
|                                                   +--------------------+                |
|                                                   | Telegram Gateway   |                |
|                                                   +--------------------+                |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Hard Security Constraints

1. **Unidirectional Traffic Flow (Outbound-Only from Zone A)**:
   - The Edge Collector initiates an outbound connection to Zone B via the Tailscale overlay interface (`tailscale0`).
   - The Command Center (Zone B) **never** initiates connections into Zone A.
   - Inbound firewall rules on Zone A drop all incoming traffic from both the physical LAN and `tailscale0`.

2. **Strict OT Read-Only Isolation**:
   - The Edge Collector adapter interface (`src/collector/adapter.py`) exposes *read-only* methods (`read_telemetry()`, `check_health()`).
   - Absolutely **no write, setpoint adjustment, control, or actuation commands** exist or are permitted.
   - If an unexpected command payload is received, the agent immediately terminates the connection.

3. **Per-Gateway Authentication**:
   - Every physical station edge device is provisioned with a unique, cryptographically random `GATEWAY_TOKEN`.
   - Ingestion endpoint (`POST /api/v1/ingest/telemetry`) validates the `X-Gateway-Token` header.
   - Token mismatch results in immediate `HTTP 401 Unauthorized` and an audit security log event.

---

## 3. Tailscale Access Control Lists (ACL) Policy

In the Tailscale Admin Console (`tailnet`), configure Access Control Lists using specific tags to enforce least-privilege network isolation:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["tag:pwa-edge-gateway"],
      "dst": ["tag:pwa-command-center:8787"]
    }
  ],
  "tagOwners": {
    "tag:pwa-edge-gateway": ["group:pwa-netops"],
    "tag:pwa-command-center": ["group:pwa-netops"]
  },
  "hosts": {
    "command-center": "100.64.0.10"
  },
  "tests": [
    {
      "src": "tag:pwa-edge-gateway",
      "accept": ["tag:pwa-command-center:8787"],
      "deny": [
        "tag:pwa-command-center:22",
        "tag:pwa-command-center:443",
        "tag:pwa-edge-gateway:8787"
      ]
    },
    {
      "src": "tag:pwa-command-center",
      "deny": ["tag:pwa-edge-gateway:*"]
    }
  ]
}
```

### Explanation of ACL Enforcements:
- **`src: ["tag:pwa-edge-gateway"]`**: Only devices tagged as edge gateways can initiate connections.
- **`dst: ["tag:pwa-command-center:8787"]`**: Can only reach port `8787` (the Ingestion API) on the Command Center node.
- **`tag:pwa-command-center` to `tag:pwa-edge-gateway:*` is DENIED**: Prevents any lateral movement or reverse access from cloud/headquarters back into the station edge.

---

## 4. Edge Gateway Provisioning & Deployment

### Step 1: Generate Auth Key in Tailscale
1. In Tailscale Admin Console, generate a **Pre-authenticated Key**:
   - Check **Reusable** (or single-use per gateway).
   - Check **Ephemeral** (optional, recommended for temporary test rigs).
   - Assign Tag: `tag:pwa-edge-gateway`.

### Step 2: Edge Device Systemd Service (`pwa-edge-collector.service`)

Create `/etc/systemd/system/pwa-edge-collector.service` on the edge gateway (e.g., Raspberry Pi 4 / Advantech IPC running Ubuntu Core / Debian):

```ini
[Unit]
Description=PWA Chiang Mai Aqua Command Edge Collector Agent
After=network-online.target tailscaled.service
Wants=network-online.target tailscaled.service

[Service]
Type=simple
User=pwa-edge
Group=pwa-edge
WorkingDirectory=/opt/pwa-collector
EnvironmentFile=/etc/pwa-collector/collector.env
ExecStart=/opt/pwa-collector/.venv/bin/python -m src.collector.edge_agent
Restart=always
RestartSec=5s
KillMode=process
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Step 3: Edge Environment File (`/etc/pwa-collector/collector.env`)

```ini
# Station & Gateway Identity
STATION_ID=CM-01
GATEWAY_ID=gw-cm01-atan-01
GATEWAY_TOKEN=gw_live_atan_5f4a8e291c7b3d04e8f1928374a5b6c7

# Network Endpoints (Tailscale Ingestion Point)
INGEST_URL=http://100.64.0.10:8787/api/v1/ingest/telemetry
POLL_INTERVAL=5.0
REQUEST_TIMEOUT=4.0

# Store-and-Forward Local Buffer
BUFFER_DB_PATH=/var/lib/pwa-collector/buffer.db
MAX_BUFFER_RECORDS=50000
RETRY_BATCH_SIZE=50
```

---

## 5. Network Interruption & Recovery (Store-and-Forward)

1. **Active VPN Connection**:
   - Collector polls local station telemetry every 5 seconds.
   - Immediately transmits telemetry to `http://100.64.0.10:8787/api/v1/ingest/telemetry`.
   - If response is `HTTP 200 OK`, record is not buffered and memory is freed.

2. **VPN Outage or Cellular Signal Loss**:
   - HTTP transmission fails (e.g. `ConnectionRefused`, `ConnectTimeout`).
   - Telemetry payload is automatically stored in local SQLite FIFO buffer (`buffer.db`) with `source_timestamp`, exact sequence number, and quality metric `UNCERTAIN_OFFLINE_BUFFER`.
   - The edge agent continues to run locally, accumulating metrics without memory leaks.

3. **Reconnection & Replay**:
   - Upon network restoration, the edge agent detects connectivity.
   - It sends the most recent telemetry packet first (to restore real-time awareness).
   - In background, it begins draining the buffered SQLite queue in sequential chunks of 50 records.
   - Ingestion server detects `source_timestamp` older than 15 seconds, marks `isHistoricalReplay=true`, updates long-term time-series charts, and **avoids triggering duplicate or out-of-order alarms**.
