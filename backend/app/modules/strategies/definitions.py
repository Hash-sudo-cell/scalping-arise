"""
Scalping Arise — Strategy Definitions

The three initial strategy definitions for Phase 5:
1. Trend Continuation
2. Pullback Continuation
3. Range Reversal

Each definition is explicit, versioned, and structured.
The condition engine evaluates these definitions — the definitions
themselves contain no evaluation logic.
"""

from __future__ import annotations

from app.modules.strategies.models import (
    ConditionCriticality,
    ConditionDefinition,
    InvalidationRule,
    LiquidityConditionDefinition,
    LiquidityConditionPolicy,
    SourceCompatibilityPolicy,
    StrategyDefinition,
    TimeframeRequirement,
    TimeframeRole,
    QualityWeight,
)


# ---------------------------------------------------------------------------
# Strategy 1: Trend Continuation
# ---------------------------------------------------------------------------

TREND_CONTINUATION = StrategyDefinition(
    strategy_id="trend_continuation",
    strategy_version="2.0",
    strategy_name="Trend Continuation",
    description=(
        "Identifies setups where the market is in an established trend "
        "and conditions suggest the trend is likely to continue. "
        "Uses trend alignment, momentum, market structure, "
        "multi-timeframe context, and liquidity context."
    ),
    enabled=True,
    applicable_market_regimes=["trending_up", "trending_down"],
    required_timeframes=[
        TimeframeRequirement(timeframe="15m", role=TimeframeRole.REQUIRED_CONTEXT),
        TimeframeRequirement(timeframe="5m", role=TimeframeRole.REQUIRED_SETUP),
        TimeframeRequirement(timeframe="1m", role=TimeframeRole.OPTIONAL_CONFIRMATION),
    ],
    source_compatibility_policy=SourceCompatibilityPolicy.FUTURES_PROXY_ALLOWED,
    required_conditions=[
        ConditionDefinition(
            condition_id="tc_trend_alignment",
            condition_name="Trend Alignment",
            description="EMA alignment must be bullish or bearish (not mixed or unavailable)",
            criticality=ConditionCriticality.CRITICAL,
        ),
        ConditionDefinition(
            condition_id="tc_regime_compatible",
            condition_name="Regime Compatible",
            description="Market regime must be trending_up or trending_down",
            criticality=ConditionCriticality.CRITICAL,
        ),
        ConditionDefinition(
            condition_id="tc_structure_supports_trend",
            condition_name="Structure Supports Trend",
            description="Recent structure labels must support the trend direction",
            criticality=ConditionCriticality.REQUIRED,
        ),
        ConditionDefinition(
            condition_id="tc_momentum_confirms",
            condition_name="Momentum Confirms",
            description="RSI must not be in opposite extreme (overbought for bullish, oversold for bearish)",
            criticality=ConditionCriticality.REQUIRED,
        ),
        ConditionDefinition(
            condition_id="tc_macd_context",
            condition_name="MACD Context",
            description="MACD context must align with or be neutral to the trend direction",
            criticality=ConditionCriticality.OPTIONAL,
        ),
        ConditionDefinition(
            condition_id="tc_volume_supports",
            condition_name="Volume Supports",
            description="Volume should not be in extreme low state",
            criticality=ConditionCriticality.OPTIONAL,
        ),
    ],
    optional_conditions=[
        ConditionDefinition(
            condition_id="tc_bb_position",
            condition_name="Bollinger Position",
            description="Price position relative to Bollinger Bands supports continuation",
            criticality=ConditionCriticality.OPTIONAL,
        ),
    ],
    invalidation_rules=[
        InvalidationRule(
            rule_id="tc_inval_choch",
            rule_name="CHOCH Against Trend",
            description="A Change of Character against the trend direction invalidates the setup",
        ),
        InvalidationRule(
            rule_id="tc_inval_regime_shift",
            rule_name="Regime Shift to Ranging",
            description="Market regime shifting to ranging invalidates the trend continuation setup",
        ),
    ],
    liquidity_conditions=[
        LiquidityConditionDefinition(
            condition_id="liq_active_pool_presence",
            condition_name="Active Liquidity Pools",
            description="At least one active liquidity pool should exist in the market",
            policy=LiquidityConditionPolicy.OPTIONAL,
        ),
        LiquidityConditionDefinition(
            condition_id="liq_sweep_presence",
            condition_name="Sweep Context",
            description="A liquidity sweep event may provide additional confirmation",
            policy=LiquidityConditionPolicy.OPTIONAL,
        ),
        LiquidityConditionDefinition(
            condition_id="liq_max_proximity",
            condition_name="Liquidity Proximity",
            description="Nearest relevant liquidity pool should be within 2.0% of price",
            policy=LiquidityConditionPolicy.OPTIONAL,
            max_distance_pct=2.0,
        ),
    ],
    liquidity_invalidation_rules=[
        InvalidationRule(
            rule_id="tc_liq_inval_opposing_sweep",
            rule_name="Opposing Sweep Detected",
            description="A strong liquidity sweep against the trend direction may invalidate the setup",
        ),
    ],
    quality_weights=[
        QualityWeight(category="structure", max_points=25, weight=0.25),
        QualityWeight(category="regime", max_points=15, weight=0.15),
        QualityWeight(category="multi_timeframe", max_points=15, weight=0.15),
        QualityWeight(category="technical_features", max_points=20, weight=0.20),
        QualityWeight(category="optional_confirmations", max_points=10, weight=0.10),
        QualityWeight(category="liquidity", max_points=15, weight=0.15),
    ],
    scoring_model_version="2.0",
)


