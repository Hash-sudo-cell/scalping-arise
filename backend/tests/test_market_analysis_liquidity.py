"""
Scalping Arise — Liquidity Analysis Tests

Comprehensive deterministic tests for the Liquidity Analysis Layer.
No live API calls, no timing dependencies, no flaky tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import application
from app.modules.market_analysis.config import MarketAnalysisSettings
from app.modules.market_analysis.liquidity import (
    analyze_liquidity,
    calculate_proximity,
    classify_post_sweep_reaction,
    cluster_equal_levels,
    detect_swing_liquidity,
    update_pool_status,
    _classify_strength,
    _cluster_swings,
    _generate_pool_id,
)
from app.modules.market_analysis.models import (
    AnalysisStatus,
    LiquidityAnalysisResult,
    LiquidityPool,
    LiquidityPoolStatus,
    LiquidityPoolType,
    LiquiditySide,
    LiquidityStrength,
    LiquiditySweep,
    LiquiditySweepMode,
    PostSweepReaction,
    SwingPoint,
    SwingType,
)
from app.modules.market_data.models import (
    Instrument,
    NormalizedCandle,
    SourceType,
    Timeframe,
)

client = TestClient(app=application)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _swing(
    index: int,
    price: float,
    swing_type: SwingType,
    confirmed: bool = True,
    hours_offset: int = 0,
) -> SwingPoint:
    return SwingPoint(
        index=index,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hours_offset),
        price=price,
        swing_type=swing_type,
        confirmed=confirmed,
        timeframe="1h",
    )


def _settings(**overrides) -> MarketAnalysisSettings:
    defaults = {
        "liquidity_equal_level_tolerance_pct": 0.05,
        "liquidity_min_touches": 2,
        "liquidity_sweep_mode": "wick",
        "liquidity_min_sweep_distance_pct": 0.0,
        "liquidity_max_active_pools": 20,
        "liquidity_max_history_depth": 50,
    }
    defaults.update(overrides)
    return MarketAnalysisSettings(**defaults)


# ---------------------------------------------------------------------------
# Test: Swing Liquidity Detection
# ---------------------------------------------------------------------------

class TestSwingLiquidity:
    def test_swing_high_creates_buy_side(self) -> None:
        """A confirmed swing high should produce a BUY_SIDE pool."""
        swings = [_swing(5, 110.0, SwingType.SWING_HIGH)]
        pools = detect_swing_liquidity(swings, "1h")
        assert len(pools) == 1
        assert pools[0].side == LiquiditySide.BUY_SIDE
        assert pools[0].pool_type == LiquidityPoolType.SWING_HIGH
        assert pools[0].price_level == 110.0
        assert pools[0].status == LiquidityPoolStatus.ACTIVE

    def test_swing_low_creates_sell_side(self) -> None:
        """A confirmed swing low should produce a SELL_SIDE pool."""
        swings = [_swing(5, 90.0, SwingType.SWING_LOW)]
        pools = detect_swing_liquidity(swings, "1h")
        assert len(pools) == 1
        assert pools[0].side == LiquiditySide.SELL_SIDE
        assert pools[0].pool_type == LiquidityPoolType.SWING_LOW
        assert pools[0].price_level == 90.0

    def test_only_confirmed_swings_used(self) -> None:
        """Unconfirmed swings should not produce pools."""
        swings = [
            _swing(5, 110.0, SwingType.SWING_HIGH, confirmed=True),
            _swing(10, 115.0, SwingType.SWING_HIGH, confirmed=False),
        ]
        pools = detect_swing_liquidity(swings, "1h")
        assert len(pools) == 1
        assert pools[0].price_level == 110.0

    def test_no_swings_produces_empty(self) -> None:
        """Empty swing list should produce no pools."""
        pools = detect_swing_liquidity([], "1h")
        assert len(pools) == 0

    def test_mixed_swings(self) -> None:
        """Mix of swing highs and lows should produce both pool types."""
        swings = [
            _swing(5, 110.0, SwingType.SWING_HIGH),
            _swing(10, 90.0, SwingType.SWING_LOW),
            _swing(15, 112.0, SwingType.SWING_HIGH),
        ]
        pools = detect_swing_liquidity(swings, "1h")
        assert len(pools) == 3
        buy_pools = [p for p in pools if p.side == LiquiditySide.BUY_SIDE]
        sell_pools = [p for p in pools if p.side == LiquiditySide.SELL_SIDE]
        assert len(buy_pools) == 2
        assert len(sell_pools) == 1

    def test_pool_boundaries_equal_to_price(self) -> None:
        """Individual swing pools should have lower_bound == upper_bound == price."""
        swings = [_swing(5, 110.0, SwingType.SWING_HIGH)]
        pools = detect_swing_liquidity(swings, "1h")
        assert pools[0].lower_bound == 110.0
        assert pools[0].upper_bound == 110.0

    def test_source_swings_populated(self) -> None:
        """Pool should reference the source swing index."""
        swings = [_swing(7, 105.0, SwingType.SWING_LOW)]
        pools = detect_swing_liquidity(swings, "1h")
        assert pools[0].source_swings == [7]

    def test_touch_count_is_one(self) -> None:
        """Individual swing pool should have touch_count of 1."""
        swings = [_swing(5, 110.0, SwingType.SWING_HIGH)]
        pools = detect_swing_liquidity(swings, "1h")
        assert pools[0].touch_count == 1


# ---------------------------------------------------------------------------
# Test: Equal Highs / Equal Lows Clustering
# ---------------------------------------------------------------------------

class TestEqualLevels:
    def test_two_qualifying_highs_create_pool(self) -> None:
        """Two swing highs within tolerance should create an EQUAL_HIGHS pool."""
        swings = [
            _swing(5, 110.0, SwingType.SWING_HIGH),
            _swing(10, 110.05, SwingType.SWING_HIGH),
        ]
        pools = cluster_equal_levels(swings, tolerance_pct=0.1, min_touches=2, timeframe="1h")
        assert len(pools) == 1
        assert pools[0].pool_type == LiquidityPoolType.EQUAL_HIGHS
        assert pools[0].side == LiquiditySide.BUY_SIDE
        assert pools[0].touch_count == 2
        assert pools[0].status == LiquidityPoolStatus.ACTIVE

    def test_highs_outside_tolerance_do_not_cluster(self) -> None:
        """Swing highs outside tolerance should not cluster together."""
        swings = [
            _swing(5, 100.0, SwingType.SWING_HIGH),
            _swing(10, 110.0, SwingType.SWING_HIGH),  # 10% apart
        ]
        pools = cluster_equal_levels(swings, tolerance_pct=0.1, min_touches=2, timeframe="1h")
        assert len(pools) == 0  # Each alone doesn't meet min_touches=2

    def test_boundary_tolerance_included(self) -> None:
        """Swings at exactly the tolerance boundary should be included."""
        # Price 100.0, tolerance 0.1% -> tolerance = 0.1
        # Price 100.09 is within tolerance of center 100.045
        swings = [
            _swing(5, 100.0, SwingType.SWING_HIGH),
            _swing(10, 100.09, SwingType.SWING_HIGH),
        ]
        pools = cluster_equal_levels(swings, tolerance_pct=0.1, min_touches=2, timeframe="1h")
        assert len(pools) == 1

    def test_minimum_touches_enforced(self) -> None:
        """Clusters with fewer than min_touches should be filtered."""
        swings = [
            _swing(5, 110.0, SwingType.SWING_HIGH),
        ]
        pools = cluster_equal_levels(swings, tolerance_pct=0.1, min_touches=2, timeframe="1h")
        assert len(pools) == 0

    def test_equal_lows_create_sell_side(self) -> None:
        """Two swing lows within tolerance should create an EQUAL_LOWS pool."""
        swings = [
            _swing(5, 90.0, SwingType.SWING_LOW),
            _swing(10, 90.02, SwingType.SWING_LOW),
        ]
        pools = cluster_equal_levels(swings, tolerance_pct=0.1, min_touches=2, timeframe="1h")
        assert len(pools) == 1
        assert pools[0].pool_type == LiquidityPoolType.EQUAL_LOWS
        assert pools[0].side == LiquiditySide.SELL_SIDE
        assert pools[0].touch_count == 2

    def test_three_qualifying_highs(self) -> None:
        """Three swing highs within tolerance should create one pool with 3 touches."""
        swings = [
            _swing(5, 110.0, SwingType.SWING_HIGH),
            _swing(10, 110.03, SwingType.SWING_HIGH),
            _swing(15, 110.06, SwingType.SWING_HIGH),
        ]
        pools = cluster_equal_levels(swings, tolerance_pct=0.1, min_touches=2, timeframe="1h")
        assert len(pools) == 1
        assert pools[0].touch_count == 3

    def test_no_swings_produces_empty(self) -> None:
        """No swings should produce no clusters."""
        pools = cluster_equal_levels([], tolerance_pct=0.1, min_touches=2, timeframe="1h")
        assert len(pools) == 0

    def test_only_confirmed_used(self) -> None:
        """Unconfirmed swings should be excluded from clustering."""
        swings = [
            _swing(5, 110.0, SwingType.SWING_HIGH, confirmed=True),
            _swing(10, 110.01, SwingType.SWING_HIGH, confirmed=False),
        ]
        pools = cluster_equal_levels(swings, tolerance_pct=0.1, min_touches=2, timeframe="1h")
        assert len(pools) == 0

    def test_pool_price_is_average(self) -> None:
        """Equal-level pool price_level should be the average of cluster swings."""
        swings = [
            _swing(5, 100.0, SwingType.SWING_HIGH),
            _swing(10, 100.1, SwingType.SWING_HIGH),
        ]
        pools = cluster_equal_levels(swings, tolerance_pct=0.2, min_touches=2, timeframe="1h")
        assert len(pools) == 1
        assert abs(pools[0].price_level - 100.05) < 0.001

    def test_pool_boundaries_span_cluster(self) -> None:
        """Equal-level pool boundaries should span min to max of cluster."""
        swings = [
            _swing(5, 100.0, SwingType.SWING_HIGH),
            _swing(10, 100.1, SwingType.SWING_HIGH),
            _swing(15, 100.05, SwingType.SWING_HIGH),
        ]
        pools = cluster_equal_levels(swings, tolerance_pct=0.2, min_touches=2, timeframe="1h")
        assert pools[0].lower_bound == 100.0
        assert pools[0].upper_bound == 100.1


# ---------------------------------------------------------------------------
# Test: Pool Strength Classification
# ---------------------------------------------------------------------------

class TestPoolStrength:
    def test_single_touch_low(self) -> None:
        """Touch count of 1 should classify as LOW strength."""
        assert _classify_strength(1) == LiquidityStrength.LOW

    def test_two_touches_medium(self) -> None:
        """Touch count of 2 should classify as MEDIUM strength."""
        assert _classify_strength(2) == LiquidityStrength.MEDIUM

    def test_three_touches_high(self) -> None:
        """Touch count of 3 should classify as HIGH strength."""
        assert _classify_strength(3) == LiquidityStrength.HIGH

    def test_four_touches_high(self) -> None:
        """Touch count of 4+ should classify as HIGH strength."""
        assert _classify_strength(5) == LiquidityStrength.HIGH

    def test_no_future_information(self) -> None:
        """Strength classification uses only touch count, no price or time data."""
        # Same touch count always produces same strength regardless of inputs
        assert _classify_strength(2) == LiquidityStrength.MEDIUM
        assert _classify_strength(2) == LiquidityStrength.MEDIUM


# ---------------------------------------------------------------------------
# Test: Pool Status Lifecycle
# ---------------------------------------------------------------------------

class TestPoolStatus:
    def test_new_pool_is_active(self) -> None:
        """Newly created pool should have ACTIVE status."""
        pool = LiquidityPool(
            pool_id="test123",
            side=LiquiditySide.BUY_SIDE,
            pool_type=LiquidityPoolType.SWING_HIGH,
            price_level=110.0,
            lower_bound=110.0,
            upper_bound=110.0,
            touch_count=1,
            timeframe="1h",
        )
        assert pool.status == LiquidityPoolStatus.ACTIVE

    def test_wick_sweep_buy_side(self) -> None:
        """WICK mode: a candle high above BUY_SIDE pool should sweep it."""
        pool = LiquidityPool(
            pool_id="test_buy",
            side=LiquiditySide.BUY_SIDE,
            pool_type=LiquidityPoolType.SWING_HIGH,
            price_level=110.0,
            lower_bound=110.0,
            upper_bound=110.0,
            touch_count=1,
            timeframe="1h",
        )
        # Candle with high=115.0 > 110.0
        candles = [_candle(0, high=115.0, low=108.0, close=112.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.WICK, 0.0)
        assert sweep is not None
        assert pool.status == LiquidityPoolStatus.SWEPT
        assert sweep.sweep_price == 115.0
        assert sweep.side == LiquiditySide.BUY_SIDE

    def test_wick_sweep_sell_side(self) -> None:
        """WICK mode: a candle low below SELL_SIDE pool should sweep it."""
        pool = LiquidityPool(
            pool_id="test_sell",
            side=LiquiditySide.SELL_SIDE,
            pool_type=LiquidityPoolType.SWING_LOW,
            price_level=90.0,
            lower_bound=90.0,
            upper_bound=90.0,
            touch_count=1,
            timeframe="1h",
        )
        candles = [_candle(0, high=92.0, low=85.0, close=88.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.WICK, 0.0)
        assert sweep is not None
        assert pool.status == LiquidityPoolStatus.SWEPT
        assert sweep.sweep_price == 85.0

    def test_close_sweep_buy_side(self) -> None:
        """CLOSE mode: candle close above BUY_SIDE pool should sweep it."""
        pool = LiquidityPool(
            pool_id="test_close_buy",
            side=LiquiditySide.BUY_SIDE,
            pool_type=LiquidityPoolType.SWING_HIGH,
            price_level=110.0,
            lower_bound=110.0,
            upper_bound=110.0,
            touch_count=1,
            timeframe="1h",
        )
        # Close=112.0 > 110.0
        candles = [_candle(0, high=115.0, low=108.0, close=112.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.CLOSE, 0.0)
        assert sweep is not None
        assert sweep.sweep_price == 112.0

    def test_close_sweep_sell_side(self) -> None:
        """CLOSE mode: candle close below SELL_SIDE pool should sweep it."""
        pool = LiquidityPool(
            pool_id="test_close_sell",
            side=LiquiditySide.SELL_SIDE,
            pool_type=LiquidityPoolType.SWING_LOW,
            price_level=90.0,
            lower_bound=90.0,
            upper_bound=90.0,
            touch_count=1,
            timeframe="1h",
        )
        candles = [_candle(0, high=92.0, low=85.0, close=88.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.CLOSE, 0.0)
        assert sweep is not None
        assert sweep.sweep_price == 88.0

    def test_no_sweep_when_price_below_buy_side(self) -> None:
        """Price below BUY_SIDE pool should not sweep it."""
        pool = LiquidityPool(
            pool_id="test_no",
            side=LiquiditySide.BUY_SIDE,
            pool_type=LiquidityPoolType.SWING_HIGH,
            price_level=110.0,
            lower_bound=110.0,
            upper_bound=110.0,
            touch_count=1,
            timeframe="1h",
        )
        candles = [_candle(0, high=109.0, low=105.0, close=107.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.WICK, 0.0)
        assert sweep is None
        assert pool.status == LiquidityPoolStatus.ACTIVE

    def test_no_sweep_when_price_above_sell_side(self) -> None:
        """Price above SELL_SIDE pool should not sweep it."""
        pool = LiquidityPool(
            pool_id="test_no2",
            side=LiquiditySide.SELL_SIDE,
            pool_type=LiquidityPoolType.SWING_LOW,
            price_level=90.0,
            lower_bound=90.0,
            upper_bound=90.0,
            touch_count=1,
            timeframe="1h",
        )
        candles = [_candle(0, high=95.0, low=91.0, close=93.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.WICK, 0.0)
        assert sweep is None
        assert pool.status == LiquidityPoolStatus.ACTIVE

    def test_already_swept_pool_returns_none(self) -> None:
        """A pool that is already SWEPT should return None."""
        pool = LiquidityPool(
            pool_id="test_swept",
            side=LiquiditySide.BUY_SIDE,
            pool_type=LiquidityPoolType.SWING_HIGH,
            price_level=110.0,
            lower_bound=110.0,
            upper_bound=110.0,
            touch_count=1,
            status=LiquidityPoolStatus.SWEPT,
            timeframe="1h",
        )
        candles = [_candle(0, high=120.0, low=105.0, close=115.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.WICK, 0.0)
        assert sweep is None

    def test_wick_only_no_close_sweep_in_close_mode(self) -> None:
        """In CLOSE mode, a wick-only touch should not sweep."""
        pool = LiquidityPool(
            pool_id="test_close_only",
            side=LiquiditySide.BUY_SIDE,
            pool_type=LiquidityPoolType.SWING_HIGH,
            price_level=110.0,
            lower_bound=110.0,
            upper_bound=110.0,
            touch_count=1,
            timeframe="1h",
        )
        # High=112.0 > 110.0 but Close=108.0 < 110.0
        candles = [_candle(0, high=112.0, low=105.0, close=108.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.CLOSE, 0.0)
        assert sweep is None
        assert pool.status == LiquidityPoolStatus.ACTIVE

    def test_exact_boundary_buy_side_sweep(self) -> None:
        """BUY_SIDE: wick at exactly the upper_bound should NOT sweep (strict >)."""
        pool = LiquidityPool(
            pool_id="test_exact",
            side=LiquiditySide.BUY_SIDE,
            pool_type=LiquidityPoolType.SWING_HIGH,
            price_level=110.0,
            lower_bound=110.0,
            upper_bound=110.0,
            touch_count=1,
            timeframe="1h",
        )
        candles = [_candle(0, high=110.0, low=105.0, close=108.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.WICK, 0.0)
        assert sweep is None

    def test_exact_boundary_sell_side_sweep(self) -> None:
        """SELL_SIDE: wick at exactly the lower_bound should NOT sweep (strict <)."""
        pool = LiquidityPool(
            pool_id="test_exact_sell",
            side=LiquiditySide.SELL_SIDE,
            pool_type=LiquidityPoolType.SWING_LOW,
            price_level=90.0,
            lower_bound=90.0,
            upper_bound=90.0,
            touch_count=1,
            timeframe="1h",
        )
        candles = [_candle(0, high=95.0, low=90.0, close=93.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.WICK, 0.0)
        assert sweep is None

    def test_min_sweep_distance_pct(self) -> None:
        """With min_sweep_distance_pct > 0, price must exceed level by that %."""
        pool = LiquidityPool(
            pool_id="test_dist",
            side=LiquiditySide.BUY_SIDE,
            pool_type=LiquidityPoolType.SWING_HIGH,
            price_level=100.0,
            lower_bound=100.0,
            upper_bound=100.0,
            touch_count=1,
            timeframe="1h",
        )
        # 100.5 is only 0.5% above 100.0 — should not sweep with 1.0% min distance
        candles = [_candle(0, high=100.5, low=95.0, close=98.0)]
        sweep = update_pool_status(pool, candles, LiquiditySweepMode.WICK, 1.0)
        assert sweep is None

        # 102.0 is 2.0% above 100.0 — should sweep with 1.0% min distance
        candles2 = [_candle(0, high=102.0, low=95.0, close=98.0)]
        sweep2 = update_pool_status(pool, candles2, LiquiditySweepMode.WICK, 1.0)
        assert sweep2 is not None


# ---------------------------------------------------------------------------
# Test: Post-Sweep Reaction
# ---------------------------------------------------------------------------

class TestPostSweepReaction:
    def test_rejection_buy_side(self) -> None:
        """BUY_SIDE sweep followed by close below pool -> REJECTION."""
        sweep = LiquiditySweep(
            sweep_id="s1",
            pool_id="p1",
            side=LiquiditySide.BUY_SIDE,
            pool_price_level=110.0,
            sweep_timestamp=datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
            sweep_mode=LiquiditySweepMode.WICK,
            sweep_price=115.0,
            candle_close=112.0,
            timeframe="1h",
        )
        # Candle at hour 5 matches sweep_timestamp, hour 6 is the reaction candle
        candles = [
            _candle(5, high=115.0, low=108.0, close=112.0),
            _candle(6, high=113.0, low=107.0, close=108.0),  # Close < 110.0
        ]
        result = classify_post_sweep_reaction(sweep, candles, max_history_depth=10)
        assert result.reaction == PostSweepReaction.REJECTION

    def test_acceptance_buy_side(self) -> None:
        """BUY_SIDE sweep followed by close above pool -> ACCEPTANCE."""
        sweep = LiquiditySweep(
            sweep_id="s2",
            pool_id="p2",
            side=LiquiditySide.BUY_SIDE,
            pool_price_level=110.0,
            sweep_timestamp=datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
            sweep_mode=LiquiditySweepMode.WICK,
            sweep_price=115.0,
            candle_close=112.0,
            timeframe="1h",
        )
        candles = [
            _candle(5, high=115.0, low=108.0, close=112.0),
            _candle(6, high=118.0, low=111.0, close=116.0),  # Close > 110.0
        ]
        result = classify_post_sweep_reaction(sweep, candles, max_history_depth=10)
        assert result.reaction == PostSweepReaction.ACCEPTANCE

    def test_rejection_sell_side(self) -> None:
        """SELL_SIDE sweep followed by close above pool -> REJECTION."""
        sweep = LiquiditySweep(
            sweep_id="s3",
            pool_id="p3",
            side=LiquiditySide.SELL_SIDE,
            pool_price_level=90.0,
            sweep_timestamp=datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
            sweep_mode=LiquiditySweepMode.WICK,
            sweep_price=85.0,
            candle_close=88.0,
            timeframe="1h",
        )
        candles = [
            _candle(5, high=92.0, low=85.0, close=88.0),
            _candle(6, high=93.0, low=89.0, close=92.0),  # Close > 90.0
        ]
        result = classify_post_sweep_reaction(sweep, candles, max_history_depth=10)
        assert result.reaction == PostSweepReaction.REJECTION

    def test_acceptance_sell_side(self) -> None:
        """SELL_SIDE sweep followed by close below pool -> ACCEPTANCE."""
        sweep = LiquiditySweep(
            sweep_id="s4",
            pool_id="p4",
            side=LiquiditySide.SELL_SIDE,
            pool_price_level=90.0,
            sweep_timestamp=datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
            sweep_mode=LiquiditySweepMode.WICK,
            sweep_price=85.0,
            candle_close=88.0,
            timeframe="1h",
        )
        candles = [
            _candle(5, high=92.0, low=85.0, close=88.0),
            _candle(6, high=89.0, low=84.0, close=86.0),  # Close < 90.0
        ]
        result = classify_post_sweep_reaction(sweep, candles, max_history_depth=10)
        assert result.reaction == PostSweepReaction.ACCEPTANCE

    def test_unavailable_no_next_candle(self) -> None:
        """No subsequent candle should produce UNAVAILABLE."""
        sweep = LiquiditySweep(
            sweep_id="s5",
            pool_id="p5",
            side=LiquiditySide.BUY_SIDE,
            pool_price_level=110.0,
            sweep_timestamp=datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
            sweep_mode=LiquiditySweepMode.WICK,
            sweep_price=115.0,
            candle_close=112.0,
            timeframe="1h",
        )
        candles = [
            _candle(0, high=115.0, low=108.0, close=112.0),
        ]
        result = classify_post_sweep_reaction(sweep, candles, max_history_depth=10)
        assert result.reaction == PostSweepReaction.UNAVAILABLE

    def test_already_classified_returns_unchanged(self) -> None:
        """A sweep that already has a classified reaction should not be reclassified."""
        sweep = LiquiditySweep(
            sweep_id="s6",
            pool_id="p6",
            side=LiquiditySide.BUY_SIDE,
            pool_price_level=110.0,
            sweep_timestamp=datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
            sweep_mode=LiquiditySweepMode.WICK,
            sweep_price=115.0,
            candle_close=112.0,
            reaction=PostSweepReaction.REJECTION,
            timeframe="1h",
        )
        candles = [
            _candle(0, high=115.0, low=108.0, close=112.0),
            _candle(1, high=118.0, low=111.0, close=116.0),  # Would be ACCEPTANCE
        ]
        result = classify_post_sweep_reaction(sweep, candles, max_history_depth=10)
        assert result.reaction == PostSweepReaction.REJECTION  # Unchanged

    def test_reaction_timestamp_set(self) -> None:
        """After classification, reaction_timestamp should be set."""
        sweep = LiquiditySweep(
            sweep_id="s7",
            pool_id="p7",
            side=LiquiditySide.BUY_SIDE,
            pool_price_level=110.0,
            sweep_timestamp=datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
            sweep_mode=LiquiditySweepMode.WICK,
            sweep_price=115.0,
            candle_close=112.0,
            timeframe="1h",
        )
        candles = [
            _candle(5, high=115.0, low=108.0, close=112.0),
            _candle(6, high=113.0, low=107.0, close=108.0),
        ]
        result = classify_post_sweep_reaction(sweep, candles, max_history_depth=10)
        assert result.reaction_timestamp is not None


# ---------------------------------------------------------------------------
# Test: Proximity Calculation
# ---------------------------------------------------------------------------

class TestProximity:
    def test_nearest_buy_side_selected(self) -> None:
        """Nearest active BUY_SIDE pool should be selected."""
        pools = [
            LiquidityPool(
                pool_id="far", side=LiquiditySide.BUY_SIDE,
                pool_type=LiquidityPoolType.SWING_HIGH,
                price_level=120.0, lower_bound=120.0, upper_bound=120.0,
                touch_count=1, timeframe="1h",
            ),
            LiquidityPool(
                pool_id="near", side=LiquiditySide.BUY_SIDE,
                pool_type=LiquidityPoolType.SWING_HIGH,
                price_level=105.0, lower_bound=105.0, upper_bound=105.0,
                touch_count=1, timeframe="1h",
            ),
        ]
        nb, ns, db, ds, bp, sp = calculate_proximity(pools, current_price=103.0)
        assert nb is not None
        assert nb.pool_id == "near"
        assert abs(db - 2.0) < 0.001

    def test_nearest_sell_side_selected(self) -> None:
        """Nearest active SELL_SIDE pool should be selected."""
        pools = [
            LiquidityPool(
                pool_id="far", side=LiquiditySide.SELL_SIDE,
                pool_type=LiquidityPoolType.SWING_LOW,
                price_level=80.0, lower_bound=80.0, upper_bound=80.0,
                touch_count=1, timeframe="1h",
            ),
            LiquidityPool(
                pool_id="near", side=LiquiditySide.SELL_SIDE,
                pool_type=LiquidityPoolType.SWING_LOW,
                price_level=98.0, lower_bound=98.0, upper_bound=98.0,
                touch_count=1, timeframe="1h",
            ),
        ]
        nb, ns, db, ds, bp, sp = calculate_proximity(pools, current_price=100.0)
        assert ns is not None
        assert ns.pool_id == "near"
        assert abs(ds - 2.0) < 0.001

    def test_no_active_pools(self) -> None:
        """No active pools should return None for all proximity values."""
        pools = [
            LiquidityPool(
                pool_id="swept1", side=LiquiditySide.BUY_SIDE,
                pool_type=LiquidityPoolType.SWING_HIGH,
                price_level=120.0, lower_bound=120.0, upper_bound=120.0,
                touch_count=1, status=LiquidityPoolStatus.SWEPT, timeframe="1h",
            ),
        ]
        nb, ns, db, ds, bp, sp = calculate_proximity(pools, current_price=100.0)
        assert nb is None
        assert ns is None
        assert db is None
        assert ds is None

    def test_percentage_distance_calculation(self) -> None:
        """Percentage distance should be correctly calculated."""
        pools = [
            LiquidityPool(
                pool_id="p1", side=LiquiditySide.BUY_SIDE,
                pool_type=LiquidityPoolType.SWING_HIGH,
                price_level=105.0, lower_bound=105.0, upper_bound=105.0,
                touch_count=1, timeframe="1h",
            ),
        ]
        nb, ns, db, ds, bp, sp = calculate_proximity(pools, current_price=100.0)
        assert bp is not None
        assert abs(bp - 5.0) < 0.001  # 5% distance

    def test_empty_pools(self) -> None:
        """Empty pool list should return None values."""
        nb, ns, db, ds, bp, sp = calculate_proximity([], current_price=100.0)
        assert nb is None
        assert ns is None
        assert db is None
        assert ds is None
        assert bp is None
        assert sp is None


# ---------------------------------------------------------------------------
# Test: Full Liquidity Analysis Pipeline
# ---------------------------------------------------------------------------

class TestFullAnalysis:
    def test_returns_analysis_result(self) -> None:
        """analyze_liquidity should return a LiquidityAnalysisResult."""
        swings = [
            _swing(5, 110.0, SwingType.SWING_HIGH),
            _swing(10, 90.0, SwingType.SWING_LOW),
        ]
        candles = [_candle(i, high=100 + i, low=90 + i, close=95 + i) for i in range(20)]
        result = analyze_liquidity(swings, candles, current_price=100.0)
        assert isinstance(result, LiquidityAnalysisResult)
        assert result.status == AnalysisStatus.AVAILABLE

    def test_no_swings_unavailable(self) -> None:
        """No swings should produce UNAVAILABLE status."""
        candles = [_candle(i, high=100 + i, low=90 + i, close=95 + i) for i in range(20)]
        result = analyze_liquidity([], candles, current_price=100.0)
        assert result.status == AnalysisStatus.UNAVAILABLE
        assert "No confirmed swings" in result.reason

    def test_pools_populated(self) -> None:
        """Available swings should produce pools."""
        swings = [
            _swing(5, 110.0, SwingType.SWING_HIGH),
            _swing(10, 90.0, SwingType.SWING_LOW),
            _swing(15, 112.0, SwingType.SWING_HIGH),
        ]
        # Candles must not sweep the pools: highs < 110, lows > 90
        candles = [_candle(i, high=105.0, low=95.0, close=100.0) for i in range(20)]
        result = analyze_liquidity(swings, candles, current_price=100.0)
        assert len(result.pools) == 3
        assert result.active_pool_count == 3

    def test_sweep_detection_in_pipeline(self) -> None:
        """Pools should be swept when candle data triggers it."""
        swings = [_swing(5, 100.0, SwingType.SWING_HIGH)]
        # Candle with high > 100.0
        candles = [_candle(0, high=105.0, low=95.0, close=102.0)]
        result = analyze_liquidity(swings, candles, current_price=100.0)
        assert result.swept_pool_count == 1
        assert len(result.sweeps) == 1

    def test_proximity_populated(self) -> None:
        """Proximity should be calculated when pools exist."""
        swings = [
            _swing(5, 110.0, SwingType.SWING_HIGH),
            _swing(10, 90.0, SwingType.SWING_LOW),
        ]
        # Candles must not sweep pools: highs < 110, lows > 90
        candles = [_candle(i, high=105.0, low=95.0, close=100.0) for i in range(20)]
        result = analyze_liquidity(swings, candles, current_price=105.0)
        assert result.nearest_buy_side_pool is not None
        assert result.nearest_sell_side_pool is not None
        assert result.distance_to_buy_side is not None
        assert result.distance_to_sell_side is not None

    def test_max_active_pools_trimmed(self) -> None:
        """Excess pools beyond max should be INVALIDATED."""
        swings = [_swing(i, 100.0 + i * 0.01, SwingType.SWING_HIGH) for i in range(25)]
        # Candles must not sweep pools: highs stay below 100.24
        candles = [_candle(i, high=99.0, low=95.0, close=97.0) for i in range(30)]
        settings = _settings(liquidity_max_active_pools=5)
        result = analyze_liquidity(swings, candles, current_price=97.0, settings=settings)
        active = sum(1 for p in result.pools if p.status == LiquidityPoolStatus.ACTIVE)
        invalidated = sum(1 for p in result.pools if p.status == LiquidityPoolStatus.INVALIDATED)
        assert active <= 5
        assert invalidated > 0

    def test_source_metadata_preserved(self) -> None:
        """Pools should preserve timeframe from input."""
        swings = [_swing(5, 110.0, SwingType.SWING_HIGH)]
        candles = [_candle(i, high=100 + i, low=90 + i, close=95 + i) for i in range(20)]
        result = analyze_liquidity(swings, candles, current_price=100.0)
        assert all(p.timeframe == "1h" for p in result.pools)


# ---------------------------------------------------------------------------
# Test: API Integration
# ---------------------------------------------------------------------------

class TestLiquidityAPI:
    def test_capabilities_includes_liquidity(self) -> None:
        """Capabilities endpoint should include liquidity_analysis."""
        response = client.get("/api/v1/market-analysis/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert "liquidity_analysis" in data["supported_analyses"]

    def test_capabilities_has_liquidity_config(self) -> None:
        """Capabilities should include liquidity configuration."""
        response = client.get("/api/v1/market-analysis/capabilities")
        data = response.json()
        assert "liquidity_equal_level_tolerance_pct" in data["configuration"]
        assert "liquidity_min_touches" in data["configuration"]
        assert "liquidity_sweep_mode" in data["configuration"]
        assert "liquidity_max_active_pools" in data["configuration"]

    def test_analysis_response_includes_liquidity(self) -> None:
        """Main analysis response should include a liquidity section."""
        response = client.get(
            "/api/v1/market-analysis",
            params={"instrument": "XAU/USD", "timeframe": "1h", "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        # If analysis is available, liquidity should be present
        if data["status"] == "available":
            assert "liquidity" in data
            liq = data["liquidity"]
            assert "status" in liq
            assert "active_pool_count" in liq
            assert "swept_pool_count" in liq
            assert "pool_count" in liq
            assert "sweep_count" in liq

    def test_existing_fields_preserved(self) -> None:
        """Existing Phase 3 fields should remain in the response."""
        response = client.get(
            "/api/v1/market-analysis",
            params={"instrument": "XAU/USD", "timeframe": "1h", "limit": 200},
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "reason" in data
        assert "analysis_timestamp" in data
        # These fields may be present even if unavailable
        # (they're just None/absent when status is unavailable)

    def test_health_endpoint_unchanged(self) -> None:
        """Health endpoint should still work unchanged."""
        response = client.get("/api/v1/market-analysis/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


# ---------------------------------------------------------------------------
# Test: Pool ID Determinism
# ---------------------------------------------------------------------------

class TestPoolIDDeterminism:
    def test_same_inputs_same_id(self) -> None:
        """Same inputs should always produce the same pool ID."""
        id1 = _generate_pool_id(LiquiditySide.BUY_SIDE, LiquidityPoolType.SWING_HIGH, 110.0, "1h")
        id2 = _generate_pool_id(LiquiditySide.BUY_SIDE, LiquidityPoolType.SWING_HIGH, 110.0, "1h")
        assert id1 == id2

    def test_different_prices_different_id(self) -> None:
        """Different price levels should produce different pool IDs."""
        id1 = _generate_pool_id(LiquiditySide.BUY_SIDE, LiquidityPoolType.SWING_HIGH, 110.0, "1h")
        id2 = _generate_pool_id(LiquiditySide.BUY_SIDE, LiquidityPoolType.SWING_HIGH, 110.1, "1h")
        assert id1 != id2

    def test_different_sides_different_id(self) -> None:
        """Different sides should produce different pool IDs."""
        id1 = _generate_pool_id(LiquiditySide.BUY_SIDE, LiquidityPoolType.SWING_HIGH, 110.0, "1h")
        id2 = _generate_pool_id(LiquiditySide.SELL_SIDE, LiquidityPoolType.SWING_HIGH, 110.0, "1h")
        assert id1 != id2


# ---------------------------------------------------------------------------
# Test: Configuration Validation
# ---------------------------------------------------------------------------

class TestLiquidityConfig:
    def test_defaults_are_sane(self) -> None:
        """Default configuration should have reasonable values."""
        settings = MarketAnalysisSettings()
        assert settings.liquidity_equal_level_tolerance_pct >= 0.0
        assert settings.liquidity_min_touches >= 1
        assert settings.liquidity_sweep_mode in ("wick", "close")
        assert settings.liquidity_max_active_pools >= 1
        assert settings.liquidity_max_history_depth >= 5

    def test_custom_settings(self) -> None:
        """Custom settings should override defaults."""
        settings = _settings(
            liquidity_equal_level_tolerance_pct=0.1,
            liquidity_min_touches=3,
            liquidity_sweep_mode="close",
            liquidity_max_active_pools=10,
        )
        assert settings.liquidity_equal_level_tolerance_pct == 0.1
        assert settings.liquidity_min_touches == 3
        assert settings.liquidity_sweep_mode == "close"
        assert settings.liquidity_max_active_pools == 10


# ---------------------------------------------------------------------------
# Test: Clustering Edge Cases
# ---------------------------------------------------------------------------

class TestClusteringEdgeCases:
    def test_single_cluster_of_many(self) -> None:
        """Many swings within tolerance should form one cluster."""
        swings = [
            _swing(i, 100.0 + i * 0.001, SwingType.SWING_HIGH)
            for i in range(10)
        ]
        clusters = _cluster_swings(swings, tolerance_pct=0.1)
        assert len(clusters) == 1
        assert len(clusters[0]) == 10

    def test_multiple_clusters(self) -> None:
        """Swings at distinct price levels should form separate clusters."""
        swings = [
            _swing(1, 100.0, SwingType.SWING_HIGH),
            _swing(2, 100.01, SwingType.SWING_HIGH),
            _swing(3, 110.0, SwingType.SWING_HIGH),
            _swing(4, 110.01, SwingType.SWING_HIGH),
        ]
        clusters = _cluster_swings(swings, tolerance_pct=0.05)
        assert len(clusters) == 2
        assert len(clusters[0]) == 2
        assert len(clusters[1]) == 2

    def test_empty_swings(self) -> None:
        """Empty swing list should produce no clusters."""
        clusters = _cluster_swings([], tolerance_pct=0.1)
        assert len(clusters) == 0

    def test_single_swing(self) -> None:
        """Single swing should produce one cluster of one."""
        swings = [_swing(1, 100.0, SwingType.SWING_HIGH)]
        clusters = _cluster_swings(swings, tolerance_pct=0.1)
        assert len(clusters) == 1
        assert len(clusters[0]) == 1
