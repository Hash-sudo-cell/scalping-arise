"""
Scalping Arise — Candle Lifecycle State Machine

Manages the forming → closed transition for live candles across
multiple timeframes. When a new tick arrives, it determines whether
the current candle should be updated (still forming) or a new candle
should be started (previous period closed).

State transitions:
    FORMING → CLOSED: when tick timestamp crosses into a new candle period
    CLOSED → FORMING: when a new tick arrives for the next period
    FORMING → FORMING: tick within same period (update OHLC)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_data.models import (
    CandleState,
    Instrument,
    NormalizedCandle,
    SourceType,
    Timeframe,
)

logger = logging.getLogger(__name__)


def _candle_period_start(timestamp: datetime, timeframe: Timeframe) -> datetime:
    """
    Calculate the candle period start time for a given timestamp.

    Aligns the timestamp to the start of its candle period based on
    the timeframe interval. All calculations in UTC.
    """
    ts = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)
    interval = timeframe.interval_seconds

    epoch_seconds = ts.timestamp()
    period_start_seconds = (epoch_seconds // interval) * interval
    return datetime.fromtimestamp(period_start_seconds, tz=timezone.utc)


def _is_new_period(prev_timestamp: datetime, new_timestamp: datetime, timeframe: Timeframe) -> bool:
    """Check if a new timestamp belongs to a different candle period than the previous one."""
    prev_period = _candle_period_start(prev_timestamp, timeframe)
    new_period = _candle_period_start(new_timestamp, timeframe)
    return new_period > prev_period


class CandleLifecycle:
    """
    Manages candle lifecycle for a single timeframe.

    Tracks the current forming candle and transitions it to closed
    when new ticks arrive for a subsequent period.
    """

    def __init__(self, instrument: Instrument, timeframe: Timeframe) -> None:
        self._instrument = instrument
        self._timeframe = timeframe
        self._current: Optional[NormalizedCandle] = None
        self._state: CandleState = CandleState.FORMING
        self._last_update: Optional[datetime] = None
        self._closed_count: int = 0

    @property
    def instrument(self) -> Instrument:
        return self._instrument

    @property
    def timeframe(self) -> Timeframe:
        return self._timeframe

    @property
    def state(self) -> CandleState:
        return self._state

    @property
    def current_candle(self) -> Optional[NormalizedCandle]:
        return self._current

    @property
    def last_update(self) -> Optional[datetime]:
        return self._last_update

    @property
    def closed_count(self) -> int:
        return self._closed_count

    def update(self, tick_timestamp: datetime, open_price: float, high: float, low: float, close: float, volume: Optional[float] = None) -> Optional[NormalizedCandle]:
        """
        Process a new tick and update the lifecycle state.

        Returns the previously closed candle if a transition occurred,
        otherwise None.
        """
        closed_candle: Optional[NormalizedCandle] = None

        if self._current is None:
            # First tick — create forming candle
            self._current = self._create_candle(tick_timestamp, open_price, high, low, close, volume, is_closed=False)
            self._state = CandleState.FORMING
            self._last_update = tick_timestamp
            logger.debug(
                "New forming candle: %s %s @ %s",
                self._instrument.value, self._timeframe.value,
                tick_timestamp.isoformat(),
            )
            return None

        # Check if this tick belongs to a new period
        if self._last_update and _is_new_period(self._last_update, tick_timestamp, self._timeframe):
            # Close the current candle
            self._current = self._current.model_copy(update={"is_closed": True})
            self._state = CandleState.CLOSED
            closed_candle = self._current
            self._closed_count += 1

            logger.info(
                "Candle closed: %s %s @ %s (O=%.2f H=%.2f L=%.2f C=%.2f)",
                self._instrument.value, self._timeframe.value,
                closed_candle.timestamp.isoformat(),
                closed_candle.open, closed_candle.high,
                closed_candle.low, closed_candle.close,
            )

            # Start new forming candle
            self._current = self._create_candle(tick_timestamp, open_price, high, low, close, volume, is_closed=False)
            self._state = CandleState.FORMING
        else:
            # Same period — update the forming candle's OHLC
            new_high = max(self._current.high, high)
            new_low = min(self._current.low, low)
            self._current = self._current.model_copy(
                update={
                    "high": new_high,
                    "low": new_low,
                    "close": close,
                    "volume": (self._current.volume or 0) + (volume or 0) if volume else self._current.volume,
                }
            )
            self._state = CandleState.FORMING

        self._last_update = tick_timestamp
        return closed_candle

    def close_current(self) -> Optional[NormalizedCandle]:
        """
        Force-close the current forming candle.

        Used when the stream disconnects or at shutdown.
        Returns the closed candle if one existed.
        """
        if self._current is None:
            return None

        closed = self._current.model_copy(update={"is_closed": True})
        self._current = None
        self._state = CandleState.CLOSED
        self._closed_count += 1

        logger.debug(
            "Force-closed candle: %s %s @ %s",
            self._instrument.value, self._timeframe.value,
            closed.timestamp.isoformat(),
        )
        return closed

    def reset(self) -> None:
        """Reset the lifecycle state."""
        self._current = None
        self._state = CandleState.FORMING
        self._last_update = None

    def _create_candle(
        self,
        timestamp: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: Optional[float],
        is_closed: bool,
    ) -> NormalizedCandle:
        """Create a new NormalizedCandle with live source identity."""
        period_start = _candle_period_start(timestamp, self._timeframe)
        return NormalizedCandle(
            instrument=self._instrument,
            provider_instrument="XAU_USD",
            source_type=SourceType.LIVE,
            timeframe=self._timeframe,
            timestamp=period_start,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            is_closed=is_closed,
            source="oanda",
        )
