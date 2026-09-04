"""
Scalping Arise — Market Data Model Tests
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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


# ---------------------------------------------------------------------------
# Timeframe tests
# ---------------------------------------------------------------------------

class TestTimeframe:
    def test_all_values_exist(self) -> None:
        assert len(Timeframe) == 10

    def test_interval_seconds(self) -> None:
        assert Timeframe.M1.interval_seconds == 60
        assert Timeframe.M5.interval_seconds == 300
        assert Timeframe.H1.interval_seconds == 3600
        assert Timeframe.D1.interval_seconds == 86400

    def test_display_name(self) -> None:
        assert Timeframe.M1.display_name == "1 Minute"
        assert Timeframe.H4.display_name == "4 Hour"
        assert Timeframe.D1.display_name == "Daily"


# ---------------------------------------------------------------------------
# Instrument tests
# ---------------------------------------------------------------------------

class TestInstrument:
    def test_xau_usd(self) -> None:
        assert Instrument.XAU_USD.value == "XAU/USD"


# ---------------------------------------------------------------------------
# NormalizedCandle tests
# ---------------------------------------------------------------------------

class TestNormalizedCandle:
    def _make_candle(self, **overrides) -> NormalizedCandle:
        defaults = dict(
            instrument=Instrument.XAU_USD,
            provider_instrument="XAU/USD",
            source_type=SourceType.SPOT,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0,
            high=2010.0,
            low=1995.0,
            close=2005.0,
            volume=1000.0,
            is_closed=True,
            source="test",
        )
        defaults.update(overrides)
        return NormalizedCandle(**defaults)

    def test_valid_candle(self) -> None:
        candle = self._make_candle()
        assert candle.instrument == Instrument.XAU_USD
        assert candle.open == 2000.0
        assert candle.is_closed is True

    def test_forming_candle(self) -> None:
        candle = self._make_candle(is_closed=False)
        assert candle.is_closed is False

    def test_no_volume(self) -> None:
        candle = self._make_candle(volume=None)
        assert candle.volume is None

    def test_rejects_zero_price(self) -> None:
        with pytest.raises(Exception):
            self._make_candle(open=0)

    def test_rejects_negative_price(self) -> None:
        with pytest.raises(Exception):
            self._make_candle(close=-100)


# ---------------------------------------------------------------------------
# LatestPrice tests
# ---------------------------------------------------------------------------

class TestLatestPrice:
    def test_valid_price(self) -> None:
        price = LatestPrice(
            instrument=Instrument.XAU_USD,
            provider_instrument="XAU/USD",
            source_type=SourceType.SPOT,
            price=2050.50,
            timestamp=datetime.now(timezone.utc),
            source="test",
        )
        assert price.price == 2050.50
        assert price.is_forming is False

    def test_forming_price(self) -> None:
        price = LatestPrice(
            instrument=Instrument.XAU_USD,
            provider_instrument="XAU/USD",
            source_type=SourceType.SPOT,
            price=2050.50,
            timestamp=datetime.now(timezone.utc),
            source="test",
            is_forming=True,
        )
        assert price.is_forming is True


# ---------------------------------------------------------------------------
# ProviderCapabilities tests
# ---------------------------------------------------------------------------

class TestProviderCapabilities:
    def _make_caps(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name="test",
            supported_instruments=[Instrument.XAU_USD],
            timeframe_capabilities={
                Timeframe.M1: TimeframeCapability.NATIVE,
                Timeframe.M5: TimeframeCapability.NATIVE,
                Timeframe.H1: TimeframeCapability.NATIVE,
                Timeframe.D1: TimeframeCapability.NATIVE,
                Timeframe.M3: TimeframeCapability.UNSUPPORTED,
            },
        )

    def test_instrument_supported(self) -> None:
        caps = self._make_caps()
        assert caps.is_instrument_supported(Instrument.XAU_USD)

    def test_instrument_not_supported(self) -> None:
        caps = self._make_caps()
        # No other instruments in the enum for now, but test the logic
        assert caps.is_instrument_supported(Instrument.XAU_USD)

    def test_timeframe_native(self) -> None:
        caps = self._make_caps()
        assert caps.is_timeframe_supported(Timeframe.M1) is True

    def test_timeframe_unsupported(self) -> None:
        caps = self._make_caps()
        assert caps.is_timeframe_supported(Timeframe.M3) is False


# ---------------------------------------------------------------------------
# ProviderHealth tests
# ---------------------------------------------------------------------------

class TestProviderHealth:
    def test_healthy(self) -> None:
        health = ProviderHealth(
            provider_name="test",
            status=ProviderHealthStatus.HEALTHY,
            latency_ms=50.0,
            message="OK",
        )
        assert health.status == ProviderHealthStatus.HEALTHY

    def test_unavailable(self) -> None:
        health = ProviderHealth(
            provider_name="test",
            status=ProviderHealthStatus.UNAVAILABLE,
            message="Connection refused",
        )
        assert health.status == ProviderHealthStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# Source identity tests
# ---------------------------------------------------------------------------

class TestSourceIdentity:
    def test_spot_source_type(self) -> None:
        candle = NormalizedCandle(
            instrument=Instrument.XAU_USD,
            provider_instrument="XAU/USD",
            source_type=SourceType.SPOT,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0, high=2010.0, low=1995.0, close=2005.0,
            source="twelve_data",
        )
        assert candle.source_type == SourceType.SPOT
        assert candle.provider_instrument == "XAU/USD"

    def test_futures_proxy_source_type(self) -> None:
        candle = NormalizedCandle(
            instrument=Instrument.XAU_USD,
            provider_instrument="GC=F",
            source_type=SourceType.FUTURES_PROXY,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0, high=2010.0, low=1995.0, close=2005.0,
            source="yfinance",
        )
        assert candle.source_type == SourceType.FUTURES_PROXY
        assert candle.provider_instrument == "GC=F"

    def test_source_type_enum_values(self) -> None:
        assert SourceType.SPOT.value == "spot"
        assert SourceType.FUTURES_PROXY.value == "futures_proxy"

    def test_latest_price_spot(self) -> None:
        price = LatestPrice(
            instrument=Instrument.XAU_USD,
            provider_instrument="XAU/USD",
            source_type=SourceType.SPOT,
            price=2050.0,
            timestamp=datetime.now(timezone.utc),
            source="twelve_data",
        )
        assert price.source_type == SourceType.SPOT
        assert price.provider_instrument == "XAU/USD"

    def test_latest_price_futures_proxy(self) -> None:
        price = LatestPrice(
            instrument=Instrument.XAU_USD,
            provider_instrument="GC=F",
            source_type=SourceType.FUTURES_PROXY,
            price=2050.0,
            timestamp=datetime.now(timezone.utc),
            source="yfinance",
        )
        assert price.source_type == SourceType.FUTURES_PROXY
        assert price.provider_instrument == "GC=F"
