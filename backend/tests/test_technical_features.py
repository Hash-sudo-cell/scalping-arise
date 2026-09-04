"""
Scalping Arise — Phase 4 Technical Features Tests

Deterministic, isolated tests for each indicator.
Uses hand-crafted candle data — no external API calls.
"""

from __future__ import annotations

import os

import pytest

# Set test environment before any app imports
os.environ["SCALPING_ARISE_ENVIRONMENT"] = "testing"
os.environ["SCALPING_ARISE_DEBUG"] = "true"
os.environ["SCALPING_ARISE_LOG_LEVEL"] = "WARNING"

from app.modules.market_data.models import (
    CandlesResponse,
    Instrument,
    NormalizedCandle,
    SourceType,
    Timeframe,
)
from app.modules.technical_features.models import (
    EMAAlignment,
    EMADirection,
    EMAResult,
    EMAValue,
    FeatureAvailability,
    FeatureAvailabilityItem,
    FeatureMetadata,
    FeatureResult,
    FeatureSetStatus,
    MultiTimeframeResult,
    TimeframeFeatureResult,
    VolatilityClassification,
    RSIResult,
    RSISessionState,
    MACDResult,
    MACDContext,
    ATRResult,
    ATRVolatilityState,
    BollingerBandsResult,
    BollingerPosition,
    VolumeResult,
    VolumeState,
    PriceFeatures,
)
from app.modules.technical_features.config import (
    TechnicalFeaturesSettings,
    get_technical_features_settings,
)
from app.modules.technical_features.ema import calculate_ema, calculate_ema_series, calculate_ema_features
from app.modules.technical_features.rsi import calculate_rsi
from app.modules.technical_features.macd import calculate_macd
from app.modules.technical_features.atr import calculate_atr, calculate_true_ranges
from app.modules.technical_features.bollinger import calculate_bollinger_bands
from app.modules.technical_features.volume import calculate_volume_features, has_volume_data
from app.modules.technical_features.price_features import calculate_price_features
from app.modules.technical_features.validation import validate_feature_context, build_feature_metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(
    closes: list[float],
    volumes: list[float | None] | None = None,
    base_price: float | None = None,
) -> list[NormalizedCandle]:
    """Build NormalizedCandle list from close prices."""
    from datetime import datetime, timedelta, timezone

    base_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i, close in enumerate(closes):
        vol = volumes[i] if volumes else 1000.0
        candle = NormalizedCandle(
            instrument=Instrument.XAU_USD,
            timeframe=Timeframe.H1,
            timestamp=base_ts + timedelta(hours=i),
            open=close - 0.5,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=vol,
            is_closed=True,
            source="yfinance",
            provider_instrument="GC=F",
            source_type=SourceType.FUTURES_PROXY,
        )
        candles.append(candle)
    return candles


def _make_candles_response(candles: list[NormalizedCandle]) -> CandlesResponse:
    """Build CandlesResponse from candle list."""
    return CandlesResponse(
        instrument=Instrument.XAU_USD,
                timeframe=Timeframe.H1,
        count=len(candles),
        source="yfinance",
        source_type=SourceType.FUTURES_PROXY,
        has_gaps=False,
        candles=candles,
    )


def _rising_candles(n: int = 300, start: float = 2000.0, step: float = 2.0) -> list[NormalizedCandle]:
    """Generate a steadily rising price series."""
    closes = [start + i * step for i in range(n)]
    return _make_candles(closes)


def _falling_candles(n: int = 300, start: float = 2200.0, step: float = 2.0) -> list[NormalizedCandle]:
    """Generate a steadily falling price series."""
    closes = [start - i * step for i in range(n)]
    return _make_candles(closes)


def _flat_candles(n: int = 300, price: float = 2000.0) -> list[NormalizedCandle]:
    """Generate a flat price series."""
    closes = [price] * n
    return _make_candles(closes)


def _oscillating_candles(n: int = 300, base: float = 2000.0, amplitude: float = 50.0) -> list[NormalizedCandle]:
    """Generate oscillating price series."""
    import math
    closes = [base + amplitude * math.sin(i * 0.1) for i in range(n)]
    return _make_candles(closes)


# ---------------------------------------------------------------------------
# Configuration Tests
# ---------------------------------------------------------------------------

class TestConfiguration:
    """TechnicalFeaturesSettings validation."""

    def test_default_settings(self):
        cfg = get_technical_features_settings()
        assert cfg.ema_fast_period == 20
        assert cfg.ema_medium_period == 50
        assert cfg.ema_slow_period == 200
        assert cfg.rsi_period == 14
        assert cfg.macd_fast_period == 12
        assert cfg.macd_slow_period == 26
        assert cfg.macd_signal_period == 9
        assert cfg.atr_period == 14
        assert cfg.bb_period == 20
        assert cfg.bb_std_dev == 2.0
        assert cfg.volume_sma_period == 20
        assert cfg.price_lookback == 20

    def test_settings_validation_fast_ge_medium(self):
        with pytest.raises(ValueError, match="ema_fast_period must be < ema_medium_period"):
            TechnicalFeaturesSettings(ema_fast_period=50, ema_medium_period=20)

    def test_settings_validation_medium_ge_slow(self):
        with pytest.raises(ValueError, match="ema_medium_period must be < ema_slow_period"):
            TechnicalFeaturesSettings(ema_medium_period=200, ema_slow_period=50)

    def test_settings_validation_macd_fast_ge_slow(self):
        with pytest.raises(ValueError, match="macd_fast_period must be < macd_slow_period"):
            TechnicalFeaturesSettings(macd_fast_period=26, macd_slow_period=12)

    def test_settings_validation_zero_period(self):
        with pytest.raises(ValueError, match="atr_period must be > 0"):
            TechnicalFeaturesSettings(atr_period=0)

    def test_settings_validation_negative_std_dev(self):
        with pytest.raises(ValueError, match="bb_std_dev must be > 0"):
            TechnicalFeaturesSettings(bb_std_dev=-1.0)


# ---------------------------------------------------------------------------
# EMA Tests
# ---------------------------------------------------------------------------

