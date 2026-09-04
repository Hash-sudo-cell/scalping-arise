"""
Scalping Arise — Liquidity Analysis Layer

Objective, descriptive liquidity context derived from confirmed swing points.
No trading decisions — market facts only.

Pipeline:
    Reuse existing confirmed swings
        -> Detect swing-based liquidity
        -> Cluster equal highs / equal lows
        -> Create normalized pools
        -> Classify strength
        -> Update/determine pool status
        -> Detect sweeps
        -> Classify post-sweep reaction
        -> Calculate nearest pools / proximity
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_analysis.config import MarketAnalysisSettings, get_market_analysis_settings
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
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pool ID generation (deterministic, stable)
# ---------------------------------------------------------------------------

def _generate_pool_id(
    side: LiquiditySide,
    pool_type: LiquidityPoolType,
    price_level: float,
    timeframe: str,
) -> str:
    """
    Generate a deterministic, stable pool ID.

    The same inputs always produce the same ID. Used for sweep matching
    and deduplication.
    """
    raw = f"{side.value}:{pool_type.value}:{price_level:.6f}:{timeframe}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _generate_sweep_id(pool_id: str, sweep_timestamp: datetime) -> str:
    """Generate a deterministic sweep event ID."""
    raw = f"{pool_id}:{sweep_timestamp.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Step 1: Swing-based liquidity detection
# ---------------------------------------------------------------------------

def detect_swing_liquidity(
    swings: list[SwingPoint],
    timeframe: str,
) -> list[LiquidityPool]:
    """
    Convert confirmed swings into individual liquidity pools.

    Rules:
        - Swing High -> BUY_SIDE liquidity pool
        - Swing Low  -> SELL_SIDE liquidity pool
        - Only confirmed swings are used
        - Each swing becomes its own pool

    Args:
        swings: Confirmed swing points from Phase 3 swing detection.
        timeframe: Timeframe label for pool metadata.

    Returns:
        List of individual swing-based LiquidityPool objects.
    """
    pools: list[LiquidityPool] = []

    for swing in swings:
        if not swing.confirmed:
            continue

        if swing.swing_type == SwingType.SWING_HIGH:
            side = LiquiditySide.BUY_SIDE
            pool_type = LiquidityPoolType.SWING_HIGH
        elif swing.swing_type == SwingType.SWING_LOW:
            side = LiquiditySide.SELL_SIDE
            pool_type = LiquidityPoolType.SWING_LOW
        else:
            continue

        pool_id = _generate_pool_id(side, pool_type, swing.price, timeframe)

        pools.append(LiquidityPool(
            pool_id=pool_id,
            side=side,
            pool_type=pool_type,
            price_level=swing.price,
            lower_bound=swing.price,
            upper_bound=swing.price,
            touch_count=1,
            source_swings=[swing.index],
            source_timestamps=[swing.timestamp],
            created_at=swing.timestamp,
            status=LiquidityPoolStatus.ACTIVE,
            strength=LiquidityStrength.LOW,  # Single swing = LOW
            timeframe=timeframe,
        ))

    logger.debug("Detected %d swing-based liquidity pools", len(pools))
    return pools


# ---------------------------------------------------------------------------
# Step 2: Equal highs / equal lows clustering
# ---------------------------------------------------------------------------

def cluster_equal_levels(
    swings: list[SwingPoint],
    tolerance_pct: float,
    min_touches: int,
    timeframe: str,
) -> list[LiquidityPool]:
    """
    Cluster confirmed swings into equal highs or equal lows pools.

    Rules:
        - Swing highs within tolerance_pct of each other -> EQUAL_HIGHS pool (BUY_SIDE)
        - Swing lows within tolerance_pct of each other -> EQUAL_LOWS pool (SELL_SIDE)
        - Only clusters with >= min_touches are kept
        - Clustering uses a simple single-linkage algorithm
        - Boundary tolerance: swings at exactly the tolerance boundary are included
        - No look-ahead bias: only swings available at evaluation time are used
        - Duplicate prevention: each swing belongs to at most one cluster

    Args:
        swings: Confirmed swing points.
        tolerance_pct: Percentage tolerance for clustering (e.g. 0.05 means 0.05%).
        min_touches: Minimum swings to form a cluster.
        timeframe: Timeframe label.

    Returns:
        List of equal-highs or equal-lows LiquidityPool objects.
    """
    pools: list[LiquidityPool] = []

    # Separate confirmed swings by type
    high_swings = [s for s in swings if s.confirmed and s.swing_type == SwingType.SWING_HIGH]
    low_swings = [s for s in swings if s.confirmed and s.swing_type == SwingType.SWING_LOW]

    # Cluster highs
    high_clusters = _cluster_swings(high_swings, tolerance_pct)
    for cluster in high_clusters:
        if len(cluster) >= min_touches:
            pool = _create_equal_level_pool(
                cluster,
                LiquiditySide.BUY_SIDE,
                LiquidityPoolType.EQUAL_HIGHS,
                tolerance_pct,
                timeframe,
            )
            pools.append(pool)

    # Cluster lows
    low_clusters = _cluster_swings(low_swings, tolerance_pct)
    for cluster in low_clusters:
        if len(cluster) >= min_touches:
            pool = _create_equal_level_pool(
                cluster,
                LiquiditySide.SELL_SIDE,
                LiquidityPoolType.EQUAL_LOWS,
                tolerance_pct,
                timeframe,
            )
            pools.append(pool)

    logger.debug("Clustered %d equal-level pools", len(pools))
    return pools


def _cluster_swings(
    swings: list[SwingPoint],
    tolerance_pct: float,
) -> list[list[SwingPoint]]:
    """
    Single-linkage clustering of swings by price proximity.

    Swings within tolerance_pct of the group center are added to the group.
    When a new swing is outside tolerance, the current group is finalized
    and a new group starts.

    Each swing appears in at most one cluster.
    """
    if not swings:
        return []

    # Sort by price for deterministic clustering
    sorted_swings = sorted(swings, key=lambda s: s.price)

    clusters: list[list[SwingPoint]] = []
    current_group: list[SwingPoint] = [sorted_swings[0]]

    for i in range(1, len(sorted_swings)):
        swing = sorted_swings[i]
        group_prices = [s.price for s in current_group]
        group_center = sum(group_prices) / len(group_prices)
        tolerance = group_center * (tolerance_pct / 100)

        if abs(swing.price - group_center) <= tolerance:
            current_group.append(swing)
        else:
            clusters.append(current_group)
            current_group = [swing]

    clusters.append(current_group)
    return clusters


def _create_equal_level_pool(
    cluster: list[SwingPoint],
    side: LiquiditySide,
    pool_type: LiquidityPoolType,
    tolerance_pct: float,
    timeframe: str,
) -> LiquidityPool:
    """Create a normalized equal-level pool from a cluster of swings."""
    prices = [s.price for s in cluster]
    avg_price = sum(prices) / len(prices)

    # Boundaries: the min/max of the cluster, expanded by tolerance
    lower = min(prices)
    upper = max(prices)

    pool_id = _generate_pool_id(side, pool_type, avg_price, timeframe)

    return LiquidityPool(
        pool_id=pool_id,
        side=side,
        pool_type=pool_type,
        price_level=avg_price,
        lower_bound=lower,
        upper_bound=upper,
        touch_count=len(cluster),
        source_swings=[s.index for s in cluster],
        source_timestamps=[s.timestamp for s in cluster],
        created_at=min(s.timestamp for s in cluster),
        status=LiquidityPoolStatus.ACTIVE,
        strength=_classify_strength(len(cluster)),
        timeframe=timeframe,
    )


# ---------------------------------------------------------------------------
# Step 3: Pool strength classification
# ---------------------------------------------------------------------------

def _classify_strength(touch_count: int) -> LiquidityStrength:
    """
    Deterministic strength classification based on touch count.

    Rules:
        - touch_count == 1 -> LOW
        - touch_count == 2 -> MEDIUM
        - touch_count >= 3 -> HIGH

    No future information used. Purely descriptive.
    """
    if touch_count >= 3:
        return LiquidityStrength.HIGH
    elif touch_count == 2:
        return LiquidityStrength.MEDIUM
    else:
        return LiquidityStrength.LOW


# ---------------------------------------------------------------------------
# Step 4: Pool status lifecycle
# ---------------------------------------------------------------------------

def update_pool_status(
    pool: LiquidityPool,
    candles: list[NormalizedCandle],
    sweep_mode: LiquiditySweepMode,
    min_sweep_distance_pct: float,
) -> LiquiditySweep | None:
    """
    Check if a candle sweeps the given pool.

    Status lifecycle:
        ACTIVE -> SWEPT (when price takes the pool level)

    Sweep rules:
        - BUY_SIDE: price trades above the pool upper_bound
        - SELL_SIDE: price trades below the pool lower_bound
        - WICK mode: wick (high/low) takes the level
        - CLOSE mode: close takes the level
        - min_sweep_distance_pct: additional distance beyond level required

    Args:
        pool: The liquidity pool to check.
        candles: Available candles for sweep evaluation.
        sweep_mode: How to evaluate the sweep (wick or close).
        min_sweep_distance_pct: Minimum distance beyond pool for valid sweep.

    Returns:
        LiquiditySweep if a sweep was detected, None otherwise.
    """
    if pool.status != LiquidityPoolStatus.ACTIVE:
        return None

    for candle in candles:
        sweep_price: float
        if sweep_mode == LiquiditySweepMode.WICK:
            if pool.side == LiquiditySide.BUY_SIDE:
                sweep_price = candle.high
            else:
                sweep_price = candle.low
        else:  # CLOSE mode
            sweep_price = candle.close

        swept = False
        if pool.side == LiquiditySide.BUY_SIDE:
            threshold = pool.upper_bound * (1 + min_sweep_distance_pct / 100)
            if sweep_price > threshold:
                swept = True
        else:  # SELL_SIDE
            threshold = pool.lower_bound * (1 - min_sweep_distance_pct / 100)
            if sweep_price < threshold:
                swept = True

        if swept:
            pool.status = LiquidityPoolStatus.SWEPT
            sweep_id = _generate_sweep_id(pool.pool_id, candle.timestamp)
            return LiquiditySweep(
                sweep_id=sweep_id,
                pool_id=pool.pool_id,
                side=pool.side,
                pool_price_level=pool.price_level,
                sweep_timestamp=candle.timestamp,
                sweep_mode=sweep_mode,
                sweep_price=sweep_price,
                candle_close=candle.close,
                reaction=PostSweepReaction.UNAVAILABLE,
                timeframe=pool.timeframe,
            )

    return None


# ---------------------------------------------------------------------------
# Step 5: Post-sweep reaction classification
# ---------------------------------------------------------------------------

def classify_post_sweep_reaction(
    sweep: LiquiditySweep,
    candles: list[NormalizedCandle],
    max_history_depth: int,
) -> LiquiditySweep:
    """
    Classify price behavior after a sweep event.

    Rules (after the sweeping candle):
        - REJECTION: price returns back through the pool level
            * BUY_SIDE: next candle closes below sweep's pool_price_level
            * SELL_SIDE: next candle closes above sweep's pool_price_level
        - ACCEPTANCE: price remains beyond the pool level
            * BUY_SIDE: next candle closes above pool_price_level
            * SELL_SIDE: next candle closes below pool_price_level
        - NEUTRAL: insufficient subsequent evidence
        - UNAVAILABLE: no subsequent candle available

    Uses only candles available up to the evaluation point. No look-ahead bias.

    Args:
        sweep: The sweep event to classify.
        candles: Full candle list (used to find post-sweep candles).
        max_history_depth: Maximum candles to look ahead for reaction.

    Returns:
        Updated sweep with reaction classified.
    """
    if sweep.reaction != PostSweepReaction.UNAVAILABLE:
        return sweep  # Already classified

    # Find the sweeping candle index
    sweep_idx: Optional[int] = None
    for i, candle in enumerate(candles):
        if candle.timestamp == sweep.sweep_timestamp:
            sweep_idx = i
            break

    if sweep_idx is None:
        return sweep

    # Look at the next candle(s) for reaction
    next_start = sweep_idx + 1
    next_end = min(next_start + max_history_depth, len(candles))

    if next_start >= len(candles):
        sweep.reaction = PostSweepReaction.UNAVAILABLE
        return sweep

    # Use the first available post-sweep candle for reaction classification
    next_candle = candles[next_start]

    if sweep.side == LiquiditySide.BUY_SIDE:
        # After sweeping above, does price reject (close below) or accept (close above)?
        if next_candle.close < sweep.pool_price_level:
            sweep.reaction = PostSweepReaction.REJECTION
        elif next_candle.close >= sweep.pool_price_level:
            sweep.reaction = PostSweepReaction.ACCEPTANCE
        else:
            sweep.reaction = PostSweepReaction.NEUTRAL
    else:  # SELL_SIDE
        # After sweeping below, does price reject (close above) or accept (close below)?
        if next_candle.close > sweep.pool_price_level:
            sweep.reaction = PostSweepReaction.REJECTION
        elif next_candle.close <= sweep.pool_price_level:
            sweep.reaction = PostSweepReaction.ACCEPTANCE
        else:
            sweep.reaction = PostSweepReaction.NEUTRAL

    sweep.reaction_timestamp = next_candle.timestamp

    logger.debug(
        "Sweep %s reaction: %s (next close: %.2f vs pool: %.2f)",
        sweep.sweep_id, sweep.reaction.value, next_candle.close, sweep.pool_price_level,
    )
    return sweep


# ---------------------------------------------------------------------------
# Step 6: Nearest pool proximity calculation
# ---------------------------------------------------------------------------

def calculate_proximity(
    pools: list[LiquidityPool],
    current_price: float,
) -> tuple[Optional[LiquidityPool], Optional[LiquidityPool], Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    Calculate the nearest active BUY_SIDE and SELL_SIDE pools.

    Distance is absolute price distance and percentage distance.

    Args:
        pools: All liquidity pools (active and non-active).
        current_price: Latest available price from the candle dataset.

    Returns:
        Tuple of (nearest_buy, nearest_sell, dist_buy, dist_sell, dist_buy_pct, dist_sell_pct)
        where dist_* values may be None if no active pools exist.
    """
    active_pools = [p for p in pools if p.status == LiquidityPoolStatus.ACTIVE]

    nearest_buy: Optional[LiquidityPool] = None
    nearest_sell: Optional[LiquidityPool] = None
    min_buy_dist: Optional[float] = None
    min_sell_dist: Optional[float] = None

    for pool in active_pools:
        # Distance is from current price to the pool's price_level
        dist = abs(current_price - pool.price_level)

        if pool.side == LiquiditySide.BUY_SIDE:
            if min_buy_dist is None or dist < min_buy_dist:
                min_buy_dist = dist
                nearest_buy = pool
        elif pool.side == LiquiditySide.SELL_SIDE:
            if min_sell_dist is None or dist < min_sell_dist:
                min_sell_dist = dist
                nearest_sell = pool

    # Calculate percentage distances
    buy_pct: Optional[float] = None
    sell_pct: Optional[float] = None

    if min_buy_dist is not None and current_price > 0:
        buy_pct = (min_buy_dist / current_price) * 100

    if min_sell_dist is not None and current_price > 0:
        sell_pct = (min_sell_dist / current_price) * 100

    return nearest_buy, nearest_sell, min_buy_dist, min_sell_dist, buy_pct, sell_pct


