"""
Scalping Arise — Event Provider Interface

Abstract interface for external event/news data providers.
Implementations can be added behind this interface without
coupling the core engine to any specific provider.

Tests use MockEventProvider — no network access required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from app.modules.news_intelligence.models import NormalizedEvent


class EventProvider(ABC):
    """
    Abstract event provider interface.

    Concrete implementations fetch from external APIs.
    The mock provider returns deterministic fixtures for tests.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of this provider."""
        ...

    @abstractmethod
    async def fetch_events(
        self,
        *,
        instrument: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[NormalizedEvent]:
        """
        Fetch normalized events.

        Args:
            instrument: Filter events affecting this instrument (optional).
            since: Only return events after this timestamp (optional).
            limit: Maximum number of events to return.

        Returns:
            List of normalized events, newest first.
        """
        ...

    @abstractmethod
    async def get_latest_update_time(self) -> Optional[datetime]:
        """
        Return the timestamp of the most recent data update from this provider.

        Returns None if the provider has never been queried.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Whether the provider is currently reachable/operational."""
        ...


class MockEventProvider(EventProvider):
    """
    Deterministic mock event provider for testing.

    Returns pre-configured events without any network access.
    """

    def __init__(self, events: Optional[list[NormalizedEvent]] = None) -> None:
        self._events = events or []
        self._available = True
        self._last_update: Optional[datetime] = datetime.now(timezone.utc)

    @property
    def provider_name(self) -> str:
        return "mock_provider"

    async def fetch_events(
        self,
        *,
        instrument: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[NormalizedEvent]:
        """Return pre-configured events, optionally filtered."""
        result = self._events

        if since is not None:
            result = [e for e in result if e.timestamp >= since]

        if instrument is not None:
            result = [
                e for e in result
                if instrument in e.affected_instruments
                or not e.affected_instruments
            ]

        return result[:limit]

    async def get_latest_update_time(self) -> Optional[datetime]:
        return self._last_update

    async def is_available(self) -> bool:
        return self._available

    def set_events(self, events: list[NormalizedEvent]) -> None:
        """Set the events this provider returns."""
        self._events = events
        self._last_update = datetime.now(timezone.utc)

    def set_available(self, available: bool) -> None:
        """Toggle provider availability."""
        self._available = available
