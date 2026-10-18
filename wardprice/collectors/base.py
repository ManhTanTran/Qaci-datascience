"""Per-source collector interface used by reviewed adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import CollectionTarget, DiscoveredUrl


class BaseCollector(ABC):
    """Contract for a source-specific adapter; networking policy stays shared."""

    source_name: str

    @abstractmethod
    def discover(
        self, target: CollectionTarget, property_type: str, limit: int
    ) -> list[DiscoveredUrl]:
        """Return only direct listing URLs admitted by the source adapter."""

    @abstractmethod
    def extract(self, listing_url: str) -> dict[str, Any]:
        """Extract a single listing and preserve source evidence."""

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Report source access readiness without bypassing its access policy."""