# ---------------------------------------------------------------------------
# Strategy 2: Pullback Continuation
# ---------------------------------------------------------------------------

PULLBACK_CONTINUATION = StrategyDefinition(
    strategy_id="pullback_continuation",
    strategy_version="2.0",
    strategy_name="Pullback Continuation",
    description=(
        "Identifies setups where the market is in an established trend "
        "but has experienced a pullback, and conditions suggest the "
        "pullback is temporary and the primary trend will resume. "
        "Uses trend context, pullback detection via structure, "
        "support/resistance, EMA/price relationship, momentum recovery, "
        "and liquidity context."
    ),
    enabled=True,
    applicable_market_regimes=["trending_up", "trending_down"],
    required_timeframes=[
        TimeframeRequirement(timeframe="15m", role=TimeframeRole.REQUIRED_CONTEXT),
        TimeframeRequirement(timeframe="5m", role=TimeframeRole.REQUIRED_SETUP),
        TimeframeRequirement(timeframe="1m", role=TimeframeRole.OPTIONAL_CONFIRMATION),
    ],
    source_compatibility_policy=SourceCompatibilityPolicy.FUTURES_PROXY_ALLOWED,
    required_conditions=[
        ConditionDefinition(
            condition_id="pc_underlying_trend",
            condition_name="Underlying Trend Exists",
            description="A clear bullish or bearish trend must exist in the higher timeframe context",
            criticality=ConditionCriticality.CRITICAL,
        ),
        ConditionDefinition(
            condition_id="pc_pullback_detected",
            condition_name="Pullback Detected",
            description="Recent structure must show a counter-trend move (pullback) against the primary trend",
            criticality=ConditionCriticality.CRITICAL,
        ),
        ConditionDefinition(
            condition_id="pc_price_near_support_resistance",
            condition_name="Price Near S/R Zone",
            description="Price should be near a support zone (for bullish) or resistance zone (for bearish) area",
            criticality=ConditionCriticality.REQUIRED,
        ),
        ConditionDefinition(
            condition_id="pc_momentum_recovering",
            condition_name="Momentum Recovering",
            description="RSI should be moving toward neutral from the pullback extreme",
            criticality=ConditionCriticality.REQUIRED,
        ),
        ConditionDefinition(
            condition_id="pc_ema_relationship",
            condition_name="EMA Relationship",
            description="Price should be interacting with a key EMA (near or bouncing from it)",
            criticality=ConditionCriticality.REQUIRED,
        ),
        ConditionDefinition(
            condition_id="pc_regime_compatible",
            condition_name="Regime Compatible",
            description="Market regime must still be trending (not shifted to ranging)",
            criticality=ConditionCriticality.REQUIRED,
        ),
    ],
    optional_conditions=[
        ConditionDefinition(
            condition_id="pc_macd_turning",
            condition_name="MACD Turning",
            description="MACD histogram showing signs of reversal toward trend direction",
            criticality=ConditionCriticality.OPTIONAL,
        ),
        ConditionDefinition(
            condition_id="pc_volume_confirmation",
            condition_name="Volume Confirmation",
            description="Volume increasing during the pullback recovery",
            criticality=ConditionCriticality.OPTIONAL,
        ),
    ],
    invalidation_rules=[
        InvalidationRule(
            rule_id="pc_inval_structure_break",
            rule_name="Structure Break Against Trend",
            description="A structure break (BOS) against the primary trend invalidates the pullback setup",
        ),
        InvalidationRule(
            rule_id="pc_inval_regime_shift",
            rule_name="Regime Shift to Ranging",
            description="Market regime shifting to ranging invalidates the pullback continuation",
        ),
        InvalidationRule(
            rule_id="pc_inval_deep_pullback",
            rule_name="Deep Pullback",
            description="Pullback exceeds 61.8% of the prior trend move — no longer a pullback",
        ),
    ],
    liquidity_conditions=[
        LiquidityConditionDefinition(
            condition_id="liq_active_pool_presence",
            condition_name="Active Liquidity Pools",
            description="Active liquidity pools provide context for the pullback zone",
            policy=LiquidityConditionPolicy.OPTIONAL,
        ),
        LiquidityConditionDefinition(
            condition_id="liq_required_side",
            condition_name="Relevant Liquidity Side",
            description="Liquidity on the trend-continuation side should be present",
            policy=LiquidityConditionPolicy.OPTIONAL,
            required_side="buy_side",
        ),
        LiquidityConditionDefinition(
            condition_id="liq_sweep_presence",
            condition_name="Sweep Context",
            description="A liquidity sweep may confirm the pullback has taken liquidity before reversal",
            policy=LiquidityConditionPolicy.OPTIONAL,
        ),
        LiquidityConditionDefinition(
            condition_id="liq_max_proximity",
            condition_name="Liquidity Proximity",
            description="Nearest relevant liquidity pool should be within 1.5% of price",
            policy=LiquidityConditionPolicy.OPTIONAL,
            max_distance_pct=1.5,
        ),
    ],
    liquidity_invalidation_rules=[
        InvalidationRule(
            rule_id="pc_liq_inval_opposing_sweep",
            rule_name="Opposing Sweep Against Trend",
            description="A liquidity sweep against the trend direction may invalidate the pullback setup",
        ),
    ],
    quality_weights=[
        QualityWeight(category="structure", max_points=20, weight=0.20),
        QualityWeight(category="regime", max_points=10, weight=0.10),
        QualityWeight(category="multi_timeframe", max_points=15, weight=0.15),
        QualityWeight(category="technical_features", max_points=20, weight=0.20),
        QualityWeight(category="optional_confirmations", max_points=10, weight=0.10),
        QualityWeight(category="liquidity", max_points=25, weight=0.25),
    ],
    scoring_model_version="2.0",
)


