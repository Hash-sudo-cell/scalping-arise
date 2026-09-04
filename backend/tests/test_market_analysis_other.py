"""
Scalping Arise — Support/Resistance, Sessions, Regime, and Validation Tests

Combined tests for remaining analysis components.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.market_analysis.models import (
    AnalysisStatus,
    MarketRegime,
    MarketSession,
    StructureLabel,
    StructurePoint,
    SwingPoint,
    SwingType,
    TrendState,
    ZoneType,
)
from app.modules.market_analysis.regime import classify_regime
from app.modules.market_analysis.sessions import classify_session
from app.modules.market_analysis.support_resistance import detect_zones
from app.modules.market_analysis.validation import validate_analysis_context, build_analysis_context
from app.modules.market_analysis.config import MarketAnalysisSettings
from app.modules.market_data.models import (
    CandlesResponse,
    Instrument,
    NormalizedCandle,
    SourceType,
    Timeframe,
)
from pydantic import BaseModel
from datetime import datetime, timezone


def _candle(
    ts_offset: int,
    high: float,
    low: float,
    close: float,
    open_price: float = 100.0,
    timeframe: Timeframe = Timeframe.H1,
    source: str = "test",
) -> NormalizedCandle:
    return NormalizedCandle(
        instrument=Instrument.XAU_USD,
        provider_instrument="XAU/USD",
        source_type=SourceType.SPOT,
        timeframe=timeframe,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=ts_offset),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        is_closed=True,
        source=source,
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


# ---------------------------------------------------------------------------
# Support/Resistance Tests
# ---------------------------------------------------------------------------

class TestSupportResistance:
    def test_support_zone(self) -> None:
        """Swing lows at similar prices should form a support zone."""
        points = [
            _structure_point(StructureLabel.HL, 90.0, 5, SwingType.SWING_LOW),
            _structure_point(StructureLabel.HL, 90.5, 10, SwingType.SWING_LOW),
            _structure_point(StructureLabel.HL, 90.2, 15, SwingType.SWING_LOW),
        ]
        support, resistance = detect_zones(points, tolerance_pct=1.0, min_swings=2)
        assert len(support) >= 1
        assert support[0].zone_type == ZoneType.SUPPORT
        assert support[0].strength >= 2
        assert support[0].lower_bound <= 90.0
        assert support[0].upper_bound >= 90.5

    def test_resistance_zone(self) -> None:
        """Swing highs at similar prices should form a resistance zone."""
        points = [
            _structure_point(StructureLabel.HH, 110.0, 5, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.LH, 109.8, 10, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.HH, 110.2, 15, SwingType.SWING_HIGH),
        ]
        support, resistance = detect_zones(points, tolerance_pct=1.0, min_swings=2)
        assert len(resistance) >= 1
        assert resistance[0].zone_type == ZoneType.RESISTANCE

    def test_zone_boundaries(self) -> None:
        """Zone boundaries should span from min to max swing price in the group."""
        points = [
            _structure_point(StructureLabel.HL, 88.0, 5, SwingType.SWING_LOW),
            _structure_point(StructureLabel.HL, 92.0, 10, SwingType.SWING_LOW),
        ]
        support, _ = detect_zones(points, tolerance_pct=5.0, min_swings=2)
        assert len(support) >= 1
        assert support[0].lower_bound == 88.0
        assert support[0].upper_bound == 92.0

    def test_multiple_evidence_swings(self) -> None:
        """Zone strength should equal the number of swings in the group."""
        points = [
            _structure_point(StructureLabel.HH, 100.0, 2, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.HH, 100.5, 5, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.LH, 100.2, 8, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.HH, 100.3, 11, SwingType.SWING_HIGH),
        ]
        _, resistance = detect_zones(points, tolerance_pct=1.0, min_swings=2)
        assert len(resistance) >= 1
        assert resistance[0].strength >= 3

    def test_insufficient_data(self) -> None:
        """Empty structure points should return no zones."""
        support, resistance = detect_zones([])
        assert len(support) == 0
        assert len(resistance) == 0

    def test_below_min_swings_filtered(self) -> None:
        """Zones with fewer than min_swings should be filtered out."""
        points = [
            _structure_point(StructureLabel.HL, 90.0, 5, SwingType.SWING_LOW),
        ]
        support, _ = detect_zones(points, tolerance_pct=1.0, min_swings=2)
        assert len(support) == 0


# ---------------------------------------------------------------------------
# Session Classification Tests
# ---------------------------------------------------------------------------

class TestSessionClassification:
    def test_asian_session(self) -> None:
        """Hour 3 UTC should be Asian session."""
        ts = datetime(2024, 1, 1, 3, 0, 0, tzinfo=timezone.utc)
        assert classify_session(ts) == MarketSession.ASIAN

    def test_london_session(self) -> None:
        """Hour 10 UTC should be London session."""
        ts = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert classify_session(ts) == MarketSession.LONDON

    def test_new_york_session(self) -> None:
        """Hour 14 UTC should be Overlap (London 7-16, NY 12-21)."""
        ts = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        assert classify_session(ts) == MarketSession.OVERLAP

    def test_overlap_session(self) -> None:
        """Hour 15 UTC (London open, NY open) should be overlap."""
        ts = datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
        assert classify_session(ts) == MarketSession.OVERLAP

    def test_off_session(self) -> None:
        """Hour 22 UTC should be off session."""
        ts = datetime(2024, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
        assert classify_session(ts) == MarketSession.OFF_SESSION

    def test_boundary_london_start(self) -> None:
        """Hour 7 UTC should be London start."""
        ts = datetime(2024, 1, 1, 7, 0, 0, tzinfo=timezone.utc)
        session = classify_session(ts)
        assert session in (MarketSession.LONDON, MarketSession.OVERLAP)

    def test_boundary_ny_end(self) -> None:
        """Hour 21 UTC should be off session (NY ends at 21)."""
        ts = datetime(2024, 1, 1, 21, 0, 0, tzinfo=timezone.utc)
        session = classify_session(ts)
        assert session in (MarketSession.OFF_SESSION, MarketSession.ASIAN)

    def test_midnight(self) -> None:
        """Midnight UTC should be Asian."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert classify_session(ts) == MarketSession.ASIAN


