"""
Scalping Arise — Market Data Provider Abstraction

Defines the Protocol that all provider adapters must implement.
The rest of the application depends on this abstraction, not on
specific provider implementations.
"""

from __future__ import annotations

from typing import Optional, Protocol

from app.modules.market_data.models import (
    Instrument,
    LatestPrice,
    NormalizedCandle,
    ProviderCapabilities,
    ProviderHealth,
    Timeframe,
)


class MarketDataProvider(Protocol):
    """
    Protocol for market data provider adapters.

    Every adapter must implement these methods.
    The adapter is responsible for:
        - Translating provider-specific symbols
        - Converting provider responses to NormalizedCandle
        - Handling provider-specific errors
        - Reporting health status
    """

    @property
    def name(self) -> str:
        """Provider identifier string."""
        ...

    async def health_check(self) -> ProviderHealth:
        """
        Check provider availability and data freshness.

        Returns a ProviderHealth with status HEALTHY/DEGRADED/UNAVAILABLE.
        """
        ...

    def get_capabilities(self) -> ProviderCapabilities:
        """Return this provider's supported instruments and timeframes."""
        ...

    def map_symbol(self, instrument: Instrument) -> str:
        """Map canonical instrument to provider-specific symbol."""
        ...

    async def fetch_historical_candles(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        limit: int = 100,
    ) -> list[NormalizedCandle]:
        """
        Fetch historical closed candles.

        Returns a list of NormalizedCandle sorted by timestamp ascending.
        """
        ...

    async def fetch_latest_price(
        self,
        instrument: Instrument,
    ) -> Optional[LatestPrice]:
        """
        Fetch the most recent price for an instrument.

        May represent a forming candle's current price.
        Returns None if data is unavailable.
        """
        ...

    async def fetch_latest_candle(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> Optional[NormalizedCandle]:
        """
        Fetch the most recent candle (forming or closed).

        Returns None if data is unavailable.
        """
        ...
