"""Zone A Edge Collector Module.

Provides read-only adapters, point definitions, local buffer, and autonomous
edge agent for transmitting water telemetry from Zone A (Station/OT)
to Zone B (Operations Center) securely.
"""

from src.collector.adapter import EdgeCollectorAdapter
from src.collector.simulated_adapter import SimulatedFieldAdapter
from src.collector.buffer import CollectorBuffer
from src.collector.edge_agent import EdgeCollectorAgent

__all__ = [
    "EdgeCollectorAdapter",
    "SimulatedFieldAdapter",
    "CollectorBuffer",
    "EdgeCollectorAgent",
]