# ---------------------------------------------------------------------------
# Market Regime Tests
# ---------------------------------------------------------------------------

class TestMarketRegime:
    def test_trending_up(self) -> None:
        """Bullish trend with bullish BOS should classify as TRENDING_UP."""
        from app.modules.market_analysis.models import BOSEvent, BOSDirection
        bos = [
            BOSEvent(
                direction=BOSDirection.BULLISH_BOS,
                broken_level=105.0,
                break_price=110.0,
                break_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                confirmation_basis="close_above",
                timeframe="1h",
                evidence="test",
            )
        ]
        points = [
            _structure_point(StructureLabel.HH, 110, 5, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.HL, 95, 10, SwingType.SWING_LOW),
            _structure_point(StructureLabel.HH, 115, 15, SwingType.SWING_HIGH),
        ]
        result = classify_regime(TrendState.BULLISH, points, bos, [])
        assert result.state == MarketRegime.TRENDING_UP
        assert len(result.evidence) > 0

    def test_trending_down(self) -> None:
        """Bearish trend with bearish BOS should classify as TRENDING_DOWN."""
        from app.modules.market_analysis.models import BOSEvent, BOSDirection
        bos = [
            BOSEvent(
                direction=BOSDirection.BEARISH_BOS,
                broken_level=95.0,
                break_price=90.0,
                break_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                confirmation_basis="close_below",
                timeframe="1h",
                evidence="test",
            )
        ]
        points = [
            _structure_point(StructureLabel.LL, 90, 5, SwingType.SWING_LOW),
            _structure_point(StructureLabel.LH, 105, 10, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.LL, 85, 15, SwingType.SWING_LOW),
        ]
        result = classify_regime(TrendState.BEARISH, points, bos, [])
        assert result.state == MarketRegime.TRENDING_DOWN

    def test_ranging(self) -> None:
        """Ranging trend should classify as RANGING."""
        points = [
            _structure_point(StructureLabel.HH, 110, 5, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.LL, 90, 10, SwingType.SWING_LOW),
            _structure_point(StructureLabel.HH, 108, 15, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.LL, 92, 20, SwingType.SWING_LOW),
        ]
        result = classify_regime(TrendState.RANGING, points, [], [])
        assert result.state == MarketRegime.RANGING

    def test_volatile(self) -> None:
        """Multiple CHOCH events should classify as VOLATILE."""
        from app.modules.market_analysis.models import CHOCHEvent, CHOCHDirection
        choch_events = [
            CHOCHEvent(
                direction=CHOCHDirection.BULLISH_CHOCH,
                broken_level=105.0,
                break_price=110.0,
                break_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                confirmation_basis="close_above",
                prior_structure="LH -> LL",
                timeframe="1h",
                evidence="test1",
            ),
            CHOCHEvent(
                direction=CHOCHDirection.BEARISH_CHOCH,
                broken_level=95.0,
                break_price=90.0,
                break_timestamp=datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
                confirmation_basis="close_below",
                prior_structure="HH -> HL",
                timeframe="1h",
                evidence="test2",
            ),
        ]
        result = classify_regime(TrendState.RANGING, [], [], choch_events)
        assert result.state == MarketRegime.VOLATILE

    def test_unclear(self) -> None:
        """Unclear trend with no events should classify as UNCLEAR."""
        result = classify_regime(TrendState.UNCLEAR, [], [], [])
        assert result.state == MarketRegime.UNCLEAR

    def test_evidence_populated(self) -> None:
        """Regime result should include supporting evidence."""
        points = [
            _structure_point(StructureLabel.HH, 110, 5, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.HL, 95, 10, SwingType.SWING_LOW),
            _structure_point(StructureLabel.HH, 115, 15, SwingType.SWING_HIGH),
            _structure_point(StructureLabel.HL, 98, 20, SwingType.SWING_LOW),
            _structure_point(StructureLabel.HH, 120, 25, SwingType.SWING_HIGH),
        ]
        result = classify_regime(TrendState.BULLISH, points, [], [])
        assert len(result.evidence) > 0


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------

