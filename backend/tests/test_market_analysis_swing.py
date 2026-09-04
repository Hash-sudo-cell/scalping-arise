"""
Scalping Arise — Swing Detection Tests

Tests for deterministic swing-high and swing-low detection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.market_analysis.swing_detection import detect_swings
from app.modules.market_analysis.models import SwingType
from app.modules.market_data.models import Instrument, NormalizedCandle, SourceType, Timeframe


def _candle(
    ts_offset: int,
    high: float,
    low: float,
    open_price: float = 100.0,
    close_price: float = 100.0,
    instrument: Instrument = Instrument.XAU_USD,
    timeframe: Timeframe = Timeframe.H1,
    source: str = "test",
) -> NormalizedCandle:
    """Create a test candle at a given offset from base time."""
    return NormalizedCandle(
        instrument=instrument,
        provider_instrument="XAU/USD",
        source_type=SourceType.SPOT,
        timeframe=timeframe,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=ts_offset),
        open=open_price,
        high=high,
        low=low,
        close=close_price,
        volume=1000.0,
        is_closed=True,
        source=source,
    )


class TestSwingDetection:
    def test_clear_swing_high(self) -> None:
        """A candle whose high exceeds all neighbors should be detected as swing high."""
        candles = [
            _candle(0, high=100, low=90),
            _candle(1, high=101, low=91),
            _candle(2, high=110, low=95),  # swing high
            _candle(3, high=102, low=92),
            _candle(4, high=101, low=91),
            _candle(5, high=100, low=90),
        ]
        swings = detect_swings(candles, lookback=2)
        assert len(swings) >= 1
        highs = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
        assert len(highs) == 1
        assert highs[0].price == 110.0

    def test_clear_swing_low(self) -> None:
        """A candle whose low is below all neighbors should be detected as swing low."""
        candles = [
            _candle(0, high=110, low=100),
            _candle(1, high=109, low=99),
            _candle(2, high=105, low=90),  # swing low
            _candle(3, high=108, low=98),
            _candle(4, high=109, low=99),
            _candle(5, high=110, low=100),
        ]
        swings = detect_swings(candles, lookback=2)
        lows = [s for s in swings if s.swing_type == SwingType.SWING_LOW]
        assert len(lows) == 1
        assert lows[0].price == 90.0

    def test_no_swing_uniform(self) -> None:
        """Uniform candles should produce no swings."""
        candles = [_candle(i, high=100, low=90) for i in range(10)]
        swings = detect_swings(candles, lookback=2)
        assert len(swings) == 0

    def test_insufficient_candles(self) -> None:
        """Fewer than 2*lookback+1 candles should produce no swings."""
        candles = [_candle(i, high=100 + i, low=90 + i) for i in range(3)]
        swings = detect_swings(candles, lookback=2)
        assert len(swings) == 0

    def test_edge_candles_not_detected(self) -> None:
        """Candles at the start/end of the series cannot be swings (insufficient neighbors)."""
        candles = [
            _candle(0, high=200, low=80),  # Edge — too high, should NOT be swing
            _candle(1, high=101, low=91),
            _candle(2, high=102, low=92),
            _candle(3, high=101, low=91),
            _candle(4, high=100, low=90),
        ]
        swings = detect_swings(candles, lookback=2)
        # The first candle (index 0) should not be detected even though it has the highest high
        highs = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
        for h in highs:
            assert h.index > 0

    def test_multiple_swings(self) -> None:
        """Multiple swing points should be detected in a zigzag pattern."""
        candles = [
            _candle(0, high=100, low=90),
            _candle(1, high=105, low=95),
            _candle(2, high=110, low=98),  # swing high
            _candle(3, high=105, low=95),
            _candle(4, high=100, low=88),  # swing low
            _candle(5, high=105, low=95),
            _candle(6, high=112, low=98),  # swing high
            _candle(7, high=105, low=95),
            _candle(8, high=100, low=90),
        ]
        swings = detect_swings(candles, lookback=2)
        highs = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
        lows = [s for s in swings if s.swing_type == SwingType.SWING_LOW]
        assert len(highs) >= 2
        assert len(lows) >= 1

    def test_swings_sorted_by_timestamp(self) -> None:
        """Detected swings should be chronologically ordered."""
        candles = [
            _candle(0, high=100, low=90),
            _candle(1, high=105, low=95),
            _candle(2, high=110, low=98),
            _candle(3, high=105, low=95),
            _candle(4, high=100, low=88),
            _candle(5, high=105, low=95),
            _candle(6, high=112, low=98),
            _candle(7, high=105, low=95),
            _candle(8, high=100, low=90),
        ]
        swings = detect_swings(candles, lookback=2)
        for i in range(1, len(swings)):
            assert swings[i].timestamp >= swings[i - 1].timestamp

    def test_swings_carry_timeframe(self) -> None:
        """Detected swings should carry the candle timeframe."""
        candles = [
            _candle(0, high=100, low=90, timeframe=Timeframe.M15),
            _candle(1, high=105, low=95, timeframe=Timeframe.M15),
            _candle(2, high=110, low=98, timeframe=Timeframe.M15),
            _candle(3, high=105, low=95, timeframe=Timeframe.M15),
            _candle(4, high=100, low=90, timeframe=Timeframe.M15),
            _candle(5, high=105, low=95, timeframe=Timeframe.M15),
            _candle(6, high=110, low=98, timeframe=Timeframe.M15),
            _candle(7, high=105, low=95, timeframe=Timeframe.M15),
            _candle(8, high=100, low=90, timeframe=Timeframe.M15),
        ]
        swings = detect_swings(candles, lookback=2)
        for s in swings:
            assert s.timeframe == "15m"

    def test_lookback_1(self) -> None:
        """With lookback=1, only immediate neighbors need to be lower/higher."""
        candles = [
            _candle(0, high=100, low=90),
            _candle(1, high=110, low=95),  # swing high (lookback=1)
            _candle(2, high=100, low=90),
        ]
        swings = detect_swings(candles, lookback=1)
        highs = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
        assert len(highs) == 1
        assert highs[0].price == 110.0
