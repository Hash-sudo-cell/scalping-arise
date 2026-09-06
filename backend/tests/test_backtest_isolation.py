"""
Scalping Arise — Backtest Data Isolation Tests

Proves that historical backtests NEVER access live market data providers.
All signal generation and trade planning must use the replay data path.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from app.modules.backtesting.replay_market_data_provider import ReplayMarketDataProvider
from app.modules.backtesting.replay_market_data_service import ReplayMarketDataService
from app.modules.market_data.models import (
    Instrument,
    NormalizedCandle,
    ProviderHealthStatus,
    SourceType,
    Timeframe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candle(
    ts: datetime,
    close: float = 2000.0,
    instrument: Instrument = Instrument.XAU_USD,
    timeframe: Timeframe = Timeframe.H1,
) -> NormalizedCandle:
    return NormalizedCandle(
        timestamp=ts,
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=100.0,
        instrument=instrument,
        timeframe=timeframe,
        source="test",
        source_type=SourceType.SPOT,
        provider_instrument=instrument.value,
    )


def _make_candles(
    count: int = 50,
    start: datetime | None = None,
    interval_minutes: int = 60,
    base_price: float = 2000.0,
) -> list[NormalizedCandle]:
    if start is None:
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i in range(count):
        ts = start + timedelta(minutes=i * interval_minutes)
        price = base_price + (i % 10) * 0.5
        candles.append(_make_candle(ts, close=price))
    return candles


# ---------------------------------------------------------------------------
# Test: ReplayMarketDataProvider
# ---------------------------------------------------------------------------

class TestReplayMarketDataProvider:
    """Test the historical replay provider in isolation."""

    def test_no_live_references(self):
        """Provider has no reference to live providers."""
        provider = ReplayMarketDataProvider()
        assert not hasattr(provider, '_primary')
        assert not hasattr(provider, '_fallback')
        assert not hasattr(provider, '_failover')
        assert provider.name == "replay"

    def test_load_data(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)
        # After loading, should have data
        assert (Instrument.XAU_USD.value, Timeframe.H1.value) in provider._candles

    @pytest.mark.asyncio
    async def test_fetch_without_time_raises(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)

        with pytest.raises(RuntimeError, match="current_time not set"):
            await provider.fetch_historical_candles(Instrument.XAU_USD, Timeframe.H1, 10)

    @pytest.mark.asyncio
    async def test_visible_candles_respects_current_time(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)

        # Set time to candle index 19 (20th candle)
        provider.set_current_time(candles[19].timestamp)

        result = await provider.fetch_historical_candles(Instrument.XAU_USD, Timeframe.H1, 100)

        # Should return only 20 candles (indices 0-19)
        assert len(result) == 20
        for c in result:
            assert c.timestamp <= candles[19].timestamp

    @pytest.mark.asyncio
    async def test_future_candles_inaccessible(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)

        # Set time to candle index 9
        provider.set_current_time(candles[9].timestamp)

        result = await provider.fetch_historical_candles(Instrument.XAU_USD, Timeframe.H1, 50)

        # Should return 10 candles (0-9), not 50
        assert len(result) == 10
        for c in result:
            assert c.timestamp <= candles[9].timestamp

    @pytest.mark.asyncio
    async def test_limit_truncates_correctly(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)

        provider.set_current_time(candles[49].timestamp)

        result = await provider.fetch_historical_candles(Instrument.XAU_USD, Timeframe.H1, 10)

        # Should return only 10 most recent
        assert len(result) == 10
        assert result[-1].timestamp == candles[49].timestamp

    @pytest.mark.asyncio
    async def test_no_live_price_leak(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)
        provider.set_current_time(candles[25].timestamp)

        price = await provider.fetch_latest_price(Instrument.XAU_USD)

        assert price is not None
        assert price.instrument == Instrument.XAU_USD
        assert price.source == "replay"
        assert price.bid == candles[25].close

    @pytest.mark.asyncio
    async def test_fetch_latest_candle_respects_time(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)
        provider.set_current_time(candles[14].timestamp)

        latest = await provider.fetch_latest_candle(Instrument.XAU_USD, Timeframe.H1)

        assert latest is not None
        assert latest.timestamp == candles[14].timestamp

    @pytest.mark.asyncio
    async def test_empty_data_raises(self):
        provider = ReplayMarketDataProvider()
        provider.set_current_time(datetime.now(timezone.utc))

        with pytest.raises(RuntimeError, match="No historical data loaded"):
            await provider.fetch_historical_candles(Instrument.XAU_USD, Timeframe.H1, 10)

    @pytest.mark.asyncio
    async def test_health_check_with_data(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(10)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)
        provider.set_current_time(candles[5].timestamp)

        health = await provider.health_check()
        assert health.status == ProviderHealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_without_data(self):
        provider = ReplayMarketDataProvider()
        health = await provider.health_check()
        assert health.status == ProviderHealthStatus.DEGRADED

    def test_capabilities_from_loaded_data(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(10)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)

        caps = provider.get_capabilities()
        assert Instrument.XAU_USD in caps.supported_instruments
        assert Timeframe.H1 in caps.timeframe_capabilities


# ---------------------------------------------------------------------------
# Test: ReplayMarketDataService
# ---------------------------------------------------------------------------

class TestReplayMarketDataService:
    """Test the replay service wrapper matches MarketDataService interface."""

    @pytest.mark.asyncio
    async def test_fetch_candles_returns_response(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)
        provider.set_current_time(candles[25].timestamp)

        service = ReplayMarketDataService(provider)
        response = await service.fetch_candles(Instrument.XAU_USD, Timeframe.H1, 10)

        assert response.count == 10
        assert response.instrument == Instrument.XAU_USD
        assert response.timeframe == Timeframe.H1
        assert response.source == "replay"

    def test_service_never_has_live_streaming(self):
        provider = ReplayMarketDataProvider()
        service = ReplayMarketDataService(provider)
        assert service.live_streaming is False

    def test_service_active_source_is_replay(self):
        provider = ReplayMarketDataProvider()
        service = ReplayMarketDataService(provider)
        assert service.active_source == "replay"

    @pytest.mark.asyncio
    async def test_service_advances_clock(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)
        provider.set_current_time(candles[0].timestamp)

        service = ReplayMarketDataService(provider)
        service.set_current_time(candles[10].timestamp)

        response = await service.fetch_candles(Instrument.XAU_USD, Timeframe.H1, 100)
        assert response.count == 11  # candles 0-10

    @pytest.mark.asyncio
    async def test_start_live_stream_is_noop(self):
        provider = ReplayMarketDataProvider()
        service = ReplayMarketDataService(provider)
        # Should not raise
        await service.start_live_stream()
        await service.stop_live_stream()

    @pytest.mark.asyncio
    async def test_fetch_latest_price(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)
        provider.set_current_time(candles[20].timestamp)

        service = ReplayMarketDataService(provider)
        price = await service.fetch_latest_price(Instrument.XAU_USD)

        assert price is not None
        assert price.bid == candles[20].close

    @pytest.mark.asyncio
    async def test_fetch_latest_candle(self):
        provider = ReplayMarketDataProvider()
        candles = _make_candles(50)
        provider.load_data(Instrument.XAU_USD, Timeframe.H1, candles)
        provider.set_current_time(candles[30].timestamp)

        service = ReplayMarketDataService(provider)
        candle = await service.fetch_latest_candle(Instrument.XAU_USD, Timeframe.H1)

        assert candle is not None
        assert candle.timestamp == candles[30].timestamp


# ---------------------------------------------------------------------------
# Test: Backtest runner isolation wiring
# ---------------------------------------------------------------------------

class TestBacktestRunnerIsolation:
    """Prove the runner wires replay services, not live."""

    def test_runner_imports_replay(self):
        import app.modules.backtesting.runner as runner_mod
        assert hasattr(runner_mod, 'ReplayMarketDataProvider')
        assert hasattr(runner_mod, 'ReplayMarketDataService')

    def test_create_replay_services(self):
        from app.modules.backtesting.runner import BacktestRunner
        from app.modules.backtesting.models import HistoricalCandle

        runner = BacktestRunner()
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        candles = []
        for i in range(50):
            ts = start + timedelta(hours=i)
            candles.append(HistoricalCandle(
                timestamp=ts,
                open=2000.0, high=2001.0, low=1999.0, close=2000.0,
                volume=100.0, instrument="XAU/USD", timeframe="1h",
            ))

        provider, service = runner._create_replay_services(
            candles=candles, instrument="XAU/USD", timeframe="1h",
        )

        assert isinstance(provider, ReplayMarketDataProvider)
        assert isinstance(service, ReplayMarketDataService)

    def test_create_signal_service_with_replay(self):
        from app.modules.backtesting.runner import BacktestRunner

        runner = BacktestRunner()
        provider = ReplayMarketDataProvider()
        service = ReplayMarketDataService(provider)

        signal_svc = runner._create_signal_service(service)
        assert signal_svc._market_data is service

    def test_create_planning_service_with_replay(self):
        from app.modules.backtesting.runner import BacktestRunner

        runner = BacktestRunner()
        provider = ReplayMarketDataProvider()
        service = ReplayMarketDataService(provider)

        planning_svc = runner._create_planning_service(service)
        assert planning_svc._market_data is service
