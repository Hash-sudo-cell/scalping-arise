"""
Scalping Arise — Live Streaming Component Tests

Deterministic tests for candle lifecycle, connection health,
OANDA provider, and TradingView provider using controlled inputs.
No network calls — all external dependencies are mocked.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment
os.environ["SCALPING_ARISE_ENVIRONMENT"] = "testing"
os.environ["SCALPING_ARISE_DEBUG"] = "true"
os.environ["SCALPING_ARISE_LOG_LEVEL"] = "WARNING"
os.environ["SCALPING_ARISE_TWELVE_DATA_API_KEY"] = "test_key"
os.environ["SCALPING_ARISE_PRIMARY_PROVIDER"] = "twelve_data"
os.environ["SCALPING_ARISE_FALLBACK_PROVIDER"] = "yfinance"
os.environ["SCALPING_ARISE_LIVE_ENABLED"] = "false"

from app.modules.market_data.live.candle_lifecycle import (
    CandleLifecycle,
    _candle_period_start,
    _is_new_period,
)
from app.modules.market_data.live.connection_health import ConnectionHealthManager
from app.modules.market_data.models import (
    CandleState,
    ConnectionState,
    Instrument,
    NormalizedCandle,
    SourceType,
    Timeframe,
)
from app.modules.market_data.providers.oanda import OandaProvider
from app.modules.market_data.providers.tradingview import TradingViewProvider


# ---------------------------------------------------------------------------
# Candle Lifecycle Tests
# ---------------------------------------------------------------------------

class TestCandlePeriodStart:
    def test_m1_alignment(self) -> None:
        ts = datetime(2024, 1, 15, 12, 7, 30, tzinfo=timezone.utc)
        result = _candle_period_start(ts, Timeframe.M1)
        assert result == datetime(2024, 1, 15, 12, 7, 0, tzinfo=timezone.utc)

    def test_m5_alignment(self) -> None:
        ts = datetime(2024, 1, 15, 12, 7, 30, tzinfo=timezone.utc)
        result = _candle_period_start(ts, Timeframe.M5)
        assert result == datetime(2024, 1, 15, 12, 5, 0, tzinfo=timezone.utc)

    def test_h1_alignment(self) -> None:
        ts = datetime(2024, 1, 15, 12, 37, 0, tzinfo=timezone.utc)
        result = _candle_period_start(ts, Timeframe.H1)
        assert result == datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_d1_alignment(self) -> None:
        ts = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        result = _candle_period_start(ts, Timeframe.D1)
        assert result == datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)


class TestIsNewPeriod:
    def test_same_period(self) -> None:
        t1 = datetime(2024, 1, 15, 12, 0, 30, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 15, 12, 0, 45, tzinfo=timezone.utc)
        assert _is_new_period(t1, t2, Timeframe.M1) is False

    def test_new_period(self) -> None:
        t1 = datetime(2024, 1, 15, 12, 0, 30, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 15, 12, 1, 0, tzinfo=timezone.utc)
        assert _is_new_period(t1, t2, Timeframe.M1) is True

    def test_new_period_h1(self) -> None:
        t1 = datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
        assert _is_new_period(t1, t2, Timeframe.H1) is True

    def test_same_period_h1(self) -> None:
        t1 = datetime(2024, 1, 15, 12, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 15, 12, 50, 0, tzinfo=timezone.utc)
        assert _is_new_period(t1, t2, Timeframe.H1) is False


class TestCandleLifecycle:
    def test_first_tick_creates_forming(self) -> None:
        lc = CandleLifecycle(Instrument.XAU_USD, Timeframe.M1)
        ts = datetime(2024, 1, 15, 12, 7, 30, tzinfo=timezone.utc)
        result = lc.update(ts, 2000.0, 2005.0, 1995.0, 2002.0, 100.0)

        assert result is None  # No closed candle on first tick
        assert lc.state == CandleState.FORMING
        assert lc.current_candle is not None
        assert lc.current_candle.open == 2000.0
        assert lc.current_candle.close == 2002.0
        assert lc.current_candle.is_closed is False
        assert lc.current_candle.source_type == SourceType.LIVE

    def test_same_period_updates_ohlc(self) -> None:
        lc = CandleLifecycle(Instrument.XAU_USD, Timeframe.M1)
        ts1 = datetime(2024, 1, 15, 12, 7, 10, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 12, 7, 30, tzinfo=timezone.utc)

        lc.update(ts1, 2000.0, 2005.0, 1995.0, 2002.0)
        lc.update(ts2, 2001.0, 2008.0, 1993.0, 2006.0)

        assert lc.state == CandleState.FORMING
        assert lc.current_candle.high == 2008.0  # Updated high
        assert lc.current_candle.low == 1993.0   # Updated low
        assert lc.current_candle.close == 2006.0  # Updated close
        assert lc.current_candle.open == 2000.0   # Open preserved

    def test_new_period_closes_previous(self) -> None:
        lc = CandleLifecycle(Instrument.XAU_USD, Timeframe.M1)
        ts1 = datetime(2024, 1, 15, 12, 7, 30, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 12, 8, 10, tzinfo=timezone.utc)

        lc.update(ts1, 2000.0, 2005.0, 1995.0, 2002.0)
        closed = lc.update(ts2, 2010.0, 2015.0, 2005.0, 2012.0)

        assert closed is not None
        assert closed.is_closed is True
        assert closed.timestamp == datetime(2024, 1, 15, 12, 7, 0, tzinfo=timezone.utc)
        assert closed.open == 2000.0
        assert closed.close == 2002.0
        assert lc.state == CandleState.FORMING
        assert lc.current_candle.open == 2010.0
        assert lc.closed_count == 1

    def test_force_close(self) -> None:
        lc = CandleLifecycle(Instrument.XAU_USD, Timeframe.M1)
        ts = datetime(2024, 1, 15, 12, 7, 30, tzinfo=timezone.utc)
        lc.update(ts, 2000.0, 2005.0, 1995.0, 2002.0)

        closed = lc.close_current()
        assert closed is not None
        assert closed.is_closed is True
        assert lc.current_candle is None
        assert lc.closed_count == 1

    def test_force_close_empty(self) -> None:
        lc = CandleLifecycle(Instrument.XAU_USD, Timeframe.M1)
        closed = lc.close_current()
        assert closed is None

    def test_reset(self) -> None:
        lc = CandleLifecycle(Instrument.XAU_USD, Timeframe.M1)
        ts = datetime(2024, 1, 15, 12, 7, 30, tzinfo=timezone.utc)
        lc.update(ts, 2000.0, 2005.0, 1995.0, 2002.0)
        lc.reset()

        assert lc.current_candle is None
        assert lc.last_update is None
        assert lc.closed_count == 0

    def test_volume_accumulation(self) -> None:
        lc = CandleLifecycle(Instrument.XAU_USD, Timeframe.M1)
        ts1 = datetime(2024, 1, 15, 12, 7, 10, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 12, 7, 30, tzinfo=timezone.utc)

        lc.update(ts1, 2000.0, 2005.0, 1995.0, 2002.0, 100.0)
        lc.update(ts2, 2001.0, 2006.0, 1996.0, 2003.0, 50.0)

        assert lc.current_candle.volume == 150.0

    def test_candle_period_start_alignment(self) -> None:
        lc = CandleLifecycle(Instrument.XAU_USD, Timeframe.M5)
        ts = datetime(2024, 1, 15, 12, 7, 30, tzinfo=timezone.utc)
        lc.update(ts, 2000.0, 2005.0, 1995.0, 2002.0)

        # Should be aligned to 12:05
        assert lc.current_candle.timestamp == datetime(2024, 1, 15, 12, 5, 0, tzinfo=timezone.utc)

    def test_multiple_closes(self) -> None:
        lc = CandleLifecycle(Instrument.XAU_USD, Timeframe.M1)
        ts1 = datetime(2024, 1, 15, 12, 7, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 12, 8, 0, tzinfo=timezone.utc)
        ts3 = datetime(2024, 1, 15, 12, 9, 0, tzinfo=timezone.utc)

        lc.update(ts1, 2000.0, 2005.0, 1995.0, 2002.0)
        lc.update(ts2, 2010.0, 2015.0, 2005.0, 2012.0)
        lc.update(ts3, 2020.0, 2025.0, 2015.0, 2022.0)

        assert lc.closed_count == 2
        assert lc.current_candle.open == 2020.0


# ---------------------------------------------------------------------------
# Connection Health Tests
# ---------------------------------------------------------------------------

class TestConnectionHealthManager:
    def setup_method(self) -> None:
        self.hm = ConnectionHealthManager()

    def test_initial_state(self) -> None:
        assert self.hm.state == ConnectionState.DISCONNECTED
        assert self.hm.oanda_connected is False
        assert self.hm.tv_connected is False

    def test_start_transitions_to_connecting(self) -> None:
        self.hm.start()
        assert self.hm.state == ConnectionState.CONNECTING

    def test_oanda_connected_transitions_to_degraded(self) -> None:
        self.hm.start()
        self.hm.mark_oanda_connected()
        assert self.hm.state == ConnectionState.DEGRADED  # TV not connected yet

    def test_both_connected_transitions_to_connected(self) -> None:
        self.hm.start()
        self.hm.mark_oanda_connected()
        self.hm.mark_tv_connected()
        assert self.hm.state == ConnectionState.CONNECTED

    def test_tv_connected_without_oanda(self) -> None:
        self.hm.start()
        self.hm.mark_tv_connected()
        assert self.hm.state == ConnectionState.DEGRADED

    def test_oanda_disconnect_without_tv(self) -> None:
        self.hm.start()
        self.hm.mark_oanda_connected()
        self.hm.mark_oanda_disconnected("timeout")
        assert self.hm.state == ConnectionState.DISCONNECTED
        assert self.hm.last_error == "timeout"

    def test_oanda_disconnect_with_tv(self) -> None:
        self.hm.start()
        self.hm.mark_oanda_connected()
        self.hm.mark_tv_connected()
        self.hm.mark_oanda_disconnected("timeout")
        assert self.hm.state == ConnectionState.DEGRADED

    def test_tv_disconnect_with_oanda(self) -> None:
        self.hm.start()
        self.hm.mark_oanda_connected()
        self.hm.mark_tv_connected()
        self.hm.mark_tv_disconnected()
        assert self.hm.state == ConnectionState.DEGRADED

    def test_staleness_detection(self) -> None:
        self.hm.start()
        self.hm.mark_oanda_connected()
        self.hm.mark_tv_connected()
        assert self.hm.state == ConnectionState.CONNECTED

        # Simulate stale by setting last_data_at to past
        self.hm._last_data_at = datetime.now(timezone.utc) - timedelta(seconds=100)

        is_stale = self.hm.check_staleness()
        assert is_stale is True
        assert self.hm.state == ConnectionState.STALE

    def test_data_received_resets_stale(self) -> None:
        self.hm.start()
        self.hm.mark_oanda_connected()
        self.hm.mark_tv_connected()
        self.hm._last_data_at = datetime.now(timezone.utc) - timedelta(seconds=100)
        self.hm._transition(ConnectionState.STALE)

        self.hm.record_data_received()
        assert self.hm.state == ConnectionState.CONNECTED

    def test_reconnect_attempts_increment(self) -> None:
        self.hm.start()
        self.hm.mark_oanda_connected()
        self.hm.mark_oanda_disconnected()

        def _fake_reconnect():
            pass

        async def _run():
            await self.hm.start_reconnect(_fake_reconnect)
            await self.hm.start_reconnect(_fake_reconnect)

        asyncio.new_event_loop().run_until_complete(_run())
        assert self.hm.reconnect_attempts == 2

    def test_reset(self) -> None:
        self.hm.start()
        self.hm.mark_oanda_connected()
        self.hm.mark_tv_connected()
        self.hm.record_data_received()
        self.hm.reset()

        assert self.hm.state == ConnectionState.DISCONNECTED
        assert self.hm.oanda_connected is False
        assert self.hm.reconnect_attempts == 0

    def test_status_dict(self) -> None:
        self.hm.start()
        status = self.hm.get_status_dict()
        assert "connection_state" in status
        assert "oanda_connected" in status
        assert "tv_connected" in status
        assert "reconnect_attempts" in status


# ---------------------------------------------------------------------------
# OANDA Provider Tests
# ---------------------------------------------------------------------------

class TestOandaProvider:
    def setup_method(self) -> None:
        self.provider = OandaProvider(
            account_id="101-001-12345678-001",
            api_token="test_token_abc123",
        )

    def test_name(self) -> None:
        assert self.provider.name == "oanda"

    def test_map_symbol(self) -> None:
        assert self.provider.map_symbol(Instrument.XAU_USD) == "XAU_USD"

    def test_capabilities(self) -> None:
        caps = self.provider.get_capabilities()
        assert caps.provider_name == "oanda"
        assert caps.requires_api_key is True
        assert caps.rate_limit_per_minute == 120
        assert Instrument.XAU_USD in caps.supported_instruments

    def test_capabilities_all_timeframes(self) -> None:
        from app.modules.market_data.models import TimeframeCapability
        caps = self.provider.get_capabilities()
        for tf in Timeframe:
            assert caps.timeframe_capabilities[tf] == TimeframeCapability.NATIVE

    def test_parse_timestamp(self) -> None:
        ts = self.provider._oanda_timestamp_to_utc("2024-01-15T14:30:00.123456789Z")
        assert ts.tzinfo == timezone.utc
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.hour == 14
        assert ts.minute == 30

    def test_parse_candle(self) -> None:
        mid = {
            "o": "2000.500",
            "h": "2010.250",
            "l": "1995.750",
            "c": "2005.000",
            "v": "1500",
            "time": "2024-01-15T14:30:00.000000000Z",
        }
        candle = self.provider._parse_oanda_candle(mid, Instrument.XAU_USD, Timeframe.M1, is_closed=True)
        assert candle.open == 2000.5
        assert candle.high == 2010.25
        assert candle.low == 1995.75
        assert candle.close == 2005.0
        assert candle.volume == 1500.0
        assert candle.is_closed is True
        assert candle.source_type == SourceType.LIVE
        assert candle.source == "oanda"
        assert candle.provider_instrument == "XAU_USD"


# ---------------------------------------------------------------------------
# TradingView Provider Tests
# ---------------------------------------------------------------------------

class TestTradingViewProvider:
    def setup_method(self) -> None:
        self.provider = TradingViewProvider(symbol="OANDA:XAUUSD")

    def test_name(self) -> None:
        assert self.provider.name == "tradingview"

    def test_map_symbol(self) -> None:
        assert self.provider.map_symbol(Instrument.XAU_USD) == "OANDA:XAUUSD"

    def test_capabilities(self) -> None:
        caps = self.provider.get_capabilities()
        assert caps.provider_name == "tradingview"
        assert caps.requires_api_key is False
        assert Instrument.XAU_USD in caps.supported_instruments

    def test_not_connected_initially(self) -> None:
        assert self.provider.is_connected is False

    def test_health_check_when_disconnected(self) -> None:
        import asyncio
        health = asyncio.new_event_loop().run_until_complete(self.provider.health_check())
        assert health.status.value == "unavailable"

    def test_verify_price_consistent(self) -> None:
        is_consistent, divergence = self.provider.verify_price(2000.0, 2001.0, tolerance_pct=0.3)
        assert is_consistent is True
        assert divergence < 0.3

    def test_verify_price_divergent(self) -> None:
        is_consistent, divergence = self.provider.verify_price(2000.0, 2020.0, tolerance_pct=0.3)
        assert is_consistent is False
        assert divergence > 0.9

    def test_verify_price_zero(self) -> None:
        is_consistent, divergence = self.provider.verify_price(0, 2000.0)
        assert is_consistent is False
        assert divergence == 100.0

    def test_fetch_historical_when_disconnected(self) -> None:
        import asyncio
        candles = asyncio.new_event_loop().run_until_complete(
            self.provider.fetch_historical_candles(Instrument.XAU_USD, Timeframe.M5, 10)
        )
        assert candles == []

    def test_fetch_latest_price_when_disconnected(self) -> None:
        import asyncio
        price = asyncio.new_event_loop().run_until_complete(
            self.provider.fetch_latest_price(Instrument.XAU_USD)
        )
        assert price is None