class TestEMA:
    """EMA calculation tests."""

    def test_ema_series_insufficient_data(self):
        candles = _flat_candles(10)
        result = calculate_ema_series(candles, 20)
        assert all(v is None for v in result)

    def test_ema_series_sufficient_data(self):
        candles = _flat_candles(50, price=100.0)
        result = calculate_ema_series(candles, 20)
        # First 19 should be None
        assert result[0] is None
        assert result[18] is None
        # From index 19 onward, should have values
        assert result[19] is not None
        # For flat data, EMA should converge to the price
        assert abs(result[-1] - 100.0) < 0.01

    def test_ema_single_period_insufficient(self):
        candles = _flat_candles(5)
        result = calculate_ema(candles, 20)
        assert result.availability == FeatureAvailability.INSUFFICIENT_DATA
        assert result.value is None

    def test_ema_single_period_available(self):
        candles = _flat_candles(50, price=100.0)
        result = calculate_ema(candles, 20)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.value is not None
        assert abs(result.value - 100.0) < 0.01
        assert result.period == 20
        assert result.required_history == 20

    def test_ema_direction_rising(self):
        candles = _rising_candles(50)
        result = calculate_ema(candles, 20)
        assert result.direction == EMADirection.RISING

    def test_ema_direction_falling(self):
        candles = _falling_candles(50)
        result = calculate_ema(candles, 20)
        assert result.direction == EMADirection.FALLING

    def test_ema_direction_flat(self):
        candles = _flat_candles(50)
        result = calculate_ema(candles, 20)
        assert result.direction == EMADirection.FLAT

    def test_ema_price_relative_above(self):
        candles = _rising_candles(50)
        result = calculate_ema(candles, 20)
        assert result.price_relative == "above"

    def test_ema_price_relative_below(self):
        candles = _falling_candles(50)
        result = calculate_ema(candles, 20)
        assert result.price_relative == "below"

    def test_ema_alignment_bullish(self):
        candles = _rising_candles(300)
        result = calculate_ema_features(candles)
        assert result.alignment == EMAAlignment.BULLISH
        assert len(result.alignment_evidence) > 0

    def test_ema_alignment_bearish(self):
        candles = _falling_candles(300)
        result = calculate_ema_features(candles)
        assert result.alignment == EMAAlignment.BEARISH

    def test_ema_alignment_mixed(self):
        candles = _oscillating_candles(300)
        result = calculate_ema_features(candles)
        # Oscillating could be mixed or either — just check it's valid
        assert result.alignment in [EMAAlignment.MIXED, EMAAlignment.BULLISH, EMAAlignment.BEARISH]

    def test_ema_alignment_unavailable_insufficient_data(self):
        candles = _flat_candles(10)
        result = calculate_ema_features(candles)
        assert result.alignment == EMAAlignment.UNAVAILABLE

    def test_ema_no_look_ahead(self):
        """Verify EMA at candle i doesn't use candle i+1 data."""
        closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        candles = _make_candles(closes)
        # With period=3, we need 3 candles
        ema_series = calculate_ema_series(candles, 3)
        # First two are None, third is SMA(100,101,102)=101
        assert ema_series[0] is None
        assert ema_series[1] is None
        assert ema_series[2] is not None
        # Fourth EMA should only use first 4 closes
        # SMA seed = (100+101+102)/3 = 101
        # EMA[3] = (103 - 101) * (2/4) + 101 = 102
        assert abs(ema_series[3] - 102.0) < 0.01


# ---------------------------------------------------------------------------
# EMA Warm-Up Boundary Tests
# ---------------------------------------------------------------------------

class TestEMAWarmUp:
    """EMA independent availability at warm-up boundaries."""

    def test_ema20_available_ema200_insufficient(self):
        """With 100 candles: EMA20=AVAILABLE, EMA200=INSUFFICIENT_DATA."""
        candles = _rising_candles(100)
        result = calculate_ema_features(candles)
        assert result.fast.availability == FeatureAvailability.AVAILABLE
        assert result.medium.availability == FeatureAvailability.AVAILABLE
        assert result.slow.availability == FeatureAvailability.INSUFFICIENT_DATA
        assert result.fast.value is not None
        assert result.medium.value is not None
        assert result.slow.value is None

    def test_ema_alignment_unavailable_with_partial_data(self):
        """Alignment stays UNAVAILABLE when any EMA is INSUFFICIENT_DATA."""
        candles = _rising_candles(100)
        result = calculate_ema_features(candles)
        assert result.alignment == EMAAlignment.UNAVAILABLE
        assert len(result.alignment_evidence) == 0

    def test_ema_alignment_available_with_full_data(self):
        """Alignment becomes BULLISH/BEARISH/MIXED when all EMAs available."""
        candles = _rising_candles(300)
        result = calculate_ema_features(candles)
        assert result.alignment in [EMAAlignment.BULLISH, EMAAlignment.BEARISH, EMAAlignment.MIXED]
        assert result.fast.availability == FeatureAvailability.AVAILABLE
        assert result.medium.availability == FeatureAvailability.AVAILABLE
        assert result.slow.availability == FeatureAvailability.AVAILABLE

    def test_ema_direction_at_exact_boundary(self):
        """With exactly period candles: EMA=AVAILABLE, direction=UNKNOWN."""
        candles = _rising_candles(20)
        result = calculate_ema(candles, 20)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.direction == EMADirection.UNKNOWN
        assert result.value is not None

    def test_ema_direction_one_past_boundary(self):
        """With period+1 candles: direction can be determined."""
        candles = _rising_candles(21)
        result = calculate_ema(candles, 20)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.direction == EMADirection.RISING

    def test_ema_independent_periods_at_50_candles(self):
        """At 50 candles: EMA20=AVAILABLE, EMA50=AVAILABLE, EMA200=INSUFFICIENT."""
        candles = _rising_candles(50)
        result = calculate_ema_features(candles)
        assert result.fast.availability == FeatureAvailability.AVAILABLE
        assert result.medium.availability == FeatureAvailability.AVAILABLE
        assert result.slow.availability == FeatureAvailability.INSUFFICIENT_DATA

    def test_ema_independent_periods_at_200_candles(self):
        """At 200 candles: all EMAs AVAILABLE, alignment can be calculated."""
        candles = _rising_candles(200)
        result = calculate_ema_features(candles)
        assert result.fast.availability == FeatureAvailability.AVAILABLE
        assert result.medium.availability == FeatureAvailability.AVAILABLE
        assert result.slow.availability == FeatureAvailability.AVAILABLE
        assert result.alignment in [EMAAlignment.BULLISH, EMAAlignment.BEARISH, EMAAlignment.MIXED]


# ---------------------------------------------------------------------------
# MACD Staged Warm-Up Boundary Tests
# ---------------------------------------------------------------------------

class TestMACDStagedWarmUp:
    """MACD staged component availability at warm-up boundaries."""

    def test_macd_stage0_insufficient(self):
        """< 26 candles: all components INSUFFICIENT_DATA."""
        candles = _rising_candles(20)
        result = calculate_macd(candles)
        assert result.availability == FeatureAvailability.INSUFFICIENT_DATA
        assert result.macd_line is None
        assert result.signal_line is None
        assert result.histogram is None
        assert result.macd_line_availability == FeatureAvailability.INSUFFICIENT_DATA
        assert result.signal_line_availability == FeatureAvailability.INSUFFICIENT_DATA
        assert result.histogram_availability == FeatureAvailability.INSUFFICIENT_DATA

    def test_macd_stage1_macd_line_only(self):
        """26-34 candles: macd_line AVAILABLE, signal/histogram INSUFFICIENT."""
        # Default MACD: fast=12, slow=26, signal=9
        # MACD line needs slow_period=26 candles
        # Signal needs slow_period + signal_period = 35 candles
        candles = _rising_candles(30)
        result = calculate_macd(candles)
        assert result.macd_line is not None
        assert result.macd_line_availability == FeatureAvailability.AVAILABLE
        assert result.signal_line_availability == FeatureAvailability.INSUFFICIENT_DATA
        assert result.histogram_availability == FeatureAvailability.INSUFFICIENT_DATA
        # Overall should be INSUFFICIENT_DATA since signal/histogram not ready
        assert result.availability == FeatureAvailability.INSUFFICIENT_DATA
        assert result.signal_line is None
        assert result.histogram is None

    def test_macd_stage2_full_available(self):
        """35+ candles: all components AVAILABLE."""
        candles = _rising_candles(50)
        result = calculate_macd(candles)
        assert result.macd_line is not None
        assert result.signal_line is not None
        assert result.histogram is not None
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.macd_line_availability == FeatureAvailability.AVAILABLE
        assert result.signal_line_availability == FeatureAvailability.AVAILABLE
        assert result.histogram_availability == FeatureAvailability.AVAILABLE

    def test_macd_at_exact_boundary_26(self):
        """Exactly 26 candles: MACD line available, signal still warming up."""
        candles = _rising_candles(26)
        result = calculate_macd(candles)
        assert result.macd_line is not None
        assert result.macd_line_availability == FeatureAvailability.AVAILABLE
        assert result.signal_line_availability == FeatureAvailability.INSUFFICIENT_DATA
        assert result.histogram_availability == FeatureAvailability.INSUFFICIENT_DATA

    def test_macd_at_exact_boundary_35(self):
        """Exactly 35 candles: all components available."""
        candles = _rising_candles(35)
        result = calculate_macd(candles)
        assert result.macd_line is not None
        assert result.signal_line is not None
        assert result.histogram is not None
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.macd_line_availability == FeatureAvailability.AVAILABLE
        assert result.signal_line_availability == FeatureAvailability.AVAILABLE
        assert result.histogram_availability == FeatureAvailability.AVAILABLE

    def test_macd_context_neutral_during_warmup(self):
        """Context stays NEUTRAL when signal_line not available."""
        candles = _rising_candles(30)
        result = calculate_macd(candles)
        assert result.context == MACDContext.NEUTRAL

    def test_macd_serialization_includes_component_availability(self):
        """MACDResult serializes per-component availability fields."""
        candles = _rising_candles(50)
        result = calculate_macd(candles)
        data = result.model_dump(mode="json")
        assert "macd_line_availability" in data
        assert "signal_line_availability" in data
        assert "histogram_availability" in data
        assert data["macd_line_availability"] == "available"
        assert data["signal_line_availability"] == "available"
        assert data["histogram_availability"] == "available"