class TestAnalysisValidation:
    def _make_response(self, count: int = 30, closed: bool = True) -> CandlesResponse:
        candles = [
            _candle(i, high=100 + i, low=90 + i, close=95 + i)
            for i in range(count)
        ]
        if not closed:
            candles[-1] = _candle(count - 1, high=100, low=90, close=95)
            candles[-1] = NormalizedCandle(
                instrument=Instrument.XAU_USD,
                provider_instrument="XAU/USD",
                source_type=SourceType.SPOT,
                timeframe=Timeframe.H1,
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=count - 1),
                open=95.0, high=100.0, low=90.0, close=95.0,
                volume=1000.0, is_closed=False, source="test",
            )
        return CandlesResponse(
            instrument=Instrument.XAU_USD,
            timeframe=Timeframe.H1,
            candles=candles,
            source="test",
            source_type=SourceType.SPOT,
            count=len(candles),
        )

    def test_valid_context(self) -> None:
        """Sufficient ordered candles should validate."""
        resp = self._make_response(30)
        is_valid, reason = validate_analysis_context(resp)
        assert is_valid is True
        assert "successfully" in reason.lower()

    def test_insufficient_candles(self) -> None:
        """Too few candles should fail validation."""
        resp = self._make_response(5)
        is_valid, reason = validate_analysis_context(resp)
        assert is_valid is False
        assert "Insufficient" in reason

    def test_duplicate_timestamps(self) -> None:
        """Duplicate timestamps should fail validation."""
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        candles = [
            NormalizedCandle(
                instrument=Instrument.XAU_USD,
                provider_instrument="XAU/USD",
                source_type=SourceType.SPOT,
                timeframe=Timeframe.H1,
                timestamp=ts,  # All same timestamp
                open=100.0 + i, high=105.0 + i, low=95.0 + i, close=102.0 + i,
                volume=1000.0, is_closed=True, source="test",
            )
            for i in range(25)  # Enough to pass min candle check
        ]
        resp = CandlesResponse(
            instrument=Instrument.XAU_USD,
            timeframe=Timeframe.H1,
            candles=candles,
            source="test",
            source_type=SourceType.SPOT,
            count=len(candles),
        )
        is_valid, reason = validate_analysis_context(resp)
        assert is_valid is False
        assert "Duplicate" in reason or "identical" in reason

    def test_source_metadata_preserved(self) -> None:
        """build_analysis_context should preserve source metadata."""
        resp = self._make_response(30)
        ctx = build_analysis_context(resp)
        assert ctx.canonical_instrument == "XAU/USD"
        assert ctx.provider_instrument == "XAU/USD"
        assert ctx.source_type == "spot"
        assert ctx.timeframe == "1h"
        assert ctx.candle_count == 30

    def test_futures_proxy_metadata(self) -> None:
        """FUTURES_PROXY source type should be preserved."""
        candles = [
            NormalizedCandle(
                instrument=Instrument.XAU_USD,
                provider_instrument="GC=F",
                source_type=SourceType.FUTURES_PROXY,
                timeframe=Timeframe.H1,
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                open=100.0 + i, high=105.0 + i, low=95.0 + i, close=102.0 + i,
                volume=1000.0, is_closed=True, source="yfinance",
            )
            for i in range(30)
        ]
        resp = CandlesResponse(
            instrument=Instrument.XAU_USD,
            timeframe=Timeframe.H1,
            candles=candles,
            source="yfinance",
            source_type=SourceType.FUTURES_PROXY,
            count=30,
        )
        ctx = build_analysis_context(resp)
        assert ctx.source_type == "futures_proxy"
        assert ctx.provider_instrument == "GC=F"
        assert ctx.provider == "yfinance"
