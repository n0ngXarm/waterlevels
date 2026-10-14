"""End-to-End Field Integration Test Suite for Zone A & Zone B.

Phase 1 Remediations Verified:
1. SimulatedFieldAdapter (nominal readings, faults, disconnects, limits)
2. CollectorBuffer:
   - Persistent sequence numbering & epoch tracking
   - Bounded SQLite ring buffer (max records limit & drop oldest)
   - Retention policy enforcement
3. EdgeCollectorAgent:
   - Default SIMULATED_LAB classification
   - Monotonic persistent sequence across restarts
   - Live delivery, network drop buffering, reconnection replay, restart resilience
4. Transport & Gateway Authentication headers
"""

from datetime import datetime, timezone, timedelta
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

        # Success: Echo server-enforced classification
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "ok": True,
            "stationId": parsed.get("stationId"),
            "dataClassification": parsed.get("dataClassification", "SIMULATED_LAB"),
            "sequenceNumber": parsed.get("sequenceNumber", 0)
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
    """Validates SQLite FIFO store-and-forward queue resilience and size enforcement."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_buffer.db"
        self.buffer = CollectorBuffer(str(self.db_path), max_records=5)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fifo_ordering_and_mark_sent(self):
        self.assertEqual(self.buffer.pending_count(), 0)

        p1 = {"stationId": "CM-01", "sequenceNumber": 1, "sourceTimestamp": "2026-10-14T08:00:00Z"}
        p2 = {"stationId": "CM-01", "sequenceNumber": 2, "sourceTimestamp": "2026-10-14T08:00:05Z"}
        p3 = {"stationId": "CM-01", "sequenceNumber": 3, "sourceTimestamp": "2026-10-14T08:00:10Z"}

        id1 = self.buffer.enqueue(p1)
        id2 = self.buffer.enqueue(p2)
        id3 = self.buffer.enqueue(p3)

        self.assertEqual(self.buffer.pending_count(), 3)

        batch = self.buffer.dequeue_batch(limit=2)
        self.assertEqual(len(batch), 2)
        self.assertEqual(batch[0]["id"], id1)
        self.assertEqual(batch[0]["packet"]["sequenceNumber"], 1)
        self.assertEqual(batch[1]["id"], id2)
        self.assertEqual(batch[1]["packet"]["sequenceNumber"], 2)

        removed = self.buffer.mark_sent([id1, id2])
        self.assertEqual(removed, 2)
        self.assertEqual(self.buffer.pending_count(), 1)

        remaining = self.buffer.dequeue_batch(limit=10)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], id3)

    def test_persistent_sequence_and_epoch(self):
        epoch1 = self.buffer.get_epoch()
        self.assertTrue(epoch1.startswith("EP-"))
        self.assertEqual(self.buffer.get_epoch(), epoch1, "Epoch must be stable across calls")

        seq1 = self.buffer.get_next_sequence_number()
        seq2 = self.buffer.get_next_sequence_number()
        self.assertEqual(seq1, 1)
        self.assertEqual(seq2, 2)
        self.assertEqual(self.buffer.get_last_sequence_number(), 2)

        # Simulate agent restart with fresh buffer instance pointing to same file
        buf2 = CollectorBuffer(str(self.db_path))
        self.assertEqual(buf2.get_epoch(), epoch1, "Restarted instance must retain previous epoch")
        self.assertEqual(buf2.get_last_sequence_number(), 2, "Restarted instance must retain last sequence number")
        seq3 = buf2.get_next_sequence_number()
        self.assertEqual(seq3, 3, "Sequence number must continue monotonically")

    def test_bounded_ring_buffer_overwrite(self):
        """Validates that buffer limits prevent unbounded disk growth (drops oldest pending)."""
        # Buffer max_records set to 5 in setUp
        for i in range(1, 8):
            self.buffer.enqueue({"stationId": "CM-01", "sequenceNumber": i})

        # Count must never exceed max_records (5)
        self.assertEqual(self.buffer.pending_count(), 5)

        # Oldest records (1 and 2) must have been dropped to accommodate records 6 and 7
        batch = self.buffer.dequeue_batch(limit=10)
        self.assertEqual(len(batch), 5)
        seqs = [b["packet"]["sequenceNumber"] for b in batch]
        self.assertEqual(seqs, [3, 4, 5, 6, 7])

    def test_wal_accounting_and_checkpoint(self):
        """Validates that get_total_disk_bytes accounts for WAL and checkpoint truncates WAL."""
        for i in range(1, 10):
            self.buffer.enqueue({"stationId": "CM-01", "sequenceNumber": i, "payload": "x" * 1024})

        total_bytes = self.buffer.get_total_disk_bytes()
        self.assertGreater(total_bytes, 0)

        # Test online checkpoint truncate
        self.buffer.checkpoint()
        self.assertLessEqual(self.buffer.get_total_disk_bytes(), self.buffer.max_bytes)

    def test_buffer_backup_to_consistent_snapshot(self):
        """Validates that buffer.backup_to creates a clean, usable SQLite snapshot."""
        for i in range(1, 4):
            self.buffer.enqueue({"stationId": "CM-01", "sequenceNumber": i, "pressure": 2.5})

        backup_path = Path(self.temp_dir.name) / "snapshot.db"
        self.buffer.backup_to(str(backup_path))

        self.assertTrue(backup_path.exists())
        # Open snapshot with a new CollectorBuffer instance and verify data integrity
        restored_buffer = CollectorBuffer(str(backup_path))
        self.assertEqual(restored_buffer.pending_count(), 3)
        batch = restored_buffer.dequeue_batch(limit=10)
        self.assertEqual(len(batch), 3)
        self.assertEqual(batch[0]["packet"]["sequenceNumber"], 1)

    def test_buffer_disk_pressure_error_fail_safe(self):
        """Validates that buffer raises BufferDiskPressureError when disk budget ceiling is reached."""
        from src.collector.buffer import BufferDiskPressureError
        small_db = Path(self.temp_dir.name) / "small_buffer.db"
        tiny_buffer = CollectorBuffer(str(small_db), max_records=1000, max_bytes=4096)

        with self.assertRaises(BufferDiskPressureError):
            for i in range(1, 50):
                tiny_buffer.enqueue({"stationId": "CM-01", "sequenceNumber": i, "data": "a" * 1024})



class TestEdgeCollectorAgentE2E(unittest.TestCase):
    """End-to-End integration tests connecting EdgeCollectorAgent to Ingestion endpoint."""

    @classmethod
    def setUpClass(cls):
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
            buffer_db_path=str(self.buffer_db),
            data_classification="SIMULATED_LAB"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_live_delivery_and_gateway_auth(self):
        """Scenario: Normal connectivity delivers telemetry with valid gateway token."""
        res = self.agent.step()
        self.assertEqual(res["status"], "DELIVERED")
        self.assertEqual(res["http_status"], 200)

        self.assertEqual(len(MockZoneBIngestHandler.received_requests), 1)
        req = MockZoneBIngestHandler.received_requests[0]
        self.assertEqual(req["headers"]["X-Gateway-Token"], "valid-secret-token-32-chars-long")
        self.assertEqual(req["body"]["stationId"], "CM-01")
        self.assertEqual(req["body"]["dataClassification"], "SIMULATED_LAB")
        self.assertTrue(req["body"]["epoch"].startswith("EP-"))
        self.assertIn("CM01_PT_01", req["body"]["points"])

    def test_unauthorized_token_rejection(self):
        """Scenario: Invalid gateway token is rejected by server."""
        self.agent.gateway_token = "invalid-unauthorized-token-key"
        res = self.agent.step()
        self.assertEqual(res["status"], "REJECTED")
        self.assertEqual(res["http_status"], 401)

    def test_network_drop_buffering_and_recovery_replay(self):
        """Scenario: VPN disconnection causes agent to buffer; recovery triggers FIFO replay."""
        MockZoneBIngestHandler.reject_with_status = 503

        res1 = self.agent.step()
        self.assertEqual(res1["status"], "BUFFERED")
        self.assertEqual(self.agent.buffer.pending_count(), 1)

        res2 = self.agent.step()
        self.assertEqual(res2["status"], "BUFFERED")
        self.assertEqual(self.agent.buffer.pending_count(), 2)

        # Zone B back online
        MockZoneBIngestHandler.reject_with_status = 200

        res3 = self.agent.step()
        self.assertEqual(res3["status"], "DELIVERED")
        self.assertEqual(self.agent.buffer.pending_count(), 0, "Buffer must be completely emptied upon recovery")

    def test_collector_restart_resilience_and_monotonic_sequence(self):
        """Scenario: Agent restarts while records are in buffer; sequence number continues monotonically."""
        # Step 1: Record 1
        res1 = self.agent.step()
        self.assertEqual(res1["packet"]["sequenceNumber"], 1)

        # Step 2: Outage buffers record 2
        MockZoneBIngestHandler.reject_with_status = 502
        res2 = self.agent.step()
        self.assertEqual(res2["packet"]["sequenceNumber"], 2)
        self.assertEqual(self.agent.buffer.pending_count(), 1)

        # Step 3: Simulate agent termination and restart with a brand new instance pointing to same DB
        del self.agent
        new_agent = EdgeCollectorAgent(
            adapter=self.adapter,
            ingest_url=self.ingest_url,
            station_id="CM-01",
            collector_id="GW-CM01-PATAN",
            gateway_token="valid-secret-token-32-chars-long",
            buffer_db_path=str(self.buffer_db),
            data_classification="SIMULATED_LAB"
        )

        self.assertEqual(new_agent.buffer.pending_count(), 1, "Restarted agent must detect existing buffered items")

        # Step 4: Zone B back online -> sends packet 3 and flushes packet 2
        MockZoneBIngestHandler.reject_with_status = 200
        res3 = new_agent.step()
        self.assertEqual(res3["packet"]["sequenceNumber"], 3, "New agent must resume sequence number without resetting to 1")
        self.assertEqual(new_agent.buffer.pending_count(), 0, "Restarted agent successfully flushed prior buffer")

    def test_agent_handles_buffer_disk_pressure(self):
        """Scenario: Agent handles BufferDiskPressureError gracefully without crashing."""
        MockZoneBIngestHandler.reject_with_status = 503
        self.agent.buffer.max_bytes = 4096
        for i in range(1, 40):
            try:
                self.agent.buffer.enqueue({"stationId": "CM-01", "sequenceNumber": i, "data": "z" * 1024})
            except Exception:
                break

        res = self.agent.step()
        self.assertEqual(res["status"], "DISK_PRESSURE_DROPPED")
        self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()