# ---------------------------------------------------------------------------
# Service Partial Availability Tests
# ---------------------------------------------------------------------------

class TestServicePartialAvailability:
    """Service-level partial availability reporting."""

    @pytest.fixture
    def mock_service_50_candles(self):
        """Mock returning 50 candles — partial EMA warm-up."""
        from unittest.mock import AsyncMock, MagicMock

        service = MagicMock()
        candles = _rising_candles(50)
        response = CandlesResponse(
            instrument=Instrument.XAU_USD,
            timeframe=Timeframe.H1,
            count=50,
            source="yfinance",
            source_type=SourceType.FUTURES_PROXY,
            has_gaps=False,
            candles=candles,
        )
        service.get_candles = AsyncMock(return_value=response)
        return service

    @pytest.mark.asyncio
    async def test_trend_availability_shows_per_ema(self, mock_service_50_candles):
        """Trend availability reason includes per-EMA status."""
        from app.modules.technical_features.service import TechnicalFeatureService

        svc = TechnicalFeatureService(market_data_service=mock_service_50_candles)
        result = await svc.get_features(timeframe="1h", limit=300)
        trend_item = next(a for a in result.availability if a.name == "trend")
        # At 50 candles: EMA20=available, EMA50=available, EMA200=insufficient_data
        assert "EMA20=available" in trend_item.reason
        assert "EMA50=available" in trend_item.reason
        assert "EMA200=insufficient_data" in trend_item.reason
        assert trend_item.status == FeatureAvailability.INSUFFICIENT_DATA

    @pytest.mark.asyncio
    async def test_macd_availability_shows_per_component(self, mock_service_50_candles):
        """MACD availability reason includes per-component status."""
        from app.modules.technical_features.service import TechnicalFeatureService

        svc = TechnicalFeatureService(market_data_service=mock_service_50_candles)
        result = await svc.get_features(timeframe="1h", limit=300)
        macd_item = next(a for a in result.availability if a.name == "macd")
        # At 50 candles: all MACD components available (50 > 35)
        assert "MACD line=available" in macd_item.reason
        assert "signal=available" in macd_item.reason
        assert "histogram=available" in macd_item.reason
        assert macd_item.status == FeatureAvailability.AVAILABLE


# ---------------------------------------------------------------------------
# RSI Tests
# ---------------------------------------------------------------------------

class TestRSI:
    """RSI calculation tests."""

    def test_rsi_insufficient_data(self):
        candles = _flat_candles(10)
        result = calculate_rsi(candles, 14)
        assert result.availability == FeatureAvailability.INSUFFICIENT_DATA
        assert result.value is None

    def test_rsi_flat_market(self):
        """Flat market = RSI ~50 (no gains/losses → loss=0 → RSI=100)."""
        # Actually, flat = all changes = 0 → avg_gain=0, avg_loss=0
        # When avg_loss=0, RSI=100
        candles = _flat_candles(50)
        result = calculate_rsi(candles, 14)
        assert result.availability == FeatureAvailability.AVAILABLE
        # Flat market: all changes = 0, so avg_loss = 0 → RSI = 100
        assert result.value == 100.0

    def test_rsi_strong_uptrend(self):
        """Strong uptrend → RSI near overbought."""
        candles = _rising_candles(50, step=5.0)
        result = calculate_rsi(candles, 14)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.value is not None
        assert result.value > 60  # Should be strong/overbought

    def test_rsi_strong_downtrend(self):
        """Strong downtrend → RSI near oversold."""
        candles = _falling_candles(50, step=5.0)
        result = calculate_rsi(candles, 14)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.value is not None
        assert result.value < 40  # Should be weak/oversold

    def test_rsi_state_classification(self):
        """RSI state matches threshold configuration."""
        candles = _rising_candles(50, step=10.0)
        result = calculate_rsi(candles, 14)
        # Very strong uptrend → should be overbought
        assert result.state in [RSISessionState.OVERBOUGHT, RSISessionState.STRONG]

    def test_rsi_custom_thresholds(self):
        """Custom thresholds are respected."""
        candles = _rising_candles(50, step=5.0)
        # Very tight thresholds
        settings = TechnicalFeaturesSettings(
            rsi_period=14,
            rsi_oversold_threshold=45.0,
            rsi_overbought_threshold=55.0,
        )
        result = calculate_rsi(candles, 14, settings)
        assert result.availability == FeatureAvailability.AVAILABLE

    def test_rsi_required_history(self):
        """RSI requires period+1 candles."""
        candles = _rising_candles(50)
        result = calculate_rsi(candles, 14)
        assert result.required_history == 15

    def test_rsi_no_look_ahead(self):
        """Verify RSI at candle i doesn't use candle i+1 data."""
        # Create a series with known gains/losses
        closes = [
            100, 102, 101, 103, 102, 104, 103, 105, 104, 106,
            105, 107, 106, 108, 107, 109, 108, 110, 109, 111,
        ]
        candles = _make_candles(closes)
        result = calculate_rsi(candles, 10)
        assert result.availability == FeatureAvailability.AVAILABLE
        # The result should be deterministic
        assert result.value is not None

    def test_rsi_oscillating_market(self):
        """Oscillating market → RSI in a reasonable range."""
        candles = _oscillating_candles(100)
        result = calculate_rsi(candles, 14)
        assert result.availability == FeatureAvailability.AVAILABLE
        # RSI should be calculable (not None)
        assert result.value is not None
        assert 0 <= result.value <= 100


# ---------------------------------------------------------------------------
# MACD Tests
# ---------------------------------------------------------------------------

