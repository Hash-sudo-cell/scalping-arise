"""
Scalping Arise — Provider Adapter Tests

Tests provider symbol mapping, capabilities, and response parsing
using controlled inputs.
"""

from __future__ import annotations

import pytest

from app.modules.market_data.models import Instrument, SourceType, Timeframe, TimeframeCapability
from app.modules.market_data.providers.twelve_data import TwelveDataProvider
from app.modules.market_data.providers.yfinance import YFinanceProvider


class TestTwelveDataProvider:
    def setup_method(self) -> None:
        self.provider = TwelveDataProvider(api_key="test_key")

    def test_name(self) -> None:
        assert self.provider.name == "twelve_data"

    def test_map_symbol_xau_usd(self) -> None:
        assert self.provider.map_symbol(Instrument.XAU_USD) == "XAU/USD"

    def test_map_symbol_custom(self) -> None:
        provider = TwelveDataProvider(
            api_key="test",
            symbol_map={Instrument.XAU_USD: "XAUUSD"},
        )
        assert provider.map_symbol(Instrument.XAU_USD) == "XAUUSD"

    def test_capabilities(self) -> None:
        caps = self.provider.get_capabilities()
        assert caps.provider_name == "twelve_data"
        assert Instrument.XAU_USD in caps.supported_instruments
        assert caps.requires_api_key is True
        assert caps.timeframe_capabilities[Timeframe.M1] == TimeframeCapability.NATIVE
        assert caps.timeframe_capabilities[Timeframe.M3] == TimeframeCapability.UNSUPPORTED
        assert caps.timeframe_capabilities[Timeframe.H1] == TimeframeCapability.NATIVE

    def test_timeframe_not_in_map(self) -> None:
        # M3 is unsupported by Twelve Data
        caps = self.provider.get_capabilities()
        assert caps.timeframe_capabilities[Timeframe.M3] == TimeframeCapability.UNSUPPORTED

    def test_source_identity_spot(self) -> None:
        """Twelve Data produces SPOT source type with XAU/USD provider instrument."""
        assert self.provider.map_symbol(Instrument.XAU_USD) == "XAU/USD"
        # Verify capabilities reflect spot instrument
        caps = self.provider.get_capabilities()
        assert caps.provider_name == "twelve_data"


class TestYFinanceProvider:
    def setup_method(self) -> None:
        self.provider = YFinanceProvider()

    def test_name(self) -> None:
        assert self.provider.name == "yfinance"

    def test_map_symbol_xau_usd(self) -> None:
        assert self.provider.map_symbol(Instrument.XAU_USD) == "GC=F"

    def test_map_symbol_custom(self) -> None:
        provider = YFinanceProvider(
            symbol_map={Instrument.XAU_USD: "XAUUSD=X"},
        )
        assert provider.map_symbol(Instrument.XAU_USD) == "XAUUSD=X"

    def test_capabilities(self) -> None:
        caps = self.provider.get_capabilities()
        assert caps.provider_name == "yfinance"
        assert caps.requires_api_key is False
        assert caps.timeframe_capabilities[Timeframe.M1] == TimeframeCapability.NATIVE
        assert caps.timeframe_capabilities[Timeframe.M3] == TimeframeCapability.DERIVED
        assert caps.timeframe_capabilities[Timeframe.H4] == TimeframeCapability.DERIVED
        assert caps.timeframe_capabilities[Timeframe.D1] == TimeframeCapability.NATIVE

    def test_derived_detection(self) -> None:
        assert self.provider._is_derived(Timeframe.M3) is True
        assert self.provider._is_derived(Timeframe.H4) is True
        assert self.provider._is_derived(Timeframe.M1) is False
        assert self.provider._is_derived(Timeframe.D1) is False

    def test_source_identity_futures_proxy(self) -> None:
        """yfinance produces FUTURES_PROXY source type with GC=F provider instrument."""
        assert self.provider.map_symbol(Instrument.XAU_USD) == "GC=F"

    def test_aggregation(self) -> None:
        from app.modules.market_data.models import NormalizedCandle
        from datetime import datetime, timezone

        source = [
            NormalizedCandle(
                instrument=Instrument.XAU_USD,
                provider_instrument="GC=F",
                source_type=SourceType.FUTURES_PROXY,
                timeframe=Timeframe.M1,
                timestamp=datetime(2024, 1, 15, 12, i, 0, tzinfo=timezone.utc),
                open=2000 + i,
                high=2001 + i,
                low=1999 + i,
                close=2000.5 + i,
                volume=100,
                is_closed=True,
                source="test",
            )
            for i in range(6)
        ]

        result = self.provider._aggregate_candles(source, Timeframe.M3, 3)
        assert len(result) == 2
        assert result[0].timeframe == Timeframe.M3
        assert result[0].open == 2000.0
        assert result[0].high == 2003.0  # max of first 3
        assert result[0].close == 2002.5  # close of 3rd
        assert result[0].provider_instrument == "GC=F"
        assert result[0].source_type == SourceType.FUTURES_PROXY

    def test_aggregation_incomplete_batch_skipped(self) -> None:
        from app.modules.market_data.models import NormalizedCandle
        from datetime import datetime, timezone

        source = [
            NormalizedCandle(
                instrument=Instrument.XAU_USD,
                provider_instrument="GC=F",
                source_type=SourceType.FUTURES_PROXY,
                timeframe=Timeframe.M1,
                timestamp=datetime(2024, 1, 15, 12, i, 0, tzinfo=timezone.utc),
                open=2000,
                high=2010,
                low=1990,
                close=2005,
                volume=100,
                is_closed=True,
                source="test",
            )
            for i in range(4)  # 4 candles, factor=3 -> 1 complete batch + 1 incomplete
        ]

        result = self.provider._aggregate_candles(source, Timeframe.M3, 3)
        assert len(result) == 1  # Only complete batch
