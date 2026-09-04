"""
Scalping Arise — Failover Logic Tests
"""

from __future__ import annotations

from app.modules.market_data.config import MarketDataSettings
from app.modules.market_data.failover import FailoverManager
from app.modules.market_data.models import ProviderHealth, ProviderHealthStatus, SourceType


def _make_settings() -> MarketDataSettings:
    return MarketDataSettings()


def _healthy(name: str = "test") -> ProviderHealth:
    return ProviderHealth(provider_name=name, status=ProviderHealthStatus.HEALTHY, message="OK")


def _unavailable(name: str = "test", msg: str = "down") -> ProviderHealth:
    return ProviderHealth(provider_name=name, status=ProviderHealthStatus.UNAVAILABLE, message=msg)


def _degraded(name: str = "test") -> ProviderHealth:
    return ProviderHealth(provider_name=name, status=ProviderHealthStatus.DEGRADED, message="slow")


class TestFailoverManager:
    def test_default_state_uses_primary(self) -> None:
        fm = FailoverManager(_make_settings())
        assert fm.should_use_fallback() is False

    def test_primary_healthy_stays_primary(self) -> None:
        fm = FailoverManager(_make_settings())
        fm.update_primary_health(_healthy())
        assert fm.should_use_fallback() is False

    def test_primary_unavailable_triggers_fallback(self) -> None:
        fm = FailoverManager(_make_settings())
        for _ in range(3):
            fm.update_primary_health(_unavailable())
        assert fm.should_use_fallback() is True

    def test_primary_recovery_resets_count(self) -> None:
        fm = FailoverManager(_make_settings())
        fm.update_primary_health(_unavailable())
        fm.update_primary_health(_unavailable())
        fm.update_primary_health(_healthy())
        assert fm._consecutive_primary_failures == 0
        assert fm.should_use_fallback() is False

    def test_fallback_healthy(self) -> None:
        fm = FailoverManager(_make_settings())
        fm.update_fallback_health(_healthy("fallback"))
        assert fm.fallback_health is not None
        assert fm.fallback_health.status == ProviderHealthStatus.HEALTHY

    def test_consistency_validation_no_data(self) -> None:
        fm = FailoverManager(_make_settings())
        ok, msg = fm.validate_fallback_consistency([], [])
        assert ok is False

    def test_consistency_validation_consistent(self) -> None:
        from app.modules.market_data.models import Instrument, NormalizedCandle, Timeframe
        from datetime import datetime, timezone

        fm = FailoverManager(_make_settings())
        c1 = NormalizedCandle(
            instrument=Instrument.XAU_USD, provider_instrument="XAU/USD", source_type=SourceType.SPOT,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000, high=2010, low=1990, close=2005, is_closed=True, source="primary",
        )
        c2 = NormalizedCandle(
            instrument=Instrument.XAU_USD, provider_instrument="XAU/USD", source_type=SourceType.SPOT,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000, high=2010, low=1990, close=2005.5, is_closed=True, source="fallback",
        )
        ok, msg = fm.validate_fallback_consistency([c1], [c2], tolerance_pct=0.5)
        assert ok is True

    def test_consistency_validation_price_divergence(self) -> None:
        from app.modules.market_data.models import Instrument, NormalizedCandle, Timeframe
        from datetime import datetime, timezone

        fm = FailoverManager(_make_settings())
        c1 = NormalizedCandle(
            instrument=Instrument.XAU_USD, provider_instrument="XAU/USD", source_type=SourceType.SPOT,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000, high=2010, low=1990, close=2000, is_closed=True, source="primary",
        )
        c2 = NormalizedCandle(
            instrument=Instrument.XAU_USD, provider_instrument="XAU/USD", source_type=SourceType.SPOT,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000, high=2010, low=1990, close=2020, is_closed=True, source="fallback",
        )
        ok, msg = fm.validate_fallback_consistency([c1], [c2], tolerance_pct=0.5)
        assert ok is False
        assert "divergence" in msg.lower()

    def test_consistency_spot_vs_futures_skips_price_check(self) -> None:
        """When source types differ, price comparison is skipped."""
        from app.modules.market_data.models import Instrument, NormalizedCandle, Timeframe
        from datetime import datetime, timezone

        fm = FailoverManager(_make_settings())
        # SPOT primary
        c1 = NormalizedCandle(
            instrument=Instrument.XAU_USD, provider_instrument="XAU/USD", source_type=SourceType.SPOT,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000, high=2010, low=1990, close=2000, is_closed=True, source="primary",
        )
        # FUTURES_PROXY fallback — different price is expected
        c2 = NormalizedCandle(
            instrument=Instrument.XAU_USD, provider_instrument="GC=F", source_type=SourceType.FUTURES_PROXY,
            timeframe=Timeframe.H1,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            open=2000, high=2010, low=1990, close=2050, is_closed=True, source="fallback",
        )
        ok, msg = fm.validate_fallback_consistency([c1], [c2], tolerance_pct=0.5)
        assert ok is True
        assert "source types differ" in msg.lower()