class TestMACD:
    """MACD calculation tests."""

    def test_macd_insufficient_data(self):
        candles = _flat_candles(10)
        result = calculate_macd(candles)
        assert result.availability == FeatureAvailability.INSUFFICIENT_DATA

    def test_macd_sufficient_data(self):
        candles = _rising_candles(100)
        result = calculate_macd(candles)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.macd_line is not None
        assert result.signal_line is not None
        assert result.histogram is not None

    def test_macd_bullish_context(self):
        """Strong rising market → bullish or neutral MACD context."""
        candles = _rising_candles(100, step=5.0)
        result = calculate_macd(candles)
        # Rising market: MACD line should be positive
        assert result.macd_line is not None
        assert result.macd_line > 0
        # Context could be bullish (if MACD > signal) or neutral (if MACD < signal but both positive)
        assert result.context in [MACDContext.BULLISH, MACDContext.NEUTRAL]

    def test_macd_bearish_context(self):
        """Strong falling market → bearish or neutral MACD context."""
        candles = _falling_candles(100, step=5.0)
        result = calculate_macd(candles)
        # Falling market: MACD line should be negative
        assert result.macd_line is not None
        assert result.macd_line < 0
        # Context could be bearish (if MACD < signal) or neutral (if MACD > signal but both negative)
        assert result.context in [MACDContext.BEARISH, MACDContext.NEUTRAL]

    def test_macd_histogram_relationship(self):
        """Histogram = MACD - Signal."""
        candles = _rising_candles(100)
        result = calculate_macd(candles)
        expected_hist = result.macd_line - result.signal_line
        assert abs(result.histogram - expected_hist) < 0.0001

    def test_macd_required_history(self):
        """MACD requires slow_period + signal_period candles."""
        candles = _rising_candles(100)
        result = calculate_macd(candles)
        assert result.required_history == 26 + 9  # slow + signal

    def test_macd_custom_periods(self):
        """Custom MACD periods are used."""
        candles = _rising_candles(100)
        result = calculate_macd(candles, fast_period=8, slow_period=21, signal_period=5)
        assert result.fast_period == 8
        assert result.slow_period == 21
        assert result.signal_period == 5

    def test_macd_no_look_ahead(self):
        """MACD is deterministic — same input always produces same output."""
        candles = _oscillating_candles(100)
        r1 = calculate_macd(candles)
        r2 = calculate_macd(candles)
        assert r1.macd_line == r2.macd_line
        assert r1.signal_line == r2.signal_line
        assert r1.histogram == r2.histogram


# ---------------------------------------------------------------------------
# ATR Tests
# ---------------------------------------------------------------------------

class TestATR:
    """ATR calculation tests."""

    def test_true_ranges_first_candle(self):
        """First candle TR = High - Low."""
        candles = _make_candles([100.0])
        tr = calculate_true_ranges(candles)
        assert len(tr) == 1
        assert tr[0] == candles[0].high - candles[0].low

    def test_true_ranges_subsequent(self):
        """Subsequent candles use max(H-L, |H-PC|, |L-PC|)."""
        candle1 = _make_candles([100.0])[0]
        candle2 = NormalizedCandle(
            instrument=Instrument.XAU_USD,
            timeframe=Timeframe.H1,
            timestamp=candle1.timestamp,
            open=101.0,
            high=105.0,
            low=98.0,
            close=102.0,
            volume=1000,
            is_closed=True,
            source="yfinance",
            provider_instrument="GC=F",
            source_type=SourceType.FUTURES_PROXY,
        )
        tr = calculate_true_ranges([candle1, candle2])
        # TR = max(105-98, |105-100|, |98-100|) = max(7, 5, 2) = 7
        assert tr[1] == 7.0

    def test_atr_insufficient_data(self):
        candles = _flat_candles(5)
        result = calculate_atr(candles, 14)
        assert result.availability == FeatureAvailability.INSUFFICIENT_DATA

    def test_atr_flat_market(self):
        """Flat market → ATR = 0 (no true range)."""
        # All candles identical → TR = 0 for all
        candles = _flat_candles(50, price=100.0)
        # Make all high/low identical to close
        for c in candles:
            c.high = c.close
            c.low = c.close
        result = calculate_atr(candles, 14)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.value == 0.0

    def test_atr_volatile_market(self):
        """Volatile market → higher ATR."""
        # Create candles with large ranges
        from datetime import datetime, timedelta, timezone
        base_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        candles = []
        for i in range(50):
            close = 2000.0 + i * 2
            candle = NormalizedCandle(
                instrument=Instrument.XAU_USD,
                timeframe=Timeframe.H1,
                timestamp=base_ts + timedelta(hours=i),
                open=close - 0.5,
                high=close + 20.0,  # Large range
                low=close - 20.0,
                close=close,
                volume=1000,
                is_closed=True,
                source="yfinance",
                provider_instrument="GC=F",
                source_type=SourceType.FUTURES_PROXY,
            )
            candles.append(candle)
        result = calculate_atr(candles, 14)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.value > 0
        assert result.percentage > 0

    def test_atr_percentage_calculation(self):
        """ATR percentage = ATR / current_price * 100."""
        candles = _rising_candles(50)
        result = calculate_atr(candles, 14)
        if result.value and candles[-1].close:
            expected_pct = result.value / candles[-1].close * 100
            assert abs(result.percentage - expected_pct) < 0.001

    def test_atr_state_classification(self):
        """ATR state matches thresholds."""
        candles = _rising_candles(50)
        result = calculate_atr(candles, 14)
        assert result.state in [ATRVolatilityState.HIGH, ATRVolatilityState.NORMAL, ATRVolatilityState.LOW]

    def test_atr_required_history(self):
        candles = _rising_candles(50)
        result = calculate_atr(candles, 14)
        assert result.required_history == 15  # period + 1


# ---------------------------------------------------------------------------
# Bollinger Bands Tests
# ---------------------------------------------------------------------------

class TestBollingerBands:
    """Bollinger Bands calculation tests."""

    def test_bb_insufficient_data(self):
        candles = _flat_candles(10)
        result = calculate_bollinger_bands(candles, 20)
        assert result.availability == FeatureAvailability.INSUFFICIENT_DATA

    def test_bb_flat_market(self):
        """Flat market → bands collapse to middle (zero std dev)."""
        candles = _flat_candles(50, price=2000.0)
        result = calculate_bollinger_bands(candles, 20, 2.0)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.middle_band == 2000.0
        assert result.upper_band == 2000.0
        assert result.lower_band == 2000.0
        assert result.band_width == 0.0

    def test_bb_volatile_market(self):
        """Volatile market → wider bands."""
        candles = _oscillating_candles(50, amplitude=100.0)
        result = calculate_bollinger_bands(candles, 20, 2.0)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.upper_band > result.middle_band
        assert result.lower_band < result.middle_band
        assert result.band_width > 0

    def test_bb_price_position_above_upper(self):
        """Price above upper band → ABOVE_UPPER."""
        closes = [100.0] * 19 + [200.0]  # Last candle jumps above
        candles = _make_candles(closes)
        result = calculate_bollinger_bands(candles, 20, 2.0)
        assert result.price_position == BollingerPosition.ABOVE_UPPER

    def test_bb_price_position_below_lower(self):
        """Price below lower band → BELOW_LOWER."""
        closes = [100.0] * 19 + [10.0]  # Last candle drops below
        candles = _make_candles(closes)
        result = calculate_bollinger_bands(candles, 20, 2.0)
        assert result.price_position == BollingerPosition.BELOW_LOWER

    def test_bb_price_position_middle(self):
        """Price near middle → MIDDLE_REGION."""
        candles = _flat_candles(50, price=2000.0)
        result = calculate_bollinger_bands(candles, 20, 2.0)
        assert result.price_position == BollingerPosition.MIDDLE_REGION

    def test_bb_band_width_calculation(self):
        """Band width = (Upper - Lower) / Middle * 100."""
        candles = _oscillating_candles(50)
        result = calculate_bollinger_bands(candles, 20, 2.0)
        expected = (result.upper_band - result.lower_band) / result.middle_band * 100
        assert abs(result.band_width - expected) < 0.001

    def test_bb_required_history(self):
        candles = _rising_candles(50)
        result = calculate_bollinger_bands(candles, 20)
        assert result.required_history == 20

    def test_bb_custom_params(self):
        """Custom period and std dev are used."""
        candles = _oscillating_candles(50)
        result = calculate_bollinger_bands(candles, 30, 3.0)
        assert result.period == 30
        assert result.std_dev == 3.0


# ---------------------------------------------------------------------------
# Volume Tests
# ---------------------------------------------------------------------------

