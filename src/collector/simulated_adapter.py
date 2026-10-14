"""Simulated Field Adapter for Safe Lab Testing and E2E Verification.

Simulates physical water treatment plant instrumentation (pressure transmitter,
ultrasonic level transmitter, electromagnetic flow meter, turbidity sensor,
and residual chlorine analyzer) within calibrated engineering limits.
"""

from datetime import datetime, timezone
import math
import random
from typing import Any, Optional
from src.collector.adapter import EdgeCollectorAdapter


class SimulatedFieldAdapter(EdgeCollectorAdapter):
    """Safe, read-only field simulator for Zone A integration testing."""

    # Standard points configuration for a Chiang Mai Water Treatment Plant (CM-01 Pa Tan)
    DEFAULT_POINTS = {
        "CM01_PT_01": {"tag": "OUTLET_PRESSURE", "unit": "bar", "nominal": 2.50, "noise": 0.05, "min": 0.0, "max": 10.0},
        "CM01_LT_01": {"tag": "CLEAR_WATER_TANK_LEVEL", "unit": "%", "nominal": 78.0, "noise": 0.5, "min": 0.0, "max": 100.0},
        "CM01_FT_01": {"tag": "DISCHARGE_FLOW_RATE", "unit": "m3/h", "nominal": 2850.0, "noise": 25.0, "min": 0.0, "max": 50000.0},
        "CM01_AT_01": {"tag": "TREATED_WATER_TURBIDITY", "unit": "NTU", "nominal": 0.45, "noise": 0.03, "min": 0.0, "max": 100.0},
        "CM01_AT_02": {"tag": "RESIDUAL_CHLORINE", "unit": "mg/L", "nominal": 0.55, "noise": 0.02, "min": 0.0, "max": 10.0},
    }

    def __init__(self, points: Optional[dict[str, dict[str, Any]]] = None):
        self.points = points or self.DEFAULT_POINTS.copy()
        self._connected = False
        self._fault_override: dict[str, Any] = {}
        self._quality_override: dict[str, str] = {}
        self._step = 0

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def set_fault(self, point_id: str, value: float, quality: str = "GOOD") -> None:
        """Injects a specific test value or condition (e.g. pressure drop for testing alerts)."""
        self._fault_override[point_id] = value
        self._quality_override[point_id] = quality

    def clear_faults(self) -> None:
        """Clears all injected faults back to nominal baseline."""
        self._fault_override.clear()
        self._quality_override.clear()

    def read_point(self, point_id: str) -> dict[str, Any]:
        if not self._connected:
            raise ConnectionError("SimulatedFieldAdapter is disconnected")

        cfg = self.points.get(point_id)
        if not cfg:
            raise KeyError(f"Unknown point ID: {point_id}")

        self._step += 1
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check for injected fault
        if point_id in self._fault_override:
            val = round(self._fault_override[point_id], 2)
            qual = self._quality_override.get(point_id, "GOOD")
            return {
                "point_id": point_id,
                "tag": cfg["tag"],
                "value": val,
                "unit": cfg["unit"],
                "quality": qual,
                "source_timestamp": now_iso
            }

        # Calculate nominal reading with sinusoidal wave and slight Gaussian noise
        nominal = cfg["nominal"]
        noise = cfg["noise"]
        wave = math.sin(self._step * 0.1) * (noise * 1.5)
        jitter = (random.random() - 0.5) * noise
        raw_val = max(cfg["min"], min(cfg["max"], nominal + wave + jitter))

        return {
            "point_id": point_id,
            "tag": cfg["tag"],
            "value": round(raw_val, 2),
            "unit": cfg["unit"],
            "quality": "GOOD",
            "source_timestamp": now_iso
        }

    def read_all_points(self) -> dict[str, dict[str, Any]]:
        results = {}
        for pid in self.points.keys():
            results[pid] = self.read_point(pid)
        return results
