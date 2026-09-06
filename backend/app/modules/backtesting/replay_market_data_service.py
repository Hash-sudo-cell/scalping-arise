"""
Scalping Arise — Historical Replay Market Data Service

Wraps ReplayMarketDataProvider with the same public interface as
MarketDataService. Used during backtesting to ensure all downstream
services (Phase 3-8) receive historical data only.

This service MUST never:
- Connect to live providers
- Fetch current/live prices
- Access future candles
- Fall back to live data on error
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.modules.backtesting.replay_market_data_provider import ReplayMarketDataProvider
from app.modules.market_data.models import (
    CandlesResponse,
    Instrument,
    LatestPrice,
    MarketDataHealthResponse,
    NormalizedCandle,
    ProviderHealthStatus,
    SourceType,
    Timeframe,
)

logger = logging.getLogger(__name__)


class ReplayMarketDataService:
    """
    Market data service backed by historical replay data.

    Exposes the same interface as MarketDataService that downstream
    services (MarketAnalysis, TechnicalFeatures, Strategies, Signals,
    TradePlanning) depend on.
    """

    def __init__(self, provider: ReplayMarketDataProvider) -> None:
        self._provider = provider

    @property
    def active_source(self) -> Optional[str]:
        return "replay"

    @property
    def cache(self):
        """No-op cache for replay — data is pre-loaded."""
        return None

    @property
    def live_streaming(self) -> bool:
        """Live streaming is never active during replay."""
        return False

    def set_current_time(self, time: datetime) -> None:
        """Advance the simulated clock on the underlying provider."""
        self._provider.set_current_time(time)

    async def health_check(self) -> MarketDataHealthResponse:
        """Report health based on replay provider state."""
        provider_health = await self._provider.health_check()
        return MarketDataHealthResponse(
            status=provider_health.status,
            primary=provider_health,
            fallback=provider_health,
            active_source="replay",
        )

    async def fetch_candles(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        limit: int = 100,
    ) -> CandlesResponse:
        """
        Fetch candles from historical replay data.

        Returns CandlesResponse matching the live service interface.
        """
        candles = await self._provider.fetch_historical_candles(
            instrument, timeframe, limit,
        )
        return CandlesResponse(
            instrument=instrument,
            timeframe=timeframe,
            candles=candles,
            source="replay",
            source_type=SourceType.SPOT,
            count=len(candles),
            has_gaps=False,
        )

    async def fetch_latest_price(
        self,
        instrument: Instrument,
    ) -> Optional[LatestPrice]:
        """Fetch latest price from historical data at current replay time."""
        return await self._provider.fetch_latest_price(instrument)

    async def fetch_latest_candle(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> Optional[NormalizedCandle]:
        """Fetch latest candle from historical data at current replay time."""
        return await self._provider.fetch_latest_candle(instrument, timeframe)

    def get_capabilities(self) -> dict:
        """Return capabilities based on loaded historical data."""
        caps = self._provider.get_capabilities()
        return {
            "provider": "replay",
            "instruments": [i.value for i in caps.instruments],
            "timeframes": [t.value for t in caps.timeframes],
            "has_historical": caps.has_historical,
            "has_live": False,
        }

    def get_live_price(self) -> None:
        """No live price during replay."""
        return None

    def get_live_forming_candle(self, timeframe: Timeframe) -> Optional[NormalizedCandle]:
        """No forming candle during replay."""
        return None

    def get_live_status(self) -> Optional[dict]:
        """No live status during replay."""
        return None

    async def start_live_stream(self, *args, **kwargs) -> None:
        """Live streaming is not supported during replay."""
        logger.warning("Attempted to start live stream during replay — ignored")

    async def stop_live_stream(self) -> None:
        """No live stream to stop during replay."""
        pass

    async def close(self) -> None:
        """No cleanup needed for replay provider."""
        pass