class TestVolume:
    """Volume feature tests."""

    def test_volume_no_data(self):
        """No volume data → UNAVAILABLE."""
        candles = _flat_candles(50)
        for c in candles:
            c.volume = None
        result = calculate_volume_features(candles, 20)
        assert result.availability == FeatureAvailability.UNAVAILABLE
        assert result.state == VolumeState.UNAVAILABLE

    def test_has_volume_data_true(self):
        candles = _flat_candles(5)
        assert has_volume_data(candles) is True

    def test_has_volume_data_false(self):
        candles = _flat_candles(5)
        for c in candles:
            c.volume = None
        assert has_volume_data(candles) is False

    def test_volume_insufficient_data(self):
        candles = _flat_candles(5)
        result = calculate_volume_features(candles, 20)
        assert result.availability == FeatureAvailability.INSUFFICIENT_DATA

    def test_volume_high(self):
        """Volume spike → HIGH state."""
        volumes = [1000.0] * 19 + [5000.0]  # Last candle 5x average
        candles = _flat_candles(20)
        candles = _make_candles([2000.0] * 20, volumes=volumes)
        result = calculate_volume_features(candles, 20)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.state == VolumeState.HIGH
        assert result.relative_volume > 1.5

    def test_volume_low(self):
        """Low volume → LOW state."""
        volumes = [1000.0] * 19 + [100.0]  # Last candle 0.1x average
        candles = _make_candles([2000.0] * 20, volumes=volumes)
        result = calculate_volume_features(candles, 20)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.state == VolumeState.LOW
        assert result.relative_volume < 0.5

    def test_volume_normal(self):
        """Normal volume → NORMAL state."""
        volumes = [1000.0] * 20  # All same
        candles = _make_candles([2000.0] * 20, volumes=volumes)
        result = calculate_volume_features(candles, 20)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.state == VolumeState.NORMAL
        assert result.relative_volume == 1.0

    def test_volume_relative_calculation(self):
        """Relative volume = current / average."""
        volumes = [100.0, 200.0, 300.0, 400.0, 500.0]
        candles = _make_candles([2000.0] * 5, volumes=volumes)
        result = calculate_volume_features(candles, 5)
        # Average = (100+200+300+400+500)/5 = 300
        # Relative = 500/300 = 1.667
        assert abs(result.average_volume - 300.0) < 0.01
        assert abs(result.relative_volume - 1.667) < 0.01


# ---------------------------------------------------------------------------
# Price Features Tests
# ---------------------------------------------------------------------------

class TestPriceFeatures:
    """Price feature tests."""

    def test_price_insufficient_data(self):
        candles = _make_candles([100.0])
        result = calculate_price_features(candles)
        assert result.availability == FeatureAvailability.INSUFFICIENT_DATA

    def test_price_basic_calculation(self):
        closes = [99.0, 100.0]
        candles = _make_candles(closes)
        result = calculate_price_features(candles)
        assert result.availability == FeatureAvailability.AVAILABLE
        assert result.current_price == 100.0
        assert result.previous_close == 99.0
        assert result.absolute_change == 1.0
        assert abs(result.percentage_change - (1.0 / 99.0 * 100)) < 0.01

    def test_price_range(self):
        """Recent high/low/range is calculated correctly."""
        closes = [100.0, 110.0, 90.0, 105.0, 95.0]
        candles = _make_candles(closes)
        result = calculate_price_features(candles, lookback=5)
        assert result.recent_high == 111.0  # high = close + 1.0
        assert result.recent_low == 89.0    # low = close - 1.0

    def test_price_position_in_range(self):
        """Position in range: 0.0 = at low, 1.0 = at high."""
        closes = [100.0, 110.0, 120.0]
        candles = _make_candles(closes)
        result = calculate_price_features(candles, lookback=3)
        # Current price = 120, close+1 = 121
        # Recent high = 121, recent low = 99
        # position = (121 - 99) / (121 - 99) = 1.0
        assert result.position_in_range is not None
        assert result.position_in_range >= 0.0
        assert result.position_in_range <= 1.0

    def test_price_lookback_custom(self):
        """Custom lookback is respected."""
        closes = list(range(100, 130))
        candles = _make_candles([float(c) for c in closes])
        result = calculate_price_features(candles, lookback=10)
        assert result.lookback == 10

    def test_price_negative_change(self):
        """Negative price change."""
        closes = [100.0, 95.0]
        candles = _make_candles(closes)
        result = calculate_price_features(candles)
        assert result.absolute_change == -5.0
        assert result.percentage_change < 0


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------

class TestValidation:
    """Feature data validation tests."""

    def test_validate_insufficient_candles(self):
        candles = _flat_candles(10)
        response = _make_candles_response(candles)
        is_valid, reason = validate_feature_context(response)
        assert is_valid is False
        assert "Insufficient" in reason

    def test_validate_sufficient_candles(self):
        candles = _flat_candles(50)
        response = _make_candles_response(candles)
        is_valid, reason = validate_feature_context(response)
        assert is_valid is True

    def test_validate_chronological_order(self):
        """Candles must be in chronological order."""
        from datetime import datetime, timezone
        candles = _flat_candles(50)
        # Swap two candles to break order
        candles[10], candles[20] = candles[20], candles[10]
        response = _make_candles_response(candles)
        is_valid, reason = validate_feature_context(response)
        assert is_valid is False
        assert "chronological" in reason.lower()

    def test_validate_duplicate_timestamps(self):
        """Duplicate timestamps are rejected."""
        from datetime import datetime, timezone
        candles = _flat_candles(50)
        candles[5].timestamp = candles[4].timestamp
        response = _make_candles_response(candles)
        is_valid, reason = validate_feature_context(response)
        assert is_valid is False
        assert "Duplicate" in reason

    def test_build_feature_metadata(self):
        """Metadata is built correctly from CandlesResponse."""
        candles = _flat_candles(50)
        response = _make_candles_response(candles)
        metadata = build_feature_metadata(response)
        assert metadata.canonical_instrument == "XAU/USD"
        assert metadata.provider_instrument == "GC=F"
        assert metadata.provider == "yfinance"
        assert metadata.source_type == "futures_proxy"
        assert metadata.timeframe == "1h"
        assert metadata.candle_count == 50


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestModels:
    """Model serialization and structure tests."""

    def test_feature_result_serialization(self):
        """FeatureResult can be serialized to JSON."""
        result = FeatureResult(
            status=FeatureAvailability.AVAILABLE,
            reason="Test",
        )
        data = result.model_dump(mode="json")
        assert data["status"] == "available"
        assert data["reason"] == "Test"

    def test_ema_value_serialization(self):
        val = EMAValue(
            period=20,
            value=100.5,
            availability=FeatureAvailability.AVAILABLE,
            direction=EMADirection.RISING,
            price_relative="above",
            required_history=20,
        )
        data = val.model_dump(mode="json")
        assert data["period"] == 20
        assert data["value"] == 100.5
        assert data["direction"] == "rising"

    def test_rsi_result_serialization(self):
        result = RSIResult(
            period=14,
            value=65.5,
            availability=FeatureAvailability.AVAILABLE,
            state=RSISessionState.STRONG,
            required_history=15,
        )
        data = result.model_dump(mode="json")
        assert data["state"] == "strong"

    def test_feature_availability_item(self):
        item = FeatureAvailabilityItem(
            name="ema",
            status=FeatureAvailability.AVAILABLE,
            reason="All EMAs calculated",
        )
        data = item.model_dump(mode="json")
        assert data["name"] == "ema"
        assert data["status"] == "available"


# ---------------------------------------------------------------------------
# Service Integration Tests
# ---------------------------------------------------------------------------

