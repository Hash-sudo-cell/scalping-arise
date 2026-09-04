"""
Scalping Arise — BOS and CHOCH Tests

Tests for Break of Structure and Change of Character detection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.market_analysis.bos_choch import detect_bos, detect_choch
from app.modules.market_analysis.models import (
    BOSDirection,
    CHOCHDirection,
    StructureLabel,
    StructurePoint,
    SwingPoint,
    SwingType,
    TrendState,
)
from app.modules.market_data.models import Instrument, NormalizedCandle, SourceType, Timeframe


def _candle(
    ts_offset: int,
    high: float,
    low: float,
    close: float,
    open_price: float = 100.0,
) -> NormalizedCandle:
    return NormalizedCandle(
        instrument=Instrument.XAU_USD,
        provider_instrument="XAU/USD",
        source_type=SourceType.SPOT,
        timeframe=Timeframe.H1,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=ts_offset),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        is_closed=True,
        source="test",
    )


def _structure_point(
    label: StructureLabel,
    price: float,
    index: int,
    swing_type: SwingType = SwingType.SWING_HIGH,
) -> StructurePoint:
    swing = SwingPoint(
        index=index,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index),
        price=price,
        swing_type=swing_type,
        confirmed=True,
        timeframe="1h",
    )
    return StructurePoint(swing=swing, label=label, reason="test")


class TestBOSDetection:
    def test_bullish_bos(self) -> None:
        """Price closing above a swing high in bullish/unclear trend should be bullish BOS."""
        candles = [
            _candle(0, high=100, low=90, close=95),
            _candle(1, high=102, low=92, close=98),
            _candle(2, high=105, low=95, close=100),
            _candle(3, high=108, low=98, close=103),
            _candle(4, high=112, low=100, close=111),  # Breaks above swing high at 105
        ]
        structure = [
            _structure_point(StructureLabel.HH, 105.0, 2, SwingType.SWING_HIGH),
        ]
        events = detect_bos(candles, structure, TrendState.BULLISH, "close")
        bullish = [e for e in events if e.direction == BOSDirection.BULLISH_BOS]
        assert len(bullish) == 1
        assert bullish[0].broken_level == 105.0
        assert bullish[0].break_price == 111.0

    def test_bearish_bos(self) -> None:
        """Price closing below a swing low in bearish/unclear trend should be bearish BOS."""
        candles = [
            _candle(0, high=110, low=100, close=105),
            _candle(1, high=108, low=98, close=102),
            _candle(2, high=105, low=95, close=100),
            _candle(3, high=102, low=92, close=97),
            _candle(4, high=98, low=88, close=89),  # Breaks below swing low at 95
        ]
        structure = [
            _structure_point(StructureLabel.LL, 95.0, 2, SwingType.SWING_LOW),
        ]
        events = detect_bos(candles, structure, TrendState.BEARISH, "close")
        bearish = [e for e in events if e.direction == BOSDirection.BEARISH_BOS]
        assert len(bearish) == 1
        assert bearish[0].broken_level == 95.0
        assert bearish[0].break_price == 89.0

    def test_no_break(self) -> None:
        """Price not breaking the swing level should produce no BOS."""
        candles = [
            _candle(0, high=100, low=90, close=95),
            _candle(1, high=103, low=93, close=98),
            _candle(2, high=104, low=94, close=99),  # Does not break 105
        ]
        structure = [
            _structure_point(StructureLabel.HH, 105.0, 1, SwingType.SWING_HIGH),
        ]
        events = detect_bos(candles, structure, TrendState.BULLISH, "close")
        assert len(events) == 0

    def test_wick_only_non_confirmation(self) -> None:
        """With close-based confirmation, a wick above without close should not trigger BOS."""
        candles = [
            _candle(0, high=100, low=90, close=95),
            _candle(1, high=108, low=95, close=100),  # Wick above 105 but close below
        ]
        structure = [
            _structure_point(StructureLabel.HH, 105.0, 0, SwingType.SWING_HIGH),
        ]
        events = detect_bos(candles, structure, TrendState.BULLISH, "close")
        assert len(events) == 0

    def test_wick_confirmation(self) -> None:
        """With wick-based confirmation, a wick above should trigger BOS."""
        candles = [
            _candle(0, high=100, low=90, close=95),
            _candle(1, high=108, low=95, close=100),  # Wick above 105
        ]
        structure = [
            _structure_point(StructureLabel.HH, 105.0, 0, SwingType.SWING_HIGH),
        ]
        events = detect_bos(candles, structure, TrendState.BULLISH, "wick")
        assert len(events) == 1

    def test_insufficient_structure(self) -> None:
        """No structure points should produce no BOS."""
        candles = [_candle(i, high=100 + i, low=90 + i, close=95 + i) for i in range(5)]
        events = detect_bos(candles, [], TrendState.BULLISH, "close")
        assert len(events) == 0

    def test_empty_candles(self) -> None:
        """Empty candles list should produce no BOS."""
        structure = [_structure_point(StructureLabel.HH, 105.0, 0)]
        events = detect_bos([], structure, TrendState.BULLISH, "close")
        assert len(events) == 0


class TestCHOCHDetection:
    def test_bullish_choch(self) -> None:
        """In bearish trend, price closing above swing high should be bullish CHOCH."""
        candles = [
            _candle(0, high=100, low=90, close=95),
            _candle(1, high=102, low=92, close=98),
            _candle(2, high=105, low=95, close=100),
            _candle(3, high=110, low=100, close=108),  # Breaks above 105
        ]
        structure = [
            _structure_point(StructureLabel.LH, 105.0, 2, SwingType.SWING_HIGH),
        ]
        events = detect_choch(candles, structure, TrendState.BEARISH, "close")
        bullish = [e for e in events if e.direction == CHOCHDirection.BULLISH_CHOCH]
        assert len(bullish) == 1
        assert bullish[0].broken_level == 105.0

    def test_bearish_choch(self) -> None:
        """In bullish trend, price closing below swing low should be bearish CHOCH."""
        candles = [
            _candle(0, high=110, low=100, close=105),
            _candle(1, high=108, low=98, close=102),
            _candle(2, high=105, low=95, close=100),
            _candle(3, high=100, low=88, close=89),  # Breaks below 95
        ]
        structure = [
            _structure_point(StructureLabel.HL, 95.0, 2, SwingType.SWING_LOW),
        ]
        events = detect_choch(candles, structure, TrendState.BULLISH, "close")
        bearish = [e for e in events if e.direction == CHOCHDirection.BEARISH_CHOCH]
        assert len(bearish) == 1
        assert bearish[0].broken_level == 95.0

    def test_bos_not_choch(self) -> None:
        """In bullish trend, breaking above swing high should NOT produce CHOCH."""
        candles = [
            _candle(0, high=100, low=90, close=95),
            _candle(1, high=110, low=100, close=108),
        ]
        structure = [
            _structure_point(StructureLabel.HH, 105.0, 0, SwingType.SWING_HIGH),
        ]
        events = detect_choch(candles, structure, TrendState.BULLISH, "close")
        bullish_choch = [e for e in events if e.direction == CHOCHDirection.BULLISH_CHOCH]
        assert len(bullish_choch) == 0

    def test_no_choch_ranging(self) -> None:
        """In ranging trend, no CHOCH should be detected."""
        candles = [
            _candle(0, high=100, low=90, close=95),
            _candle(1, high=110, low=100, close=108),
        ]
        structure = [
            _structure_point(StructureLabel.HH, 105.0, 0, SwingType.SWING_HIGH),
        ]
        events = detect_choch(candles, structure, TrendState.RANGING, "close")
        assert len(events) == 0

    def test_choch_has_prior_structure(self) -> None:
        """CHOCH events should include the prior structure description."""
        candles = [
            _candle(0, high=100, low=90, close=95),
            _candle(1, high=110, low=100, close=108),
        ]
        structure = [
            _structure_point(StructureLabel.LH, 105.0, 0, SwingType.SWING_HIGH),
        ]
        events = detect_choch(candles, structure, TrendState.BEARISH, "close")
        assert len(events) == 1
        assert events[0].prior_structure != ""