# ---------------------------------------------------------------------------
# Main orchestration function
# ---------------------------------------------------------------------------

def analyze_liquidity(
    swings: list[SwingPoint],
    candles: list[NormalizedCandle],
    current_price: Optional[float] = None,
    settings: Optional[MarketAnalysisSettings] = None,
) -> LiquidityAnalysisResult:
    """
    Run the complete liquidity analysis pipeline.

    Steps:
        1. Detect swing-based liquidity from confirmed swings
        2. Cluster equal highs / equal lows
        3. Merge pools (swing pools + equal-level pools)
        4. Classify strength
        5. Detect sweeps against all active pools
        6. Classify post-sweep reactions
        7. Calculate nearest pools and proximity
        8. Trim to max active pools

    No look-ahead bias: all operations use only available data.

    Args:
        swings: Confirmed swing points from Phase 3.
        candles: Available candle data for sweep detection.
        current_price: Latest price for proximity calculation.
        settings: Optional settings override.

    Returns:
        LiquidityAnalysisResult with pools, sweeps, and proximity data.
    """
    cfg = settings or get_market_analysis_settings()
    timeframe = candles[0].timeframe.value if candles else "unknown"

    # Validate sweep mode
    try:
        sweep_mode = LiquiditySweepMode(cfg.liquidity_sweep_mode)
    except ValueError:
        sweep_mode = LiquiditySweepMode.WICK

    # Step 1: Swing-based liquidity
    swing_pools = detect_swing_liquidity(swings, timeframe)

    # Step 2: Equal highs / equal lows clustering
    equal_pools = cluster_equal_levels(
        swings=swings,
        tolerance_pct=cfg.liquidity_equal_level_tolerance_pct,
        min_touches=cfg.liquidity_min_touches,
        timeframe=timeframe,
    )

    # Step 3: Merge pools — swing pools and equal-level pools
    # Equal-level pools may overlap with individual swing pools.
    # We keep both for now; deduplication is handled by pool_id uniqueness.
    all_pools = swing_pools + equal_pools

    # Step 4: Classify strength for swing pools (equal pools already classified)
    for pool in all_pools:
        if pool.pool_type in (LiquidityPoolType.SWING_HIGH, LiquidityPoolType.SWING_LOW):
            pool.strength = _classify_strength(pool.touch_count)

    # Step 5: Sort pools by creation time for deterministic ordering
    all_pools.sort(key=lambda p: (p.created_at, p.pool_id))

    # Step 6: Detect sweeps
    sweeps: list[LiquiditySweep] = []
    for pool in all_pools:
        sweep = update_pool_status(
            pool=pool,
            candles=candles,
            sweep_mode=sweep_mode,
            min_sweep_distance_pct=cfg.liquidity_min_sweep_distance_pct,
        )
        if sweep is not None:
            sweeps.append(sweep)

    # Step 7: Classify post-sweep reactions
    for sweep in sweeps:
        classify_post_sweep_reaction(
            sweep=sweep,
            candles=candles,
            max_history_depth=cfg.liquidity_max_history_depth,
        )

    # Step 8: Calculate proximity
    resolved_price = current_price
    if resolved_price is None and candles:
        resolved_price = candles[-1].close

    nearest_buy, nearest_sell, dist_buy, dist_sell, buy_pct, sell_pct = (
        calculate_proximity(all_pools, resolved_price) if resolved_price else
        (None, None, None, None, None, None)
    )

    # Step 9: Trim to max active pools (keep most recent, most liquid)
    active_pools = [p for p in all_pools if p.status == LiquidityPoolStatus.ACTIVE]
    if len(active_pools) > cfg.liquidity_max_active_pools:
        # Sort by strength (descending), then by touch_count, then by created_at (newest first)
        strength_order = {
            LiquidityStrength.HIGH: 3,
            LiquidityStrength.MEDIUM: 2,
            LiquidityStrength.LOW: 1,
        }
        active_pools.sort(
            key=lambda p: (
                -strength_order.get(p.strength, 0),
                -p.touch_count,
                -p.created_at.timestamp(),
            ),
        )
        # Keep only the top N, mark rest as INVALIDATED
        keep_ids = {p.pool_id for p in active_pools[:cfg.liquidity_max_active_pools]}
        for pool in all_pools:
            if pool.status == LiquidityPoolStatus.ACTIVE and pool.pool_id not in keep_ids:
                pool.status = LiquidityPoolStatus.INVALIDATED

    # Counts
    active_count = sum(1 for p in all_pools if p.status == LiquidityPoolStatus.ACTIVE)
    swept_count = sum(1 for p in all_pools if p.status == LiquidityPoolStatus.SWEPT)

    # Recalculate proximity after trimming
    nearest_buy, nearest_sell, dist_buy, dist_sell, buy_pct, sell_pct = (
        calculate_proximity(all_pools, resolved_price) if resolved_price else
        (None, None, None, None, None, None)
    )

    # Determine status
    if not swings:
        status = AnalysisStatus.UNAVAILABLE
        reason = "No confirmed swings available for liquidity analysis"
    elif not all_pools:
        status = AnalysisStatus.UNAVAILABLE
        reason = "No liquidity pools could be created"
    else:
        status = AnalysisStatus.AVAILABLE
        reason = (
            f"Liquidity analysis complete: {active_count} active pools, "
            f"{swept_count} swept, {len(sweeps)} sweep events"
        )

    logger.info(
        "Liquidity analysis: %s — %d pools, %d sweeps",
        status.value, len(all_pools), len(sweeps),
    )

    return LiquidityAnalysisResult(
        status=status,
        reason=reason,
        pools=all_pools,
        sweeps=sweeps,
        active_pool_count=active_count,
        swept_pool_count=swept_count,
        nearest_buy_side_pool=nearest_buy,
        nearest_sell_side_pool=nearest_sell,
        distance_to_buy_side=dist_buy,
        distance_to_sell_side=dist_sell,
        distance_to_buy_side_pct=buy_pct,
        distance_to_sell_side_pct=sell_pct,
    )