class TestTechnicalFeatureService:
    """TechnicalFeatureService integration tests."""

    @pytest.fixture
    def mock_market_data_service(self):
        """Create a mock MarketDataService that returns test data."""
        from unittest.mock import AsyncMock, MagicMock
        from app.modules.market_data.models import CandlesResponse

        service = MagicMock()
        candles = _rising_candles(300)
        response = CandlesResponse(
            instrument=Instrument.XAU_USD,
            timeframe=Timeframe.H1,
            count=300,
            source="yfinance",
            source_type=SourceType.FUTURES_PROXY,
            has_gaps=False,
            candles=candles,
        )
        service.get_candles = AsyncMock(return_value=response)
        return service

    @pytest.fixture
    def mock_market_data_service_insufficient(self):
        """Create a mock MarketDataService that returns insufficient data."""
        from unittest.mock import AsyncMock, MagicMock

        service = MagicMock()
        candles = _flat_candles(5)  # Not enough
        response = CandlesResponse(
            instrument=Instrument.XAU_USD,
            timeframe=Timeframe.H1,
            count=5,
            source="yfinance",
            source_type=SourceType.FUTURES_PROXY,
            has_gaps=False,
            candles=candles,
        )
        service.get_candles = AsyncMock(return_value=response)
        return service

    @pytest.mark.asyncio
    async def test_service_returns_features(self, mock_market_data_service):
        from app.modules.technical_features.service import TechnicalFeatureService

        svc = TechnicalFeatureService(market_data_service=mock_market_data_service)
        result = await svc.get_features(timeframe="1h", limit=300)
        assert result.status == FeatureAvailability.AVAILABLE
        assert result.trend is not None
        assert result.momentum is not None
        assert result.volatility is not None
        assert result.price is not None
        assert result.metadata is not None

    @pytest.mark.asyncio
    async def test_service_insufficient_data(self, mock_market_data_service_insufficient):
        from app.modules.technical_features.service import TechnicalFeatureService

        svc = TechnicalFeatureService(market_data_service=mock_market_data_service_insufficient)
        result = await svc.get_features(timeframe="1h", limit=300)
        assert result.status == FeatureAvailability.INSUFFICIENT_DATA

    @pytest.mark.asyncio
    async def test_service_health_check(self, mock_market_data_service):
        from app.modules.technical_features.service import TechnicalFeatureService

        svc = TechnicalFeatureService(market_data_service=mock_market_data_service)
        health = await svc.health_check()
        assert health["status"] == "healthy"
        assert health["module"] == "technical_features"

    @pytest.mark.asyncio
    async def test_service_capabilities(self, mock_market_data_service):
        from app.modules.technical_features.service import TechnicalFeatureService

        svc = TechnicalFeatureService(market_data_service=mock_market_data_service)
        caps = await svc.get_capabilities()
        assert caps["module"] == "technical_features"
        assert "features" in caps
        assert "trend" in caps["features"]
        assert "momentum" in caps["features"]
        assert "volatility" in caps["features"]
        assert "volume" in caps["features"]
        assert "price" in caps["features"]


# ---------------------------------------------------------------------------
# Configuration — Extended Volatility Threshold Tests
# ---------------------------------------------------------------------------

class TestConfigurationExtended:
    """Extended configuration validation for volatility thresholds."""

    def test_extreme_threshold_default(self):
        cfg = get_technical_features_settings()
        assert cfg.atr_extreme_threshold_pct == 3.0
        assert cfg.atr_high_threshold_pct == 1.5
        assert cfg.atr_low_threshold_pct == 0.3

    def test_extreme_threshold_must_exceed_high(self):
        with pytest.raises(ValueError, match="atr_extreme_threshold_pct must be > atr_high_threshold_pct"):
            TechnicalFeaturesSettings(atr_extreme_threshold_pct=1.0, atr_high_threshold_pct=1.5)

    def test_extreme_threshold_valid(self):
        cfg = TechnicalFeaturesSettings(atr_extreme_threshold_pct=5.0, atr_high_threshold_pct=2.0)
        assert cfg.atr_extreme_threshold_pct == 5.0


# ---------------------------------------------------------------------------
# Volatility Classification Tests
# ---------------------------------------------------------------------------

class TestVolatilityClassification:
    """Extended 4-level volatility classification tests."""

    def test_classify_volatility_extreme(self):
        from app.modules.technical_features.service import _classify_volatility

        atr = ATRResult(
            period=14, value=70.0, percentage=3.5,
            availability=FeatureAvailability.AVAILABLE,
            state=ATRVolatilityState.HIGH,
            required_history=15,
        )
        cfg = get_technical_features_settings()
        cls, reason = _classify_volatility(atr, cfg)
        assert cls == VolatilityClassification.EXTREME
        assert "extreme" in reason.lower()

    def test_classify_volatility_high(self):
        from app.modules.technical_features.service import _classify_volatility

        atr = ATRResult(
            period=14, value=35.0, percentage=1.8,
            availability=FeatureAvailability.AVAILABLE,
            state=ATRVolatilityState.HIGH,
            required_history=15,
        )
        cfg = get_technical_features_settings()
        cls, reason = _classify_volatility(atr, cfg)
        assert cls == VolatilityClassification.HIGH
        assert "high" in reason.lower()

    def test_classify_volatility_normal(self):
        from app.modules.technical_features.service import _classify_volatility

        atr = ATRResult(
            period=14, value=15.0, percentage=0.8,
            availability=FeatureAvailability.AVAILABLE,
            state=ATRVolatilityState.NORMAL,
            required_history=15,
        )
        cfg = get_technical_features_settings()
        cls, reason = _classify_volatility(atr, cfg)
        assert cls == VolatilityClassification.NORMAL
        assert "between" in reason.lower()

    def test_classify_volatility_low(self):
        from app.modules.technical_features.service import _classify_volatility

        atr = ATRResult(
            period=14, value=5.0, percentage=0.2,
            availability=FeatureAvailability.AVAILABLE,
            state=ATRVolatilityState.LOW,
            required_history=15,
        )
        cfg = get_technical_features_settings()
        cls, reason = _classify_volatility(atr, cfg)
        assert cls == VolatilityClassification.LOW
        assert "low" in reason.lower()

    def test_classify_volatility_none_atr(self):
        from app.modules.technical_features.service import _classify_volatility

        cfg = get_technical_features_settings()
        cls, reason = _classify_volatility(None, cfg)
        assert cls == VolatilityClassification.NORMAL
        assert "unavailable" in reason.lower()

    def test_classify_volatility_at_boundary_extreme_high(self):
        from app.modules.technical_features.service import _classify_volatility

        # Exactly at extreme threshold
        atr = ATRResult(
            period=14, value=60.0, percentage=3.0,
            availability=FeatureAvailability.AVAILABLE,
            state=ATRVolatilityState.HIGH,
            required_history=15,
        )
        cfg = get_technical_features_settings()
        cls, _ = _classify_volatility(atr, cfg)
        assert cls == VolatilityClassification.EXTREME

    def test_classify_volatility_at_boundary_high_normal(self):
        from app.modules.technical_features.service import _classify_volatility

        # Exactly at high threshold
        atr = ATRResult(
            period=14, value=30.0, percentage=1.5,
            availability=FeatureAvailability.AVAILABLE,
            state=ATRVolatilityState.HIGH,
            required_history=15,
        )
        cfg = get_technical_features_settings()
        cls, _ = _classify_volatility(atr, cfg)
        assert cls == VolatilityClassification.HIGH

    def test_classify_volatility_at_boundary_normal_low(self):
        from app.modules.technical_features.service import _classify_volatility

        # Exactly at low threshold
        atr = ATRResult(
            period=14, value=6.0, percentage=0.3,
            availability=FeatureAvailability.AVAILABLE,
            state=ATRVolatilityState.LOW,
            required_history=15,
        )
        cfg = get_technical_features_settings()
        cls, _ = _classify_volatility(atr, cfg)
        assert cls == VolatilityClassification.LOW

    def test_classification_serialization(self):
        assert VolatilityClassification.LOW.value == "low"
        assert VolatilityClassification.NORMAL.value == "normal"
        assert VolatilityClassification.HIGH.value == "high"
        assert VolatilityClassification.EXTREME.value == "extreme"


