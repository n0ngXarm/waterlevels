"""End-to-End Field Integration Test Suite for Zone A & Zone B.

Tests:
1. SimulatedFieldAdapter (nominal readings, faults, disconnects, limits)
2. CollectorBuffer (SQLite FIFO store-and-forward, order preservation, mark_sent)
3. EdgeCollectorAgent (live delivery, network drop buffering, reconnection replay, restart resilience)
4. Transport & Gateway Authentication headers
"""

from datetime import datetime, timezone
import json
import http.server
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request

from src.collector.simulated_adapter import SimulatedFieldAdapter
from src.collector.buffer import CollectorBuffer
from src.collector.edge_agent import EdgeCollectorAgent


class MockZoneBIngestHandler(http.server.BaseHTTPRequestHandler):
    """Mock Zone B Ingestion HTTP Server for unit and integration testing."""

    # Class-level test state
    received_requests: list[dict] = []
    auth_header_required: str = "valid-secret-token-32-chars-long"
    reject_with_status: int = 200

    def log_message(self, format, *args):
        pass  # Quiet logging during test

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        parsed = json.loads(body) if body else {}

        # Record incoming request metadata
        MockZoneBIngestHandler.received_requests.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": parsed
        })

        # Check simulate server error / offline
        if MockZoneBIngestHandler.reject_with_status != 200:
            self.send_response(MockZoneBIngestHandler.reject_with_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Simulated error"}).encode("utf-8"))
            return

        # Check Gateway Auth
        token = self.headers.get("X-Gateway-Token") or self.headers.get("X-API-Key")
        if token != MockZoneBIngestHandler.auth_header_required:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
            return

        # Check basic schema validation
        if not parsed.get("stationId") or not parsed.get("points"):
            self.send_response(422)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unprocessable Entity"}).encode("utf-8"))
            return

        # Success
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "ok": True,
            "stationId": parsed.get("stationId"),
            "dataClassification": "AUTHORIZED_FIELD_TELEMETRY"
        }).encode("utf-8"))


class TestSimulatedFieldAdapter(unittest.TestCase):
    """Validates the simulated physical station instrumentation adapter."""

    def setUp(self):
        self.adapter = SimulatedFieldAdapter()

    def test_connection_state(self):
        self.assertFalse(self.adapter.is_connected())
        with self.assertRaises(ConnectionError):
            self.adapter.read_point("CM01_PT_01")

        self.adapter.connect()
        self.assertTrue(self.adapter.is_connected())

        reading = self.adapter.read_point("CM01_PT_01")
        self.assertEqual(reading["point_id"], "CM01_PT_01")
        self.assertEqual(reading["quality"], "GOOD")
        self.assertGreater(reading["value"], 0.0)

        self.adapter.disconnect()
        self.assertFalse(self.adapter.is_connected())

    def test_fault_injection_and_clearing(self):
        self.adapter.connect()

        # Normal reading should be around 2.50 bar
        norm = self.adapter.read_point("CM01_PT_01")
        self.assertAlmostEqual(norm["value"], 2.50, delta=0.5)

        # Inject critical drop fault (0.45 bar, BAD quality)
        self.adapter.set_fault("CM01_PT_01", value=0.45, quality="BAD")
        faulty = self.adapter.read_point("CM01_PT_01")
        self.assertEqual(faulty["value"], 0.45)
        self.assertEqual(faulty["quality"], "BAD")

        # Clear fault
        self.adapter.clear_faults()
        cleared = self.adapter.read_point("CM01_PT_01")
        self.assertEqual(cleared["quality"], "GOOD")
        self.assertGreater(cleared["value"], 1.5)


