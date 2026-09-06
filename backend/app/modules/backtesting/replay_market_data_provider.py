"""
Scalping Arise — Historical Replay Market Data Provider

Implements the MarketDataProvider protocol using pre-loaded historical
candle data. The simulated clock controls data visibility — only candles
with timestamp <= current_replay_time are accessible.

This provider MUST never:
- Call live market data APIs
- Return future candles
- Use current/live prices
- Leak data from outside the historical dataset
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_data.models import (
    Instrument,
    LatestPrice,
    NormalizedCandle,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
    SourceType,
    Timeframe,
    TimeframeCapability,
)

logger = logging.getLogger(__name__)


class ReplayMarketDataProvider:
    """
    MarketDataProvider implementation backed by pre-loaded historical data.

    The simulated clock (current_time) controls what data is visible.
    Requests for data beyond current_time raise RuntimeError — never
    silently fall back to live data.
    """

    def __init__(self) -> None:
        # Historical data indexed by (instrument, timeframe)
        self._candles: dict[tuple[str, str], list[NormalizedCandle]] = {}
        # Current replay timestamp — only data <= this time is visible
        self._current_time: Optional[datetime] = None
        self._instrument: Optional[Instrument] = None
        self._timeframe: Optional[Timeframe] = None

    def load_data(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        candles: list[NormalizedCandle],
    ) -> None:
        """Load historical candle data for a specific instrument/timeframe."""
        # Store sorted by timestamp ascending
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        self._candles[(instrument.value, timeframe.value)] = sorted_candles
        self._instrument = instrument
        self._timeframe = timeframe
        logger.debug(
            "Loaded %d historical candles for %s %s",
            len(sorted_candles),
            instrument.value,
            timeframe.value,
        )

    def set_current_time(self, time: datetime) -> None:
        """
        Advance the simulated clock.

        After this call, only candles with timestamp <= time are visible.
        """
        self._current_time = time

    @property
    def name(self) -> str:
        return "replay"

    async def health_check(self) -> ProviderHealth:
        """Report healthy if data is loaded and current time is set."""
        if self._current_time is not None and self._candles:
            return ProviderHealth(
                provider_name="replay",
                status=ProviderHealthStatus.HEALTHY,
                latency_ms=0.0,
                last_data_timestamp=self._current_time,
            )
        return ProviderHealth(
            provider_name="replay",
            status=ProviderHealthStatus.DEGRADED,
        )

    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities based on loaded data."""
        instruments = set()
        timeframes = set()
        for (inst, tf) in self._candles:
            instruments.add(inst)
            timeframes.add(tf)
        tf_caps = {tf: TimeframeCapability.NATIVE for tf in timeframes}
        return ProviderCapabilities(
            provider_name="replay",
            supported_instruments=[Instrument(i) for i in instruments],
            timeframe_capabilities=tf_caps,
            max_historical_candles=10000,
        )

    def map_symbol(self, instrument: Instrument) -> str:
        """Map canonical instrument — pass through for replay."""
        return instrument.value

    def _get_visible_candles(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> list[NormalizedCandle]:
        """Get candles visible at current replay time. Raises on missing data."""
        key = (instrument.value, timeframe.value)
        all_candles = self._candles.get(key, [])

        if not all_candles:
            raise RuntimeError(
                f"No historical data loaded for {instrument.value} {timeframe.value}. "
                "Cannot serve replay data without pre-loaded candles."
            )

        if self._current_time is None:
            raise RuntimeError(
                "Replay current_time not set. Call set_current_time() before data access."
            )

        # Filter to candles visible at current replay time
        visible = [c for c in all_candles if c.timestamp <= self._current_time]

        if not visible:
            raise RuntimeError(
                f"No candles visible at replay time {self._current_time.isoformat()} "
                f"for {instrument.value} {timeframe.value}. "
                f"Earliest candle: {all_candles[0].timestamp.isoformat()}"
            )

        return visible

    async def fetch_historical_candles(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        limit: int = 100,
    ) -> list[NormalizedCandle]:
        """
        Fetch historical candles up to current replay time.

        Returns candles sorted by timestamp ascending, limited to `limit`.
        Raises RuntimeError if requesting data beyond available range.
        """
        visible = self._get_visible_candles(instrument, timeframe)

        # Return the most recent `limit` candles
        result = visible[-limit:]

        logger.debug(
            "Replay fetch: %s %s — returned %d candles (up to %s)",
            instrument.value,
            timeframe.value,
            len(result),
            self._current_time.isoformat() if self._current_time else "none",
        )
        return result

    async def fetch_latest_price(
        self,
        instrument: Instrument,
    ) -> Optional[LatestPrice]:
        """
        Return the latest price from visible candles.

        Uses the close of the most recent visible candle for the instrument's
        primary timeframe.
        """
        if self._timeframe is None:
            return None

        try:
            visible = self._get_visible_candles(instrument, self._timeframe)
            if not visible:
                return None

            latest = visible[-1]
            return LatestPrice(
                instrument=instrument,
                provider_instrument=instrument.value,
                bid=latest.close,
                ask=latest.close,
                price=latest.close,
                timestamp=latest.timestamp,
                source="replay",
                source_type=SourceType.SPOT,
            )
        except RuntimeError:
            return None

    async def fetch_latest_candle(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> Optional[NormalizedCandle]:
        """
        Fetch the most recent visible candle.

        Returns None if no data available.
        """
        try:
            visible = self._get_visible_candles(instrument, timeframe)
            return visible[-1] if visible else None
        except RuntimeError:
            return None