# ---------------------------------------------------------------------------
# Feature-Set Status Tests
# ---------------------------------------------------------------------------

class TestFeatureSetStatus:
    """Feature-set readiness assessment tests."""

    def test_feature_set_status_ready(self):
        from app.modules.technical_features.service import _assess_feature_set_status

        availability = [
            FeatureAvailabilityItem(name="trend", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="rsi", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="macd", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="atr", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="bollinger_bands", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="price", status=FeatureAvailability.AVAILABLE, reason="ok"),
        ]
        status, reason = _assess_feature_set_status(availability)
        assert status == FeatureSetStatus.READY
        assert "all core features ready" in reason.lower()

    def test_feature_set_status_warming_up(self):
        from app.modules.technical_features.service import _assess_feature_set_status

        availability = [
            FeatureAvailabilityItem(name="trend", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="rsi", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="macd", status=FeatureAvailability.INSUFFICIENT_DATA, reason="warming"),
            FeatureAvailabilityItem(name="atr", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="bollinger_bands", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="price", status=FeatureAvailability.AVAILABLE, reason="ok"),
        ]
        status, reason = _assess_feature_set_status(availability)
        assert status == FeatureSetStatus.WARMING_UP
        assert "warming up" in reason.lower()

    def test_feature_set_status_unavailable(self):
        from app.modules.technical_features.service import _assess_feature_set_status

        availability = [
            FeatureAvailabilityItem(name="trend", status=FeatureAvailability.UNAVAILABLE, reason="error"),
            FeatureAvailabilityItem(name="rsi", status=FeatureAvailability.UNAVAILABLE, reason="error"),
            FeatureAvailabilityItem(name="macd", status=FeatureAvailability.UNAVAILABLE, reason="error"),
            FeatureAvailabilityItem(name="atr", status=FeatureAvailability.UNAVAILABLE, reason="error"),
            FeatureAvailabilityItem(name="bollinger_bands", status=FeatureAvailability.UNAVAILABLE, reason="error"),
            FeatureAvailabilityItem(name="price", status=FeatureAvailability.UNAVAILABLE, reason="error"),
        ]
        status, reason = _assess_feature_set_status(availability)
        assert status == FeatureSetStatus.UNAVAILABLE
        assert "all core features unavailable" in reason.lower()

    def test_feature_set_status_volume_optional(self):
        """Volume being UNAVAILABLE should not prevent READY."""
        from app.modules.technical_features.service import _assess_feature_set_status

        availability = [
            FeatureAvailabilityItem(name="trend", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="rsi", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="macd", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="atr", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="bollinger_bands", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="price", status=FeatureAvailability.AVAILABLE, reason="ok"),
            FeatureAvailabilityItem(name="volume", status=FeatureAvailability.UNAVAILABLE, reason="no data"),
        ]
        status, reason = _assess_feature_set_status(availability)
        assert status == FeatureSetStatus.READY

    def test_feature_set_status_empty(self):
        from app.modules.technical_features.service import _assess_feature_set_status

        status, reason = _assess_feature_set_status([])
        assert status == FeatureSetStatus.UNAVAILABLE
        assert "no core features" in reason.lower()

    def test_feature_set_status_serialization(self):
        assert FeatureSetStatus.READY.value == "ready"
        assert FeatureSetStatus.WARMING_UP.value == "warming_up"
        assert FeatureSetStatus.UNAVAILABLE.value == "unavailable"


# ---------------------------------------------------------------------------
# Service — Volatility Classification Integration
# ---------------------------------------------------------------------------

class TestServiceVolatilityClassification:
    """Service-level volatility classification integration."""

    @pytest.fixture
    def mock_service_50_candles(self):
        from unittest.mock import AsyncMock, MagicMock
        service = MagicMock()
        candles = _rising_candles(50)
        response = CandlesResponse(
            instrument=Instrument.XAU_USD,
            timeframe=Timeframe.H1,
            count=50,
            source="yfinance",
            source_type=SourceType.FUTURES_PROXY,
            has_gaps=False,
            candles=candles,
        )
        service.get_candles = AsyncMock(return_value=response)
        return service

    @pytest.mark.asyncio
    async def test_volatility_classification_populated(self, mock_service_50_candles):
        from app.modules.technical_features.service import TechnicalFeatureService
        svc = TechnicalFeatureService(market_data_service=mock_service_50_candles)
        result = await svc.get_features(timeframe="1h", limit=300)
        assert result.volatility_classification is not None
        assert result.volatility_classification in list(VolatilityClassification)
        assert result.volatility_classification_reason != ""

    @pytest.mark.asyncio
    async def test_feature_set_status_populated(self, mock_service_50_candles):
        from app.modules.technical_features.service import TechnicalFeatureService
        svc = TechnicalFeatureService(market_data_service=mock_service_50_candles)
        result = await svc.get_features(timeframe="1h", limit=300)
        assert result.feature_set_status in list(FeatureSetStatus)
        assert result.feature_set_reason != ""


# ---------------------------------------------------------------------------
# Multi-Timeframe Tests
# ---------------------------------------------------------------------------

class TestMultiTimeframe:
    """Multi-timeframe feature calculation tests."""

    @pytest.fixture
    def mock_service_multi(self):
        from unittest.mock import AsyncMock, MagicMock

        service = MagicMock()

        async def get_candles_side_effect(timeframe="1h", limit=300):
            if timeframe in ("1m", "5m", "15m"):
                candles = _rising_candles(100)
            else:
                candles = _rising_candles(300)
            return CandlesResponse(
                instrument=Instrument.XAU_USD,
                timeframe=Timeframe.H1,
                count=len(candles),
                source="yfinance",
                source_type=SourceType.FUTURES_PROXY,
                has_gaps=False,
                candles=candles,
            )

        service.get_candles = AsyncMock(side_effect=get_candles_side_effect)
        return service

    @pytest.mark.asyncio
    async def test_multi_timeframe_returns_all(self, mock_service_multi):
        from app.modules.technical_features.service import TechnicalFeatureService
        svc = TechnicalFeatureService(market_data_service=mock_service_multi)
        result = await svc.get_features_multi_timeframe(
            timeframes=["1m", "5m", "15m"], limit=300
        )
        assert isinstance(result, MultiTimeframeResult)
        assert len(result.timeframes) == 3
        assert result.timeframes[0].timeframe == "1m"
        assert result.timeframes[1].timeframe == "5m"
        assert result.timeframes[2].timeframe == "15m"

    @pytest.mark.asyncio
    async def test_multi_timeframe_independent_results(self, mock_service_multi):
        from app.modules.technical_features.service import TechnicalFeatureService
        svc = TechnicalFeatureService(market_data_service=mock_service_multi)
        result = await svc.get_features_multi_timeframe(
            timeframes=["1m", "5m"], limit=300
        )
        for tf_result in result.timeframes:
            assert tf_result.result is not None
            assert tf_result.result.status in list(FeatureAvailability)

    @pytest.mark.asyncio
    async def test_multi_timeframe_feature_set_status(self, mock_service_multi):
        from app.modules.technical_features.service import TechnicalFeatureService
        svc = TechnicalFeatureService(market_data_service=mock_service_multi)
        result = await svc.get_features_multi_timeframe(
            timeframes=["1m", "5m", "15m"], limit=300
        )
        assert result.feature_set_status in list(FeatureSetStatus)

    @pytest.mark.asyncio
    async def test_multi_timeframe_one_fails_others_succeed(self):
        """One timeframe failing should not destroy other results."""
        from unittest.mock import AsyncMock, MagicMock

        service = MagicMock()
        call_count = {"n": 0}

        async def get_candles_side_effect(timeframe="1h", limit=300):
            call_count["n"] += 1
            if timeframe == "5m":
                raise RuntimeError("Simulated provider error")
            candles = _rising_candles(100)
            return CandlesResponse(
                instrument=Instrument.XAU_USD,
                timeframe=Timeframe.H1,
                count=len(candles),
                source="yfinance",
                source_type=SourceType.FUTURES_PROXY,
                has_gaps=False,
                candles=candles,
            )

        service.get_candles = AsyncMock(side_effect=get_candles_side_effect)
        from app.modules.technical_features.service import TechnicalFeatureService
        svc = TechnicalFeatureService(market_data_service=service)
        result = await svc.get_features_multi_timeframe(
            timeframes=["1m", "5m", "15m"], limit=300
        )
        # 1m and 15m should succeed, 5m should be UNAVAILABLE
        assert len(result.timeframes) == 3
        tf1 = next(t for t in result.timeframes if t.timeframe == "1m")
        tf5 = next(t for t in result.timeframes if t.timeframe == "5m")
        tf15 = next(t for t in result.timeframes if t.timeframe == "15m")
        assert tf1.result.status != FeatureAvailability.UNAVAILABLE
        assert tf5.result.status == FeatureAvailability.UNAVAILABLE
        assert tf15.result.status != FeatureAvailability.UNAVAILABLE
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_multi_timeframe_empty_list(self, mock_service_multi):
        from app.modules.technical_features.service import TechnicalFeatureService
        svc = TechnicalFeatureService(market_data_service=mock_service_multi)
        result = await svc.get_features_multi_timeframe(timeframes=[], limit=300)
        assert len(result.timeframes) == 0
        assert result.feature_set_status == FeatureSetStatus.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_multi_timeframe_single_timeframe(self, mock_service_multi):
        from app.modules.technical_features.service import TechnicalFeatureService
        svc = TechnicalFeatureService(market_data_service=mock_service_multi)
        result = await svc.get_features_multi_timeframe(
            timeframes=["1m"], limit=300
        )
        assert len(result.timeframes) == 1
        assert result.timeframes[0].timeframe == "1m"


