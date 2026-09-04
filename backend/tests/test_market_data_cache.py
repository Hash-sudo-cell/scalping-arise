"""
Scalping Arise — Market Data Cache Tests
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.modules.market_data.cache import CandleCache
from app.modules.market_data.models import Instrument, NormalizedCandle, SourceType, Timeframe


def _candle(ts_hour: int = 12) -> NormalizedCandle:
    return NormalizedCandle(
        instrument=Instrument.XAU_USD,
        provider_instrument="XAU/USD",
        source_type=SourceType.SPOT,
        timeframe=Timeframe.H1,
        timestamp=datetime(2024, 1, 15, ts_hour, 0, 0, tzinfo=timezone.utc),
        open=2000.0,
        high=2010.0,
        low=1990.0,
        close=2005.0,
        volume=1000.0,
        is_closed=True,
        source="test",
    )


class TestCandleCache:
    def test_put_and_get(self) -> None:
        cache = CandleCache(enabled=True, ttl_seconds=60)
        cache.put("XAU/USD", "1h", [_candle(10), _candle(11)])
        result = cache.get("XAU/USD", "1h")
        assert len(result) == 2

    def test_get_empty(self) -> None:
        cache = CandleCache(enabled=True, ttl_seconds=60)
        result = cache.get("XAU/USD", "1h")
        assert result == []

    def test_get_with_limit(self) -> None:
        cache = CandleCache(enabled=True, ttl_seconds=60)
        cache.put("XAU/USD", "1h", [_candle(10), _candle(11), _candle(12)])
        result = cache.get("XAU/USD", "1h", limit=2)
        assert len(result) == 2

    def test_disabled_cache(self) -> None:
        cache = CandleCache(enabled=False)
        cache.put("XAU/USD", "1h", [_candle()])
        result = cache.get("XAU/USD", "1h")
        assert result == []

    def test_invalidate(self) -> None:
        cache = CandleCache(enabled=True, ttl_seconds=60)
        cache.put("XAU/USD", "1h", [_candle()])
        assert cache.total_candles == 1
        cache.invalidate("XAU/USD", "1h")
        assert cache.total_candles == 0

    def test_clear(self) -> None:
        cache = CandleCache(enabled=True, ttl_seconds=60)
        cache.put("XAU/USD", "1h", [_candle()])
        cache.put("XAU/USD", "5m", [_candle()])
        cache.clear()
        assert cache.total_candles == 0
        assert cache.entry_count == 0

    def test_update_candle(self) -> None:
        cache = CandleCache(enabled=True, ttl_seconds=60)
        cache.put("XAU/USD", "1h", [_candle(12)])
        updated = _candle(12)
        updated = updated.model_copy(update={"close": 2050.0})
        cache.update_candle(updated)
        result = cache.get("XAU/USD", "1h")
        assert result[0].close == 2050.0

    def test_max_candles_eviction(self) -> None:
        cache = CandleCache(enabled=True, ttl_seconds=60, max_candles=5)
        for i in range(10):
            cache.put("XAU/USD", f"tf_{i}", [_candle(i)])
        assert cache.total_candles <= 5

    def test_source_identity_preserved(self) -> None:
        """Cache preserves provider_instrument and source_type through put/get cycle."""
        candle = NormalizedCandle(
            instrument=Instrument.XAU_USD,
            provider_instrument="GC=F",
            source_type=SourceType.FUTURES_PROXY,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000.0, high=2010.0, low=1990.0, close=2005.0,
            volume=1000.0, is_closed=True, source="yfinance",
        )
        cache = CandleCache(enabled=True, ttl_seconds=60)
        cache.put("XAU/USD", "1h", [candle])
        result = cache.get("XAU/USD", "1h")
        assert len(result) == 1
        assert result[0].provider_instrument == "GC=F"
        assert result[0].source_type == SourceType.FUTURES_PROXY