class TestCollectorBuffer(unittest.TestCase):
    """Validates SQLite FIFO store-and-forward queue resilience."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_buffer.db"
        self.buffer = CollectorBuffer(str(self.db_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fifo_ordering_and_mark_sent(self):
        self.assertEqual(self.buffer.pending_count(), 0)

        # Enqueue 3 packets in sequence
        p1 = {"stationId": "CM-01", "sequenceNumber": 1, "sourceTimestamp": "2026-10-14T08:00:00Z"}
        p2 = {"stationId": "CM-01", "sequenceNumber": 2, "sourceTimestamp": "2026-10-14T08:00:05Z"}
        p3 = {"stationId": "CM-01", "sequenceNumber": 3, "sourceTimestamp": "2026-10-14T08:00:10Z"}

        id1 = self.buffer.enqueue(p1)
        id2 = self.buffer.enqueue(p2)
        id3 = self.buffer.enqueue(p3)

        self.assertEqual(self.buffer.pending_count(), 3)

        # Dequeue batch of 2
        batch = self.buffer.dequeue_batch(limit=2)
        self.assertEqual(len(batch), 2)
        self.assertEqual(batch[0]["id"], id1)
        self.assertEqual(batch[0]["packet"]["sequenceNumber"], 1)
        self.assertEqual(batch[1]["id"], id2)
        self.assertEqual(batch[1]["packet"]["sequenceNumber"], 2)

        # Mark first 2 sent
        removed = self.buffer.mark_sent([id1, id2])
        self.assertEqual(removed, 2)
        self.assertEqual(self.buffer.pending_count(), 1)

        # Dequeue remaining
        remaining = self.buffer.dequeue_batch(limit=10)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], id3)


class TestEdgeCollectorAgentE2E(unittest.TestCase):
    """End-to-End integration tests connecting EdgeCollectorAgent to Ingestion endpoint."""

    @classmethod
    def setUpClass(cls):
        # Start local MockZoneB HTTP server
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), MockZoneBIngestHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.ingest_url = f"http://127.0.0.1:{cls.port}/api/v1/ingest/telemetry"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        MockZoneBIngestHandler.received_requests.clear()
        MockZoneBIngestHandler.reject_with_status = 200
        self.temp_dir = tempfile.TemporaryDirectory()
        self.buffer_db = Path(self.temp_dir.name) / "agent_buffer.db"
        self.adapter = SimulatedFieldAdapter()
        self.adapter.connect()
        self.agent = EdgeCollectorAgent(
            adapter=self.adapter,
            ingest_url=self.ingest_url,
            station_id="CM-01",
            collector_id="GW-CM01-PATAN",
            gateway_token="valid-secret-token-32-chars-long",
            buffer_db_path=str(self.buffer_db)
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_live_delivery_and_gateway_auth(self):
        """Scenario: Normal connectivity delivers telemetry with valid gateway token."""
        res = self.agent.step()
        self.assertEqual(res["status"], "DELIVERED")
        self.assertEqual(res["http_status"], 200)

        # Verify request arrived at server
        self.assertEqual(len(MockZoneBIngestHandler.received_requests), 1)
        req = MockZoneBIngestHandler.received_requests[0]
        self.assertEqual(req["headers"]["X-Gateway-Token"], "valid-secret-token-32-chars-long")
        self.assertEqual(req["body"]["stationId"], "CM-01")
        self.assertEqual(req["body"]["dataClassification"], "AUTHORIZED_FIELD_TELEMETRY")
        self.assertIn("CM01_PT_01", req["body"]["points"])

    def test_unauthorized_token_rejection(self):
        """Scenario: Invalid gateway token is rejected by server."""
        self.agent.gateway_token = "invalid-unauthorized-token-key"
        res = self.agent.step()
        self.assertEqual(res["status"], "REJECTED")
        self.assertEqual(res["http_status"], 401)

    def test_network_drop_buffering_and_recovery_replay(self):
        """Scenario: VPN disconnection causes agent to buffer; recovery triggers FIFO replay."""
        # Step 1: Simulate network outage (HTTP 503 Service Unavailable)
        MockZoneBIngestHandler.reject_with_status = 503

        res1 = self.agent.step()
        self.assertEqual(res1["status"], "BUFFERED")
        self.assertEqual(self.agent.buffer.pending_count(), 1)

        res2 = self.agent.step()
        self.assertEqual(res2["status"], "BUFFERED")
        self.assertEqual(self.agent.buffer.pending_count(), 2)

        # Step 2: Restore connectivity (Zone B back online)
        MockZoneBIngestHandler.reject_with_status = 200

        # Step 3: Next step should drain the buffered records first, then send fresh telemetry
        res3 = self.agent.step()
        self.assertEqual(res3["status"], "DELIVERED")
        self.assertEqual(self.agent.buffer.pending_count(), 0, "Buffer must be completely emptied upon recovery")

    def test_collector_restart_resilience(self):
        """Scenario: Agent restarts while records are in buffer; new process resumes without data loss."""
        # Buffer 2 items
        MockZoneBIngestHandler.reject_with_status = 502
        self.agent.step()
        self.agent.step()
        self.assertEqual(self.agent.buffer.pending_count(), 2)

        # Simulate agent termination and restart with a brand new instance pointing to same SQLite DB
        del self.agent
        new_agent = EdgeCollectorAgent(
            adapter=self.adapter,
            ingest_url=self.ingest_url,
            station_id="CM-01",
            collector_id="GW-CM01-PATAN",
            gateway_token="valid-secret-token-32-chars-long",
            buffer_db_path=str(self.buffer_db)
        )

        self.assertEqual(new_agent.buffer.pending_count(), 2, "Restarted agent must detect existing buffered items")

        # Zone B back online
        MockZoneBIngestHandler.reject_with_status = 200
        new_agent.step()
        self.assertEqual(new_agent.buffer.pending_count(), 0, "Restarted agent successfully flushed prior buffer")


if __name__ == "__main__":
    unittest.main()
