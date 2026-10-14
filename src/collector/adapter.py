"""Abstract Base Class for Zone A Read-Only Edge Collector Adapters.

CRITICAL ARCHITECTURAL CONSTRAINT:
This interface is strictly READ-ONLY. No write, control, or actuation methods
are defined or permitted. The collector must NEVER alter PLC/SCADA operational state.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class EdgeCollectorAdapter(ABC):
    """Abstract base class for unidirectional, read-only field data collection."""

    @abstractmethod
    def connect(self) -> bool:
        """Establishes read-only communication channel with field instruments."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Safely closes connection to field instruments."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Returns True if the read-only communication channel is healthy."""
        pass

    @abstractmethod
    def read_point(self, point_id: str) -> dict[str, Any]:
        """
        Reads an individual telemetry point.

        Returns a dictionary with:
            point_id: Unique point identifier (e.g. 'CM01_PT_01')
            value: Float or int measured value
            unit: Engineering unit string (e.g. 'bar', 'm3/h', 'NTU')
            quality: 'GOOD' | 'BAD' | 'UNCERTAIN'
            raw_timestamp: Source device timestamp
        """
        pass

    @abstractmethod
    def read_all_points(self) -> dict[str, dict[str, Any]]:
        """
        Reads all configured points in a single coordinated cycle.

        Returns mapping: { point_id: point_data_dict }
        """
        pass
