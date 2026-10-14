#!/usr/bin/env python3
"""Simulated Zone A Edge Collector CLI Tool.

Enables safe simulation and end-to-end verification of field telemetry ingestion
from a remote station (e.g. CM-01 Pa Tan) to Zone B Command Center without
touching real SCADA/PLC equipment.

Usage:
    python tools/simulated_edge_collector.py --once
    python tools/simulated_edge_collector.py --station CM-01 --interval 5
    python tools/simulated_edge_collector.py --station CM-01 --fault pressure-low
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.collector.simulated_adapter import SimulatedFieldAdapter
from src.collector.edge_agent import EdgeCollectorAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SimulatedCollector")


def parse_args():
    parser = argparse.ArgumentParser(description="Simulated Zone A Edge Collector for AQUA COMMAND")
    parser.add_argument("--station", default=os.getenv("ZONE_A_STATION_ID", "CM-01"), help="Target Station ID (default: CM-01)")
    parser.add_argument("--gateway-id", default=os.getenv("ZONE_A_COLLECTOR_ID", "GW-CM01-PATAN"), help="Collector Gateway ID")
    parser.add_argument("--ingest-url", default=os.getenv("ZONE_A_INGEST_URL", "http://127.0.0.1:8787/api/v1/ingest/telemetry"), help="Zone B Ingestion API Endpoint")
    parser.add_argument("--token", default=os.getenv("GATEWAY_INGEST_KEY", os.getenv("ADMIN_API_KEY", "")), help="Gateway Ingestion Secret Token")
    parser.add_argument("--interval", type=int, default=int(os.getenv("ZONE_A_POLL_INTERVAL", "5")), help="Collection interval in seconds")
    parser.add_argument("--once", action="store_true", help="Transmit a single reading and exit")
    parser.add_argument("--fault", choices=["pressure-low", "turbidity-high", "tank-low", "sensor-bad"], help="Inject simulated anomaly for testing")
    parser.add_argument("--buffer-db", default="data/simulated_collector.db", help="Path to local SQLite buffer database")
    parser.add_argument("--classification", default=os.getenv("DATA_CLASSIFICATION", "SIMULATED_LAB"), help="Telemetry classification (default: SIMULATED_LAB)")
    return parser.parse_args()


def main():
    args = parse_args()
    logger.info("Initializing Zone A Simulated Collector for Station: %s (Gateway: %s)", args.station, args.gateway_id)

    adapter = SimulatedFieldAdapter()
    adapter.connect()

    # Apply test fault if requested
    if args.fault == "pressure-low":
        logger.warning("INJECTING FAULT: Low Pressure (0.65 bar - Critical Threshold)")
        adapter.set_fault("CM01_PT_01", 0.65)
    elif args.fault == "turbidity-high":
        logger.warning("INJECTING FAULT: High Turbidity (5.5 NTU - Critical Threshold)")
        adapter.set_fault("CM01_AT_01", 5.5)
    elif args.fault == "tank-low":
        logger.warning("INJECTING FAULT: Low Tank Level (12.0%% - Critical Threshold)")
        adapter.set_fault("CM01_LT_01", 12.0)
    elif args.fault == "sensor-bad":
        logger.warning("INJECTING FAULT: Bad Sensor Quality Flag")
        adapter.set_fault("CM01_PT_01", 0.0, quality="BAD")

    agent = EdgeCollectorAgent(
        adapter=adapter,
        ingest_url=args.ingest_url,
        station_id=args.station,
        collector_id=args.gateway_id,
        gateway_token=args.token,
        buffer_db_path=args.buffer_db,
        data_classification=args.classification
    )

    if args.once:
        res = agent.step()
        logger.info("Single step completed: %s (HTTP %s)", res["status"], res.get("http_status"))
        return 0 if res["status"] in ("DELIVERED", "BUFFERED") else 1

    logger.info("Starting collector loop (Interval: %ds, Ingest: %s). Press Ctrl+C to exit.", args.interval, args.ingest_url)
    try:
        while True:
            res = agent.step()
            logger.info("Telemetry Step: %s (HTTP %s, Buffer Pending: %d)", res["status"], res.get("http_status"), agent.buffer.pending_count())
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Collector stopped by user.")
        adapter.disconnect()
        return 0


if __name__ == "__main__":
    sys.exit(main())