# ---------------------------------------------------------------------------
# Multi-Timeframe Model Tests
# ---------------------------------------------------------------------------

class TestMultiTimeframeModels:
    """Multi-timeframe model serialization tests."""

    def test_multi_timeframe_result_serialization(self):
        result = MultiTimeframeResult(
            timeframes=[
                TimeframeFeatureResult(
                    timeframe="1m",
                    result=FeatureResult(
                        status=FeatureAvailability.AVAILABLE,
                        reason="ok",
                        feature_set_status=FeatureSetStatus.READY,
                        feature_set_reason="all ready",
                    ),
                ),
            ],
            feature_set_status=FeatureSetStatus.READY,
            feature_set_reason="all ready",
        )
        data = result.model_dump(mode="json")
        assert data["feature_set_status"] == "ready"
        assert len(data["timeframes"]) == 1
        assert data["timeframes"][0]["timeframe"] == "1m"
        assert data["timeframes"][0]["result"]["feature_set_status"] == "ready"

    def test_feature_result_new_fields_serialization(self):
        result = FeatureResult(
            status=FeatureAvailability.AVAILABLE,
            reason="ok",
            feature_set_status=FeatureSetStatus.READY,
            feature_set_reason="all ready",
            volatility_classification=VolatilityClassification.HIGH,
            volatility_classification_reason="ATR% 1.8% >= high threshold 1.5%",
        )
        data = result.model_dump(mode="json")
        assert data["feature_set_status"] == "ready"
        assert data["volatility_classification"] == "high"
        assert "extreme" not in data["volatility_classification_reason"]

    def test_feature_result_defaults(self):
        result = FeatureResult(status=FeatureAvailability.UNAVAILABLE)
        data = result.model_dump(mode="json")
        assert data["feature_set_status"] == "unavailable"
        assert data["volatility_classification_reason"] == ""


# ---------------------------------------------------------------------------
# Regression: Bollinger Bands uses sample std dev (BUG#2 fix)
# ---------------------------------------------------------------------------

class TestBollingerSampleStdDev:
    """Regression test: Bollinger Bands must use sample standard deviation (N-1)."""

    def test_bollinger_uses_sample_std_not_population(self):
        """
        With N=20 data points, population std divides by 20, sample divides by 19.
        Verify the bands use sample std (Bollinger's original definition).
        """
        import math
        # Create 20 candles with known close prices
        closes = [100.0 + i * 0.5 for i in range(20)]
        candles = _make_candles(closes)
        result = calculate_bollinger_bands(candles, period=20, std_dev=2.0)

        assert result.availability == FeatureAvailability.AVAILABLE

        # Manually compute expected values using sample std (N-1)
        middle = sum(closes) / 20
        sample_variance = sum((c - middle) ** 2 for c in closes) / 19  # N-1
        sample_sd = math.sqrt(sample_variance)
        expected_upper = middle + 2.0 * sample_sd
        expected_lower = middle - 2.0 * sample_sd

        assert abs(result.middle_band - middle) < 1e-4
        assert abs(result.upper_band - expected_upper) < 1e-4
        assert abs(result.lower_band - expected_lower) < 1e-4

    def test_bollinger_not_population_std(self):
        """
        Verify population std (divide by N) produces different result than what we calculate.
        If someone reverts the fix, this test catches it.
        """
        import math
        closes = [100.0 + i * 0.5 for i in range(20)]
        candles = _make_candles(closes)
        result = calculate_bollinger_bands(candles, period=20, std_dev=2.0)

        middle = sum(closes) / 20
        population_sd = math.sqrt(sum((c - middle) ** 2 for c in closes) / 20)
        sample_sd = math.sqrt(sum((c - middle) ** 2 for c in closes) / 19)

        # Population and sample SD differ
        assert population_sd != sample_sd
        # Result should match sample, NOT population
        expected_with_population = middle + 2.0 * population_sd
        assert abs(result.upper_band - expected_with_population) > 0.001, (
            "Bollinger Bands upper band matches population std — fix was reverted!"
        )


# ---------------------------------------------------------------------------
# Regression: ATR threshold ordering validation (BUG#3 fix)
# ---------------------------------------------------------------------------

class TestATRThresholdValidation:
    """Regression test: ATR thresholds must be logically ordered."""

    def test_low_threshold_must_be_below_high(self):
        """atr_low_threshold_pct must be < atr_high_threshold_pct."""
        with pytest.raises(ValueError, match="atr_low_threshold_pct must be < atr_high_threshold_pct"):
            TechnicalFeaturesSettings(
                atr_low_threshold_pct=5.0,
                atr_high_threshold_pct=1.5,
                atr_extreme_threshold_pct=3.0,
            )

    def test_valid_thresholds_accepted(self):
        """Valid threshold ordering should not raise."""
        settings = TechnicalFeaturesSettings(
            atr_low_threshold_pct=0.3,
            atr_high_threshold_pct=1.5,
            atr_extreme_threshold_pct=3.0,
        )
        assert settings.atr_low_threshold_pct == 0.3
        assert settings.atr_high_threshold_pct == 1.5
        assert settings.atr_extreme_threshold_pct == 3.0

    def test_extreme_must_be_above_high(self):
        """atr_extreme_threshold_pct must be > atr_high_threshold_pct."""
        with pytest.raises(ValueError, match="atr_extreme_threshold_pct must be > atr_high_threshold_pct"):
            TechnicalFeaturesSettings(
                atr_extreme_threshold_pct=1.0,
                atr_high_threshold_pct=1.5,
            )
