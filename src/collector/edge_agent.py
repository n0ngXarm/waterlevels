"""Autonomous Edge Collector Agent for Zone A (Station/OT Boundary).

Reads field points, attaches source timestamps and quality flags,
maintains sequence numbers, manages local buffer during network drops,
and securely transmits telemetry to Zone B Ingestion API.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Optional
import urllib.request
import urllib.error
from src.collector.adapter import EdgeCollectorAdapter
from src.collector.buffer import CollectorBuffer

logger = logging.getLogger(__name__)


class EdgeCollectorAgent:
    """Agent running on Zone A gateway connecting instrumentation to Zone B."""

    def __init__(
        self,
        adapter: EdgeCollectorAdapter,
        ingest_url: str,
        station_id: str = "CM-01",
        collector_id: str = "GW-CM01-PATAN",
        gateway_token: str = "",
        buffer_db_path: str = "data/collector_buffer.db"
    ):
        self.adapter = adapter
        self.ingest_url = ingest_url.rstrip("/")
        self.station_id = station_id
        self.collector_id = collector_id
        self.gateway_token = gateway_token
        self.buffer = CollectorBuffer(buffer_db_path)
        self._sequence_number = 0
        self._last_send_success = False

    def build_telemetry_packet(self) -> dict[str, Any]:
        """Reads adapter points and constructs standardized telemetry payload."""
        raw_points = self.adapter.read_all_points()
        self._sequence_number += 1
        now_iso = datetime.now(timezone.utc).isoformat()

        # Format points schema
        points_payload: dict[str, Any] = {}
        for pid, pt in raw_points.items():
            points_payload[pid] = {
                "value": pt["value"],
                "quality": pt.get("quality", "GOOD"),
                "unit": pt.get("unit", "")
            }

        return {
            "stationId": self.station_id,
            "collectorId": self.collector_id,
            "sequenceNumber": self._sequence_number,
            "sourceTimestamp": now_iso,
            "dataClassification": "AUTHORIZED_FIELD_TELEMETRY",
            "points": points_payload
        }

    def _post_packet(self, packet: dict[str, Any], timeout: float = 5.0) -> tuple[bool, int, str]:
        """Transmits a single telemetry packet to Zone B with gateway authentication."""
        headers = {
            "Content-Type": "application/json",
            "X-Gateway-ID": self.collector_id,
            "X-Gateway-Token": self.gateway_token,
            "X-API-Key": self.gateway_token,  # Fallback compatibility
            "User-Agent": f"ZoneA-EdgeCollector/{self.collector_id}"
        }
        data = json.dumps(packet).encode("utf-8")
        req = urllib.request.Request(self.ingest_url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                return (status in (200, 201, 202), status, body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            return (False, e.code, err_body)
        except Exception as e:
            return (False, 0, str(e))

    def flush_buffer(self, max_batch: int = 10) -> int:
        """Replays buffered historical telemetry in chronological FIFO order."""
        pending = self.buffer.dequeue_batch(limit=max_batch)
        if not pending:
            return 0

        sent_ids = []
        for item in pending:
            ok, status, _ = self._post_packet(item["packet"], timeout=4.0)
            if ok:
                sent_ids.append(item["id"])
            else:
                logger.warning("Replay of buffered packet %d failed (status=%d). Stopping replay batch.", item["id"], status)
                self.buffer.increment_attempts([item["id"]])
                break

        if sent_ids:
            self.buffer.mark_sent(sent_ids)
            logger.info("Successfully replayed %d buffered packets to Zone B.", len(sent_ids))
        return len(sent_ids)

    def step(self) -> dict[str, Any]:
        """
        Executes one collection and delivery cycle.
        1. If buffer has items, tries to flush.
        2. Reads fresh points from field adapter.
        3. Attempts delivery to Zone B.
        4. If delivery fails, saves to buffer.
        """
        # Step 1: Replay buffered records if any
        if self.buffer.pending_count() > 0:
            self.flush_buffer()

        # Step 2: Read fresh points
        packet = self.build_telemetry_packet()

        # Step 3: Send to Zone B
        ok, status, body = self._post_packet(packet)
        self._last_send_success = ok

        if ok:
            logger.debug("Delivered live telemetry seq=%d to Zone B", packet["sequenceNumber"])
            return {"status": "DELIVERED", "packet": packet, "http_status": status}

        # Step 4: Fallback to buffer if network is down or server error
        if status in (0, 500, 502, 503, 504):
            buf_id = self.buffer.enqueue(packet)
            logger.warning("Zone B unreachable (HTTP %d). Telemetry seq=%d enqueued to buffer (ID=%d)", status, packet["sequenceNumber"], buf_id)
            return {"status": "BUFFERED", "packet": packet, "buffer_id": buf_id, "http_status": status}

        # Unauthorized (401/403) or Unprocessable (422)
        logger.error("Zone B rejected packet with HTTP %d: %s", status, body)
        return {"status": "REJECTED", "packet": packet, "http_status": status, "error": body}