# ---------------------------------------------------------------------------
# Strategy 3: Range Reversal
# ---------------------------------------------------------------------------

RANGE_REVERSAL = StrategyDefinition(
    strategy_id="range_reversal",
    strategy_version="2.0",
    strategy_name="Range Reversal",
    description=(
        "Identifies setups where the market is in a ranging regime and "
        "conditions suggest a reversal from a range boundary. Uses "
        "support/resistance zones, price position, RSI extremes, "
        "Bollinger Bands, multi-timeframe context, and liquidity context."
    ),
    enabled=True,
    applicable_market_regimes=["ranging"],
    required_timeframes=[
        TimeframeRequirement(timeframe="15m", role=TimeframeRole.REQUIRED_CONTEXT),
        TimeframeRequirement(timeframe="5m", role=TimeframeRole.REQUIRED_SETUP),
        TimeframeRequirement(timeframe="1m", role=TimeframeRole.OPTIONAL_CONFIRMATION),
    ],
    source_compatibility_policy=SourceCompatibilityPolicy.FUTURES_PROXY_ALLOWED,
    required_conditions=[
        ConditionDefinition(
            condition_id="rr_regime_ranging",
            condition_name="Regime is Ranging",
            description="Market regime must be classified as ranging",
            criticality=ConditionCriticality.CRITICAL,
        ),
        ConditionDefinition(
            condition_id="rr_price_at_boundary",
            condition_name="Price at Range Boundary",
            description="Price must be near a support zone (for bullish reversal) or resistance zone (for bearish reversal)",
            criticality=ConditionCriticality.CRITICAL,
        ),
        ConditionDefinition(
            condition_id="rr_rsi_extreme",
            condition_name="RSI at Extreme",
            description="RSI should be in oversold territory (for bullish reversal) or overbought (for bearish reversal)",
            criticality=ConditionCriticality.REQUIRED,
        ),
        ConditionDefinition(
            condition_id="rr_bb_extreme",
            condition_name="Bollinger Band Extreme",
            description="Price should be near or beyond Bollinger Band extremes",
            criticality=ConditionCriticality.REQUIRED,
        ),
        ConditionDefinition(
            condition_id="rr_structure_supports_reversal",
            condition_name="Structure Supports Reversal",
            description="Recent structure should show deceleration or reversal signs at the boundary",
            criticality=ConditionCriticality.REQUIRED,
        ),
    ],
    optional_conditions=[
        ConditionDefinition(
            condition_id="rr_volume_spike",
            condition_name="Volume Spike",
            description="Unusual volume at the range boundary suggesting exhaustion or accumulation",
            criticality=ConditionCriticality.OPTIONAL,
        ),
        ConditionDefinition(
            condition_id="rr_macd_divergence",
            condition_name="MACD Divergence",
            description="MACD showing divergence from price at the range boundary",
            criticality=ConditionCriticality.OPTIONAL,
        ),
    ],
    invalidation_rules=[
        InvalidationRule(
            rule_id="rr_inval_regime_change",
            rule_name="Regime Change to Trending",
            description="Market regime shifting to trending invalidates the range reversal setup",
        ),
        InvalidationRule(
            rule_id="rr_inval_breakout",
            rule_name="Range Breakout",
            description="A strong structure break beyond the range boundary invalidates the reversal",
        ),
    ],
    liquidity_conditions=[
        LiquidityConditionDefinition(
            condition_id="liq_active_pool_presence",
            condition_name="Active Liquidity Pools",
            description="Active liquidity pools at range boundaries provide reversal context",
            policy=LiquidityConditionPolicy.REQUIRED,
        ),
        LiquidityConditionDefinition(
            condition_id="liq_equal_highs",
            condition_name="Equal Highs",
            description="Equal highs near the upper range boundary indicate pooled buy-side liquidity",
            policy=LiquidityConditionPolicy.OPTIONAL,
        ),
        LiquidityConditionDefinition(
            condition_id="liq_equal_lows",
            condition_name="Equal Lows",
            description="Equal lows near the lower range boundary indicate pooled sell-side liquidity",
            policy=LiquidityConditionPolicy.OPTIONAL,
        ),
        LiquidityConditionDefinition(
            condition_id="liq_sweep_presence",
            condition_name="Sweep Context",
            description="A liquidity sweep at the range boundary confirms liquidity was taken",
            policy=LiquidityConditionPolicy.OPTIONAL,
        ),
        LiquidityConditionDefinition(
            condition_id="liq_post_sweep_reaction",
            condition_name="Post-Sweep Rejection",
            description="After a sweep, price should reject (return through the pool level)",
            policy=LiquidityConditionPolicy.OPTIONAL,
            required_side="rejection",
        ),
        LiquidityConditionDefinition(
            condition_id="liq_max_proximity",
            condition_name="Liquidity Proximity",
            description="Nearest relevant liquidity pool should be within 1.0% of price",
            policy=LiquidityConditionPolicy.REQUIRED,
            max_distance_pct=1.0,
        ),
    ],
    liquidity_invalidation_rules=[
        InvalidationRule(
            rule_id="rr_liq_inval_acceptance_after_sweep",
            rule_name="Acceptance After Sweep",
            description="If a sweep is followed by acceptance (price stays beyond pool level), the reversal may be invalidated",
        ),
    ],
    quality_weights=[
        QualityWeight(category="structure", max_points=20, weight=0.20),
        QualityWeight(category="regime", max_points=15, weight=0.15),
        QualityWeight(category="multi_timeframe", max_points=10, weight=0.10),
        QualityWeight(category="technical_features", max_points=20, weight=0.20),
        QualityWeight(category="optional_confirmations", max_points=10, weight=0.10),
        QualityWeight(category="liquidity", max_points=25, weight=0.25),
    ],
    scoring_model_version="2.0",
)


# ---------------------------------------------------------------------------
# Strategy Registry
# ---------------------------------------------------------------------------

ALL_STRATEGIES: dict[str, StrategyDefinition] = {
    s.strategy_id: s for s in [
        TREND_CONTINUATION,
        PULLBACK_CONTINUATION,
        RANGE_REVERSAL,
    ]
}


def get_strategy_definition(strategy_id: str) -> StrategyDefinition | None:
    """Look up a strategy definition by ID."""
    return ALL_STRATEGIES.get(strategy_id)


def get_all_strategy_definitions() -> list[StrategyDefinition]:
    """Return all registered strategy definitions."""
    return list(ALL_STRATEGIES.values())
