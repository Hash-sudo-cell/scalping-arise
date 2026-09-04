"""
Scalping Arise — Condition Evaluation Engine

Reusable, deterministic condition evaluation for strategy conditions.
Evaluates conditions based on analysis and feature data, producing
structured ConditionResult objects with full traceability.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.market_analysis.models import (
    AnalysisResult,
    LiquidityAnalysisResult,
    LiquidityPool,
    LiquidityPoolStatus,
    LiquidityPoolType,
    LiquiditySide,
    LiquidityStrength,
    PostSweepReaction,
    MarketRegime,
    StructureLabel,
    TrendState,
)
from app.modules.strategies.models import (
    ConditionCriticality,
    ConditionDefinition,
    ConditionResult,
    ConditionStatus,
    LiquidityConditionDefinition,
    LiquidityConditionPolicy,
    LiquidityConditionResult,
    LiquidityConditionSummary,
    LiquidityAvailability,
    LiquidityAvailabilityStatus,
    StrategyDefinition,
    StrategyDirection,
)
from app.modules.technical_features.models import (
    EMAAlignment,
    FeatureResult,
    MACDContext,
    RSISessionState,
    BollingerPosition,
    VolumeState,
)

logger = logging.getLogger(__name__)


def _make_unavailable(condition: ConditionDefinition, reason: str) -> ConditionResult:
    """Create an UNAVAILABLE condition result."""
    return ConditionResult(
        condition_id=condition.condition_id,
        condition_name=condition.condition_name,
        description=condition.description,
        criticality=condition.criticality,
        expected_value="data available",
        actual_value="unavailable",
        status=ConditionStatus.UNAVAILABLE,
        reason=reason,
        evidence=[],
    )


def _make_passed(
    condition: ConditionDefinition,
    actual_value: str,
    reason: str,
    evidence: list[str] | None = None,
) -> ConditionResult:
    """Create a PASSED condition result."""
    return ConditionResult(
        condition_id=condition.condition_id,
        condition_name=condition.condition_name,
        description=condition.description,
        criticality=condition.criticality,
        expected_value="pass",
        actual_value=actual_value,
        status=ConditionStatus.PASSED,
        reason=reason,
        evidence=evidence or [],
    )


def _make_failed(
    condition: ConditionDefinition,
    actual_value: str,
    reason: str,
    evidence: list[str] | None = None,
) -> ConditionResult:
    """Create a FAILED condition result."""
    return ConditionResult(
        condition_id=condition.condition_id,
        condition_name=condition.condition_name,
        description=condition.description,
        criticality=condition.criticality,
        expected_value="pass",
        actual_value=actual_value,
        status=ConditionStatus.FAILED,
        reason=reason,
        evidence=evidence or [],
    )


def evaluate_condition(
    condition: ConditionDefinition,
    analysis: Optional[AnalysisResult],
    features: Optional[FeatureResult],
    direction: StrategyDirection,
    regime_state: Optional[str] = None,
) -> ConditionResult:
    """
    Evaluate a single condition against analysis and feature data.

    Dispatches to the appropriate evaluator based on condition_id.
    """
    evaluator = _CONDITION_EVALUATORS.get(condition.condition_id)
    if evaluator is None:
        # Unknown condition — treat as unavailable
        return _make_unavailable(condition, f"No evaluator for condition '{condition.condition_id}'")

    return evaluator(condition, analysis, features, direction, regime_state)


# ---------------------------------------------------------------------------
# Individual condition evaluators
# ---------------------------------------------------------------------------

def _eval_tc_trend_alignment(condition, analysis, features, direction, regime_state):
    """Trend Continuation: EMA alignment must be bullish or bearish."""
    if features is None or features.trend is None:
        return _make_unavailable(condition, "Trend features not available")
    alignment = features.trend.alignment
    if alignment in (EMAAlignment.BULLISH, EMAAlignment.BEARISH):
        return _make_passed(
            condition,
            actual_value=f"alignment={alignment.value}",
            reason=f"EMA alignment is {alignment.value}",
            evidence=[f"EMA alignment: {alignment.value}"],
        )
    return _make_failed(
        condition,
        actual_value=f"alignment={alignment.value}",
        reason=f"EMA alignment is {alignment.value} — not a clean directional alignment",
        evidence=[f"EMA alignment: {alignment.value}"],
    )


def _eval_tc_regime_compatible(condition, analysis, features, direction, regime_state):
    """Trend Continuation: regime must be trending."""
    if regime_state is None:
        return _make_unavailable(condition, "Regime not available")
    if regime_state in ("trending_up", "trending_down"):
        return _make_passed(
            condition,
            actual_value=f"regime={regime_state}",
            reason=f"Market regime is {regime_state}",
            evidence=[f"Regime: {regime_state}"],
        )
    return _make_failed(
        condition,
        actual_value=f"regime={regime_state}",
        reason=f"Market regime is {regime_state} — not trending",
        evidence=[f"Regime: {regime_state}"],
    )


def _eval_tc_structure_supports_trend(condition, analysis, features, direction, regime_state):
    """Trend Continuation: structure labels should support the trend."""
    if analysis is None or analysis.structure is None:
        return _make_unavailable(condition, "Structure analysis not available")
    labels = analysis.structure.latest_labels
    if not labels:
        return _make_failed(condition, "no labels", "No structure labels available")
    recent = labels[-5:] if len(labels) >= 5 else labels
    if direction == StrategyDirection.BULLISH:
        bullish_labels = {StructureLabel.HH, StructureLabel.HL}
        if any(l in bullish_labels for l in recent):
            return _make_passed(
                condition,
                actual_value=f"recent_labels={[l.value for l in recent]}",
                reason="Recent structure labels support bullish trend",
                evidence=[f"Recent labels: {[l.value for l in recent]}"],
            )
        return _make_failed(
            condition,
            actual_value=f"recent_labels={[l.value for l in recent]}",
            reason="Recent structure labels do not support bullish trend",
            evidence=[f"Recent labels: {[l.value for l in recent]}"],
        )
    elif direction == StrategyDirection.BEARISH:
        bearish_labels = {StructureLabel.LH, StructureLabel.LL}
        if any(l in bearish_labels for l in recent):
            return _make_passed(
                condition,
                actual_value=f"recent_labels={[l.value for l in recent]}",
                reason="Recent structure labels support bearish trend",
                evidence=[f"Recent labels: {[l.value for l in recent]}"],
            )
        return _make_failed(
            condition,
            actual_value=f"recent_labels={[l.value for l in recent]}",
            reason="Recent structure labels do not support bearish trend",
            evidence=[f"Recent labels: {[l.value for l in recent]}"],
        )
    return _make_failed(
        condition,
        actual_value=f"direction={direction.value}",
        reason="Cannot determine structure support without clear direction",
    )


def _eval_tc_momentum_confirms(condition, analysis, features, direction, regime_state):
    """Trend Continuation: RSI not in opposite extreme."""
    if features is None or features.momentum is None:
        return _make_unavailable(condition, "Momentum features not available")
    rsi = features.momentum.get("rsi")
    if rsi is None:
        return _make_unavailable(condition, "RSI not available")
    if rsi.value is None:
        return _make_unavailable(condition, "RSI value not computed")
    if direction == StrategyDirection.BULLISH and rsi.state == RSISessionState.OVERBOUGHT:
        return _make_failed(
            condition,
            actual_value=f"rsi={rsi.value:.1f}, state={rsi.state.value}",
            reason="RSI is overbought — opposes bullish continuation",
            evidence=[f"RSI: {rsi.value:.1f}, state: {rsi.state.value}"],
        )
    if direction == StrategyDirection.BEARISH and rsi.state == RSISessionState.OVERSOLD:
        return _make_failed(
            condition,
            actual_value=f"rsi={rsi.value:.1f}, state={rsi.state.value}",
            reason="RSI is oversold — opposes bearish continuation",
            evidence=[f"RSI: {rsi.value:.1f}, state: {rsi.state.value}"],
        )
    return _make_passed(
        condition,
        actual_value=f"rsi={rsi.value:.1f}, state={rsi.state.value}",
        reason=f"RSI state ({rsi.state.value}) does not oppose trend direction",
        evidence=[f"RSI: {rsi.value:.1f}, state: {rsi.state.value}"],
    )


def _eval_tc_macd_context(condition, analysis, features, direction, regime_state):
    """Trend Continuation: MACD context aligns with or is neutral to trend."""
    if features is None or features.momentum is None:
        return _make_unavailable(condition, "Momentum features not available")
    macd = features.momentum.get("macd")
    if macd is None:
        return _make_unavailable(condition, "MACD not available")
    if macd.context == MACDContext.NEUTRAL:
        return _make_passed(
            condition,
            actual_value=f"macd_context={macd.context.value}",
            reason="MACD context is neutral — does not oppose trend",
            evidence=[f"MACD context: {macd.context.value}"],
        )
    if direction == StrategyDirection.BULLISH and macd.context == MACDContext.BULLISH:
        return _make_passed(
            condition,
            actual_value=f"macd_context={macd.context.value}",
            reason="MACD context is bullish — confirms trend",
            evidence=[f"MACD context: {macd.context.value}"],
        )
    if direction == StrategyDirection.BEARISH and macd.context == MACDContext.BEARISH:
        return _make_passed(
            condition,
            actual_value=f"macd_context={macd.context.value}",
            reason="MACD context is bearish — confirms trend",
            evidence=[f"MACD context: {macd.context.value}"],
        )
    return _make_passed(
        condition,
        actual_value=f"macd_context={macd.context.value}",
        reason=f"MACD context ({macd.context.value}) does not strongly oppose trend",
        evidence=[f"MACD context: {macd.context.value}"],
    )


def _eval_tc_volume_supports(condition, analysis, features, direction, regime_state):
    """Trend Continuation: volume should not be extremely low."""
    if features is None or features.volume is None:
        return _make_unavailable(condition, "Volume features not available")
    vol = features.volume
    if vol.state == VolumeState.LOW:
        return _make_passed(
            condition,
            actual_value=f"volume_state={vol.state.value}",
            reason="Volume is low but not a blocker",
            evidence=[f"Volume state: {vol.state.value}"],
        )
    return _make_passed(
        condition,
        actual_value=f"volume_state={vol.state.value}",
        reason=f"Volume state is {vol.state.value}",
        evidence=[f"Volume state: {vol.state.value}"],
    )


def _eval_tc_bb_position(condition, analysis, features, direction, regime_state):
    """Trend Continuation: BB position supports continuation."""
    if features is None or features.volatility is None:
        return _make_unavailable(condition, "Volatility features not available")
    bb = features.volatility.get("bollinger_bands")
    if bb is None:
        return _make_unavailable(condition, "Bollinger Bands not available")
    if direction == StrategyDirection.BULLISH and bb.price_position in (BollingerPosition.MIDDLE_REGION, BollingerPosition.LOWER_REGION):
        return _make_passed(
            condition,
            actual_value=f"bb_position={bb.price_position.value}",
            reason="Price is in middle/lower BB region — room for continuation",
            evidence=[f"BB position: {bb.price_position.value}"],
        )
    if direction == StrategyDirection.BEARISH and bb.price_position in (BollingerPosition.MIDDLE_REGION, BollingerPosition.UPPER_REGION):
        return _make_passed(
            condition,
            actual_value=f"bb_position={bb.price_position.value}",
            reason="Price is in middle/upper BB region — room for continuation",
            evidence=[f"BB position: {bb.price_position.value}"],
        )
    return _make_passed(
        condition,
        actual_value=f"bb_position={bb.price_position.value}",
        reason=f"BB position ({bb.price_position.value}) — neutral",
        evidence=[f"BB position: {bb.price_position.value}"],
    )


# --- Pullback Continuation conditions ---

def _eval_pc_underlying_trend(condition, analysis, features, direction, regime_state):
    """Pullback Continuation: underlying trend exists."""
    if analysis is None or analysis.trend is None:
        return _make_unavailable(condition, "Trend analysis not available")
    trend_state = analysis.trend.state
    if trend_state in (TrendState.BULLISH, TrendState.BEARISH):
        return _make_passed(
            condition,
            actual_value=f"trend={trend_state.value}",
            reason=f"Underlying trend is {trend_state.value}",
            evidence=[f"Trend: {trend_state.value}"],
        )
    return _make_failed(
        condition,
        actual_value=f"trend={trend_state.value}",
        reason=f"No clear underlying trend (state={trend_state.value})",
        evidence=[f"Trend: {trend_state.value}"],
    )


def _eval_pc_pullback_detected(condition, analysis, features, direction, regime_state):
    """Pullback Continuation: pullback detected in structure."""
    if analysis is None or analysis.structure is None:
        return _make_unavailable(condition, "Structure analysis not available")
    labels = analysis.structure.latest_labels
    if not labels or len(labels) < 3:
        return _make_failed(
            condition,
            actual_value=f"labels={[l.value for l in labels]}",
            reason="Insufficient structure labels to detect pullback",
        )
    recent = labels[-5:] if len(labels) >= 5 else labels
    if direction == StrategyDirection.BULLISH:
        # In an uptrend, pullback shows as LH or LL in recent labels
        pullback_labels = {StructureLabel.LH, StructureLabel.LL}
        if any(l in pullback_labels for l in recent):
            return _make_passed(
                condition,
                actual_value=f"recent_labels={[l.value for l in recent]}",
                reason="Counter-trend labels detected — pullback present",
                evidence=[f"Recent labels: {[l.value for l in recent]}"],
            )
        return _make_failed(
            condition,
            actual_value=f"recent_labels={[l.value for l in recent]}",
            reason="No counter-trend labels detected — no pullback found",
            evidence=[f"Recent labels: {[l.value for l in recent]}"],
        )
    elif direction == StrategyDirection.BEARISH:
        pullback_labels = {StructureLabel.HH, StructureLabel.HL}
        if any(l in pullback_labels for l in recent):
            return _make_passed(
                condition,
                actual_value=f"recent_labels={[l.value for l in recent]}",
                reason="Counter-trend labels detected — pullback present",
                evidence=[f"Recent labels: {[l.value for l in recent]}"],
            )
        return _make_failed(
            condition,
            actual_value=f"recent_labels={[l.value for l in recent]}",
            reason="No counter-trend labels detected — no pullback found",
            evidence=[f"Recent labels: {[l.value for l in recent]}"],
        )
    return _make_failed(
        condition,
        actual_value=f"direction={direction.value}",
        reason="Cannot detect pullback without clear direction",
    )


def _eval_pc_price_near_support_resistance(condition, analysis, features, direction, regime_state):
    """Pullback Continuation: price near S/R zone."""
    if analysis is None or analysis.zones is None or features is None or features.price is None:
        return _make_unavailable(condition, "S/R zones or price not available")
    current_price = features.price.current_price
    if current_price is None:
        return _make_unavailable(condition, "Current price not available")
    zones = analysis.zones.support if direction == StrategyDirection.BULLISH else analysis.zones.resistance
    if not zones:
        return _make_passed(
            condition,
            actual_value="no zones",
            reason="No specific S/R zones detected — not blocking",
            evidence=["No zones detected"],
        )
    for zone in zones:
        if zone.lower_bound <= current_price <= zone.upper_bound * 1.02:
            return _make_passed(
                condition,
                actual_value=f"price={current_price:.2f}, zone=[{zone.lower_bound:.2f}-{zone.upper_bound:.2f}]",
                reason=f"Price is within or near {'support' if direction == StrategyDirection.BULLISH else 'resistance'} zone",
                evidence=[f"Zone: [{zone.lower_bound:.2f}-{zone.upper_bound:.2f}], price: {current_price:.2f}"],
            )
    return _make_passed(
        condition,
        actual_value=f"price={current_price:.2f}, zones_available={len(zones)}",
        reason="S/R zones exist but price is not at the boundary — not blocking",
        evidence=[f"Price: {current_price:.2f}, zones: {len(zones)}"],
    )


def _eval_pc_momentum_recovering(condition, analysis, features, direction, regime_state):
    """Pullback Continuation: RSI recovering toward neutral."""
    if features is None or features.momentum is None:
        return _make_unavailable(condition, "Momentum features not available")
    rsi = features.momentum.get("rsi")
    if rsi is None or rsi.value is None:
        return _make_unavailable(condition, "RSI not available")
    if direction == StrategyDirection.BULLISH and rsi.state in (RSISessionState.OVERSOLD, RSISessionState.WEAK, RSISessionState.NEUTRAL):
        return _make_passed(
            condition,
            actual_value=f"rsi={rsi.value:.1f}, state={rsi.state.value}",
            reason=f"RSI state ({rsi.state.value}) suggests recovery from pullback",
            evidence=[f"RSI: {rsi.value:.1f}, state: {rsi.state.value}"],
        )
    if direction == StrategyDirection.BEARISH and rsi.state in (RSISessionState.OVERBOUGHT, RSISessionState.STRONG, RSISessionState.NEUTRAL):
        return _make_passed(
            condition,
            actual_value=f"rsi={rsi.value:.1f}, state={rsi.state.value}",
            reason=f"RSI state ({rsi.state.value}) suggests recovery from pullback",
            evidence=[f"RSI: {rsi.value:.1f}, state: {rsi.state.value}"],
        )
    return _make_passed(
        condition,
        actual_value=f"rsi={rsi.value:.1f}, state={rsi.state.value}",
        reason=f"RSI state ({rsi.state.value}) — neutral for pullback",
        evidence=[f"RSI: {rsi.value:.1f}, state: {rsi.state.value}"],
    )


def _eval_pc_ema_relationship(condition, analysis, features, direction, regime_state):
    """Pullback Continuation: price interacting with key EMA."""
    if features is None or features.trend is None:
        return _make_unavailable(condition, "Trend features not available")
    ema = features.trend
    price_rel_fast = ema.fast.price_relative
    price_rel_medium = ema.medium.price_relative
    if price_rel_fast == "at" or price_rel_medium == "at":
        return _make_passed(
            condition,
            actual_value=f"fast={price_rel_fast}, medium={price_rel_medium}",
            reason="Price is at a key EMA — potential bounce point",
            evidence=[f"EMA fast relative: {price_rel_fast}, medium: {price_rel_medium}"],
        )
    if direction == StrategyDirection.BULLISH and price_rel_fast in ("above",):
        return _make_passed(
            condition,
            actual_value=f"fast={price_rel_fast}, medium={price_rel_medium}",
            reason="Price above fast EMA — pullback may be temporary",
            evidence=[f"EMA fast relative: {price_rel_fast}, medium: {price_rel_medium}"],
        )
    if direction == StrategyDirection.BEARISH and price_rel_fast in ("below",):
        return _make_passed(
            condition,
            actual_value=f"fast={price_rel_fast}, medium={price_rel_medium}",
            reason="Price below fast EMA — pullback may be temporary",
            evidence=[f"EMA fast relative: {price_rel_fast}, medium: {price_rel_medium}"],
        )
    return _make_passed(
        condition,
        actual_value=f"fast={price_rel_fast}, medium={price_rel_medium}",
        reason="EMA relationship present",
        evidence=[f"EMA fast relative: {price_rel_fast}, medium: {price_rel_medium}"],
    )


def _eval_pc_regime_compatible(condition, analysis, features, direction, regime_state):
    """Pullback Continuation: regime still trending."""
    if regime_state is None:
        return _make_unavailable(condition, "Regime not available")
    if regime_state in ("trending_up", "trending_down"):
        return _make_passed(
            condition,
            actual_value=f"regime={regime_state}",
            reason=f"Market regime is still {regime_state}",
            evidence=[f"Regime: {regime_state}"],
        )
    return _make_failed(
        condition,
        actual_value=f"regime={regime_state}",
        reason=f"Market regime shifted to {regime_state} — no longer trending",
        evidence=[f"Regime: {regime_state}"],
    )


def _eval_pc_macd_turning(condition, analysis, features, direction, regime_state):
    """Pullback Continuation: MACD histogram turning."""
    if features is None or features.momentum is None:
        return _make_unavailable(condition, "Momentum features not available")
    macd = features.momentum.get("macd")
    if macd is None or macd.histogram is None:
        return _make_unavailable(condition, "MACD histogram not available")
    if direction == StrategyDirection.BULLISH and macd.histogram > 0:
        return _make_passed(
            condition,
            actual_value=f"histogram={macd.histogram:.4f}",
            reason="MACD histogram positive — turning bullish",
            evidence=[f"Histogram: {macd.histogram:.4f}"],
        )
    if direction == StrategyDirection.BEARISH and macd.histogram < 0:
        return _make_passed(
            condition,
            actual_value=f"histogram={macd.histogram:.4f}",
            reason="MACD histogram negative — turning bearish",
            evidence=[f"Histogram: {macd.histogram:.4f}"],
        )
    return _make_passed(
        condition,
        actual_value=f"histogram={macd.histogram:.4f}",
        reason=f"MACD histogram ({macd.histogram:.4f}) — neutral",
        evidence=[f"Histogram: {macd.histogram:.4f}"],
    )


def _eval_pc_volume_confirmation(condition, analysis, features, direction, regime_state):
    """Pullback Continuation: volume increasing."""
    if features is None or features.volume is None:
        return _make_unavailable(condition, "Volume features not available")
    vol = features.volume
    if vol.state == VolumeState.HIGH:
        return _make_passed(
            condition,
            actual_value=f"volume_state={vol.state.value}",
            reason="Volume is high — confirming activity",
            evidence=[f"Volume state: {vol.state.value}"],
        )
    return _make_passed(
        condition,
        actual_value=f"volume_state={vol.state.value}",
        reason=f"Volume state: {vol.state.value}",
        evidence=[f"Volume state: {vol.state.value}"],
    )


# --- Range Reversal conditions ---

def _eval_rr_regime_ranging(condition, analysis, features, direction, regime_state):
    """Range Reversal: regime must be ranging."""
    if regime_state is None:
        return _make_unavailable(condition, "Regime not available")
    if regime_state == "ranging":
        return _make_passed(
            condition,
            actual_value=f"regime={regime_state}",
            reason="Market regime is ranging",
            evidence=[f"Regime: {regime_state}"],
        )
    return _make_failed(
        condition,
        actual_value=f"regime={regime_state}",
        reason=f"Market regime is {regime_state} — not ranging",
        evidence=[f"Regime: {regime_state}"],
    )


def _eval_rr_price_at_boundary(condition, analysis, features, direction, regime_state):
    """Range Reversal: price at range boundary."""
    if analysis is None or analysis.zones is None or features is None or features.price is None:
        return _make_unavailable(condition, "S/R zones or price not available")
    current_price = features.price.current_price
    if current_price is None:
        return _make_unavailable(condition, "Current price not available")
    zones = analysis.zones.support if direction == StrategyDirection.BULLISH else analysis.zones.resistance
    if not zones:
        return _make_failed(
            condition,
            actual_value="no zones",
            reason="No S/R zones detected — cannot determine boundary",
        )
    for zone in zones:
        if zone.lower_bound <= current_price <= zone.upper_bound * 1.03:
            return _make_passed(
                condition,
                actual_value=f"price={current_price:.2f}, zone=[{zone.lower_bound:.2f}-{zone.upper_bound:.2f}]",
                reason=f"Price is at {'support' if direction == StrategyDirection.BULLISH else 'resistance'} boundary",
                evidence=[f"Zone: [{zone.lower_bound:.2f}-{zone.upper_bound:.2f}], price: {current_price:.2f}"],
            )
    return _make_failed(
        condition,
        actual_value=f"price={current_price:.2f}",
        reason="Price is not at a range boundary",
        evidence=[f"Price: {current_price:.2f}, zones: {len(zones)}"],
    )


def _eval_rr_rsi_extreme(condition, analysis, features, direction, regime_state):
    """Range Reversal: RSI at extreme."""
    if features is None or features.momentum is None:
        return _make_unavailable(condition, "Momentum features not available")
    rsi = features.momentum.get("rsi")
    if rsi is None or rsi.value is None:
        return _make_unavailable(condition, "RSI not available")
    if direction == StrategyDirection.BULLISH and rsi.state == RSISessionState.OVERSOLD:
        return _make_passed(
            condition,
            actual_value=f"rsi={rsi.value:.1f}, state={rsi.state.value}",
            reason="RSI is oversold — supports bullish reversal",
            evidence=[f"RSI: {rsi.value:.1f}, state: {rsi.state.value}"],
        )
    if direction == StrategyDirection.BEARISH and rsi.state == RSISessionState.OVERBOUGHT:
        return _make_passed(
            condition,
            actual_value=f"rsi={rsi.value:.1f}, state={rsi.state.value}",
            reason="RSI is overbought — supports bearish reversal",
            evidence=[f"RSI: {rsi.value:.1f}, state: {rsi.state.value}"],
        )
    return _make_failed(
        condition,
        actual_value=f"rsi={rsi.value:.1f}, state={rsi.state.value}",
        reason=f"RSI state ({rsi.state.value}) is not at the expected extreme for reversal",
        evidence=[f"RSI: {rsi.value:.1f}, state: {rsi.state.value}"],
    )


def _eval_rr_bb_extreme(condition, analysis, features, direction, regime_state):
    """Range Reversal: price at Bollinger Band extreme."""
    if features is None or features.volatility is None:
        return _make_unavailable(condition, "Volatility features not available")
    bb = features.volatility.get("bollinger_bands")
    if bb is None:
        return _make_unavailable(condition, "Bollinger Bands not available")
    if direction == StrategyDirection.BULLISH and bb.price_position in (BollingerPosition.BELOW_LOWER, BollingerPosition.LOWER_REGION):
        return _make_passed(
            condition,
            actual_value=f"bb_position={bb.price_position.value}",
            reason="Price near/below lower BB — supports bullish reversal",
            evidence=[f"BB position: {bb.price_position.value}"],
        )
    if direction == StrategyDirection.BEARISH and bb.price_position in (BollingerPosition.ABOVE_UPPER, BollingerPosition.UPPER_REGION):
        return _make_passed(
            condition,
            actual_value=f"bb_position={bb.price_position.value}",
            reason="Price near/above upper BB — supports bearish reversal",
            evidence=[f"BB position: {bb.price_position.value}"],
        )
    return _make_failed(
        condition,
        actual_value=f"bb_position={bb.price_position.value}",
        reason=f"BB position ({bb.price_position.value}) is not at extreme for reversal",
        evidence=[f"BB position: {bb.price_position.value}"],
    )


def _eval_rr_structure_supports_reversal(condition, analysis, features, direction, regime_state):
    """Range Reversal: structure shows reversal signs."""
    if analysis is None or analysis.structure is None:
        return _make_unavailable(condition, "Structure analysis not available")
    labels = analysis.structure.latest_labels
    if not labels:
        return _make_failed(condition, "no labels", "No structure labels available")
    recent = labels[-3:] if len(labels) >= 3 else labels
    return _make_passed(
        condition,
        actual_value=f"recent_labels={[l.value for l in recent]}",
        reason=f"Structure labels present: {[l.value for l in recent]}",
        evidence=[f"Recent labels: {[l.value for l in recent]}"],
    )


def _eval_rr_volume_spike(condition, analysis, features, direction, regime_state):
    """Range Reversal: volume spike at boundary."""
    if features is None or features.volume is None:
        return _make_unavailable(condition, "Volume features not available")
    vol = features.volume
    if vol.state == VolumeState.HIGH:
        return _make_passed(
            condition,
            actual_value=f"volume_state={vol.state.value}",
            reason="Volume spike detected at range boundary",
            evidence=[f"Volume state: {vol.state.value}"],
        )
    return _make_passed(
        condition,
        actual_value=f"volume_state={vol.state.value}",
        reason=f"Volume state: {vol.state.value} — not spiking",
        evidence=[f"Volume state: {vol.state.value}"],
    )


def _eval_rr_macd_divergence(condition, analysis, features, direction, regime_state):
    """Range Reversal: MACD divergence."""
    if features is None or features.momentum is None:
        return _make_unavailable(condition, "Momentum features not available")
    macd = features.momentum.get("macd")
    if macd is None:
        return _make_unavailable(condition, "MACD not available")
    if direction == StrategyDirection.BULLISH and macd.context == MACDContext.BULLISH:
        return _make_passed(
            condition,
            actual_value=f"macd_context={macd.context.value}",
            reason="MACD context is bullish — supports reversal",
            evidence=[f"MACD context: {macd.context.value}"],
        )
    if direction == StrategyDirection.BEARISH and macd.context == MACDContext.BEARISH:
        return _make_passed(
            condition,
            actual_value=f"macd_context={macd.context.value}",
            reason="MACD context is bearish — supports reversal",
            evidence=[f"MACD context: {macd.context.value}"],
        )
    return _make_passed(
        condition,
        actual_value=f"macd_context={macd.context.value}",
        reason=f"MACD context ({macd.context.value}) — neutral",
        evidence=[f"MACD context: {macd.context.value}"],
    )


# ---------------------------------------------------------------------------
# Condition evaluator registry
# ---------------------------------------------------------------------------

_CONDITION_EVALUATORS = {
    # Trend Continuation
    "tc_trend_alignment": _eval_tc_trend_alignment,
    "tc_regime_compatible": _eval_tc_regime_compatible,
    "tc_structure_supports_trend": _eval_tc_structure_supports_trend,
    "tc_momentum_confirms": _eval_tc_momentum_confirms,
    "tc_macd_context": _eval_tc_macd_context,
    "tc_volume_supports": _eval_tc_volume_supports,
    "tc_bb_position": _eval_tc_bb_position,
    # Pullback Continuation
    "pc_underlying_trend": _eval_pc_underlying_trend,
    "pc_pullback_detected": _eval_pc_pullback_detected,
    "pc_price_near_support_resistance": _eval_pc_price_near_support_resistance,
    "pc_momentum_recovering": _eval_pc_momentum_recovering,
    "pc_ema_relationship": _eval_pc_ema_relationship,
    "pc_regime_compatible": _eval_pc_regime_compatible,
    "pc_macd_turning": _eval_pc_macd_turning,
    "pc_volume_confirmation": _eval_pc_volume_confirmation,
    # Range Reversal
    "rr_regime_ranging": _eval_rr_regime_ranging,
    "rr_price_at_boundary": _eval_rr_price_at_boundary,
    "rr_rsi_extreme": _eval_rr_rsi_extreme,
    "rr_bb_extreme": _eval_rr_bb_extreme,
    "rr_structure_supports_reversal": _eval_rr_structure_supports_reversal,
    "rr_volume_spike": _eval_rr_volume_spike,
    "rr_macd_divergence": _eval_rr_macd_divergence,
}


def evaluate_conditions(
    strategy: StrategyDefinition,
    analysis: Optional[AnalysisResult],
    features: Optional[FeatureResult],
    direction: StrategyDirection,
    regime_state: Optional[str] = None,
) -> list[ConditionResult]:
    """
    Evaluate all conditions for a strategy.

    Returns a list of ConditionResult for every required and optional condition.
    """
    results: list[ConditionResult] = []

    for cond in strategy.required_conditions:
        result = evaluate_condition(cond, analysis, features, direction, regime_state)
        results.append(result)

    for cond in strategy.optional_conditions:
        result = evaluate_condition(cond, analysis, features, direction, regime_state)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Liquidity condition evaluators
# ---------------------------------------------------------------------------

def _liq_make_unavailable(condition: LiquidityConditionDefinition, reason: str) -> LiquidityConditionResult:
    """Create an UNAVAILABLE liquidity condition result."""
    return LiquidityConditionResult(
        condition_id=condition.condition_id,
        condition_name=condition.condition_name,
        description=condition.description,
        policy=condition.policy,
        status=ConditionStatus.UNAVAILABLE,
        expected_value="liquidity data available",
        actual_value="unavailable",
        reason=reason,
        evidence=[],
    )


def _liq_make_passed(
    condition: LiquidityConditionDefinition,
    actual_value: str,
    reason: str,
    evidence: list[str] | None = None,
) -> LiquidityConditionResult:
    """Create a PASSED liquidity condition result."""
    return LiquidityConditionResult(
        condition_id=condition.condition_id,
        condition_name=condition.condition_name,
        description=condition.description,
        policy=condition.policy,
        status=ConditionStatus.PASSED,
        expected_value="pass",
        actual_value=actual_value,
        reason=reason,
        evidence=evidence or [],
    )


def _liq_make_failed(
    condition: LiquidityConditionDefinition,
    actual_value: str,
    reason: str,
    evidence: list[str] | None = None,
) -> LiquidityConditionResult:
    """Create a FAILED liquidity condition result."""
    return LiquidityConditionResult(
        condition_id=condition.condition_id,
        condition_name=condition.condition_name,
        description=condition.description,
        policy=condition.policy,
        status=ConditionStatus.FAILED,
        expected_value="pass",
        actual_value=actual_value,
        reason=reason,
        evidence=evidence or [],
    )


def _eval_liq_active_pool_presence(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether active liquidity pools exist."""
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    active = [p for p in liquidity.pools if p.status == LiquidityPoolStatus.ACTIVE]
    if active:
        side_summary = f"buy_side={[p.pool_id for p in active if p.side == LiquiditySide.BUY_SIDE]}, sell_side={[p.pool_id for p in active if p.side == LiquiditySide.SELL_SIDE]}"
        return _liq_make_passed(
            condition,
            actual_value=f"active_pools={len(active)}",
            reason=f"{len(active)} active liquidity pool(s) detected",
            evidence=[side_summary],
        )
    return _liq_make_failed(
        condition,
        actual_value="active_pools=0",
        reason="No active liquidity pools detected",
    )


def _eval_liq_required_side(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether the required liquidity side has active pools."""
    required_side_str = condition.required_side
    if required_side_str is None:
        return _liq_make_unavailable(condition, "No required side configured")
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    try:
        required_side = LiquiditySide(required_side_str)
    except ValueError:
        return _liq_make_unavailable(condition, f"Invalid required_side: {required_side_str}")
    active_on_side = [
        p for p in liquidity.pools
        if p.status == LiquidityPoolStatus.ACTIVE and p.side == required_side
    ]
    if active_on_side:
        return _liq_make_passed(
            condition,
            actual_value=f"{required_side_str}_active_pools={len(active_on_side)}",
            reason=f"{len(active_on_side)} active {required_side_str} pool(s) present",
            evidence=[f"Pools: {[p.pool_id for p in active_on_side]}"],
        )
    return _liq_make_failed(
        condition,
        actual_value=f"{required_side_str}_active_pools=0",
        reason=f"No active {required_side_str} pools detected",
    )


def _eval_liq_pool_type(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether a specific pool type exists among active pools."""
    required_type_str = condition.required_side  # Reuse field for pool type in this evaluator
    if required_type_str is None:
        return _liq_make_unavailable(condition, "No required pool type configured")
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    try:
        required_type = LiquidityPoolType(required_type_str)
    except ValueError:
        return _liq_make_unavailable(condition, f"Invalid pool type: {required_type_str}")
    active_of_type = [
        p for p in liquidity.pools
        if p.status == LiquidityPoolStatus.ACTIVE and p.pool_type == required_type
    ]
    if active_of_type:
        return _liq_make_passed(
            condition,
            actual_value=f"{required_type_str}_count={len(active_of_type)}",
            reason=f"{len(active_of_type)} active {required_type_str} pool(s) present",
            evidence=[f"Pools: {[p.pool_id for p in active_of_type]}"],
        )
    return _liq_make_failed(
        condition,
        actual_value=f"{required_type_str}_count=0",
        reason=f"No active {required_type_str} pools detected",
    )


def _eval_liq_min_strength(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether at least one active pool meets the minimum strength."""
    min_strength_str = condition.min_strength
    if min_strength_str is None:
        return _liq_make_unavailable(condition, "No minimum strength configured")
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    strength_order = {"low": 1, "medium": 2, "high": 3}
    min_val = strength_order.get(min_strength_str, 1)
    active = [p for p in liquidity.pools if p.status == LiquidityPoolStatus.ACTIVE]
    qualifying = [
        p for p in active
        if strength_order.get(p.strength.value, 0) >= min_val
    ]
    if qualifying:
        return _liq_make_passed(
            condition,
            actual_value=f"qualifying_pools={len(qualifying)}, min_strength={min_strength_str}",
            reason=f"{len(qualifying)} active pool(s) meet minimum strength '{min_strength_str}'",
            evidence=[f"Qualifying: {[f'{p.pool_id}({p.strength.value})' for p in qualifying]}"],
        )
    return _liq_make_failed(
        condition,
        actual_value=f"qualifying_pools=0, min_strength={min_strength_str}",
        reason=f"No active pools meet minimum strength '{min_strength_str}'",
    )


def _eval_liq_equal_highs(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether equal highs pools exist."""
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    equal_highs = [
        p for p in liquidity.pools
        if p.pool_type == LiquidityPoolType.EQUAL_HIGHS
        and p.status == LiquidityPoolStatus.ACTIVE
    ]
    if equal_highs:
        return _liq_make_passed(
            condition,
            actual_value=f"equal_highs_count={len(equal_highs)}",
            reason=f"{len(equal_highs)} active equal highs pool(s) detected",
            evidence=[f"Pools: {[p.pool_id for p in equal_highs]}"],
        )
    return _liq_make_failed(
        condition,
        actual_value="equal_highs_count=0",
        reason="No active equal highs pools detected",
    )


def _eval_liq_equal_lows(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether equal lows pools exist."""
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    equal_lows = [
        p for p in liquidity.pools
        if p.pool_type == LiquidityPoolType.EQUAL_LOWS
        and p.status == LiquidityPoolStatus.ACTIVE
    ]
    if equal_lows:
        return _liq_make_passed(
            condition,
            actual_value=f"equal_lows_count={len(equal_lows)}",
            reason=f"{len(equal_lows)} active equal lows pool(s) detected",
            evidence=[f"Pools: {[p.pool_id for p in equal_lows]}"],
        )
    return _liq_make_failed(
        condition,
        actual_value="equal_lows_count=0",
        reason="No active equal lows pools detected",
    )


def _eval_liq_sweep_presence(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether any sweep events have occurred."""
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    if liquidity.sweeps:
        return _liq_make_passed(
            condition,
            actual_value=f"sweep_count={len(liquidity.sweeps)}",
            reason=f"{len(liquidity.sweeps)} sweep event(s) detected",
            evidence=[f"Sweeps: {[s.sweep_id for s in liquidity.sweeps[:5]]}"],
        )
    return _liq_make_failed(
        condition,
        actual_value="sweep_count=0",
        reason="No sweep events detected",
    )


def _eval_liq_sweep_direction(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether a sweep occurred on the required side."""
    required_side_str = condition.required_side
    if required_side_str is None:
        return _liq_make_unavailable(condition, "No required sweep side configured")
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    try:
        required_side = LiquiditySide(required_side_str)
    except ValueError:
        return _liq_make_unavailable(condition, f"Invalid required_side: {required_side_str}")
    matching_sweeps = [
        s for s in liquidity.sweeps if s.side == required_side
    ]
    if matching_sweeps:
        return _liq_make_passed(
            condition,
            actual_value=f"{required_side_str}_sweeps={len(matching_sweeps)}",
            reason=f"{len(matching_sweeps)} {required_side_str} sweep(s) detected",
            evidence=[f"Sweeps: {[s.sweep_id for s in matching_sweeps[:5]]}"],
        )
    return _liq_make_failed(
        condition,
        actual_value=f"{required_side_str}_sweeps=0",
        reason=f"No {required_side_str} sweep events detected",
    )


def _eval_liq_post_sweep_reaction(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether any sweep has the expected post-sweep reaction."""
    expected_reaction_str = condition.required_side  # Reuse field for expected reaction
    if expected_reaction_str is None:
        return _liq_make_unavailable(condition, "No expected reaction configured")
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    try:
        expected_reaction = PostSweepReaction(expected_reaction_str)
    except ValueError:
        return _liq_make_unavailable(condition, f"Invalid expected reaction: {expected_reaction_str}")
    matching = [
        s for s in liquidity.sweeps if s.reaction == expected_reaction
    ]
    if matching:
        return _liq_make_passed(
            condition,
            actual_value=f"matching_reactions={len(matching)}, reaction={expected_reaction_str}",
            reason=f"{len(matching)} sweep(s) with '{expected_reaction_str}' reaction",
            evidence=[f"Sweeps: {[s.sweep_id for s in matching[:5]]}"],
        )
    return _liq_make_failed(
        condition,
        actual_value=f"matching_reactions=0, reaction={expected_reaction_str}",
        reason=f"No sweeps with '{expected_reaction_str}' reaction found",
    )


def _eval_liq_max_proximity(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check whether nearest relevant liquidity is within max distance."""
    max_dist = condition.max_distance_pct
    if max_dist is None:
        return _liq_make_unavailable(condition, "No max distance configured")
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    # Determine which side to check based on strategy direction
    if direction == StrategyDirection.BULLISH:
        nearest = liquidity.nearest_buy_side_pool
        dist_pct = liquidity.distance_to_buy_side_pct
    elif direction == StrategyDirection.BEARISH:
        nearest = liquidity.nearest_sell_side_pool
        dist_pct = liquidity.distance_to_sell_side_pct
    else:
        # Neutral: check both sides
        nearest_buy = liquidity.nearest_buy_side_pool
        nearest_sell = liquidity.nearest_sell_side_pool
        dist_buy_pct = liquidity.distance_to_buy_side_pct
        dist_sell_pct = liquidity.distance_to_sell_side_pct
        # Use whichever is closer
        if dist_buy_pct is not None and dist_sell_pct is not None:
            if dist_buy_pct <= dist_sell_pct:
                nearest, dist_pct = nearest_buy, dist_buy_pct
            else:
                nearest, dist_pct = nearest_sell, dist_sell_pct
        elif dist_buy_pct is not None:
            nearest, dist_pct = nearest_buy, dist_buy_pct
        elif dist_sell_pct is not None:
            nearest, dist_pct = nearest_sell, dist_sell_pct
        else:
            nearest, dist_pct = None, None

    if dist_pct is None:
        return _liq_make_failed(
            condition,
            actual_value="distance_pct=None",
            reason="No active liquidity pools with calculable proximity",
        )
    if dist_pct <= max_dist:
        return _liq_make_passed(
            condition,
            actual_value=f"distance_pct={dist_pct:.4f}, max={max_dist}",
            reason=f"Nearest liquidity within {max_dist}% threshold ({dist_pct:.4f}%)",
            evidence=[f"Pool: {nearest.pool_id if nearest else 'none'}, distance: {dist_pct:.4f}%"],
        )
    return _liq_make_failed(
        condition,
        actual_value=f"distance_pct={dist_pct:.4f}, max={max_dist}",
        reason=f"Nearest liquidity at {dist_pct:.4f}% — exceeds {max_dist}% threshold",
        evidence=[f"Pool: {nearest.pool_id if nearest else 'none'}, distance: {dist_pct:.4f}%"],
    )


def _eval_liq_nearest_pool_state(
    condition: LiquidityConditionDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionResult:
    """Check the state (active/swept) of the nearest relevant pool."""
    if liquidity is None or liquidity.status != "available":
        return _liq_make_unavailable(condition, "Liquidity analysis not available")
    if direction == StrategyDirection.BULLISH:
        nearest = liquidity.nearest_buy_side_pool
    elif direction == StrategyDirection.BEARISH:
        nearest = liquidity.nearest_sell_side_pool
    else:
        nearest = liquidity.nearest_buy_side_pool or liquidity.nearest_sell_side_pool
    if nearest is None:
        return _liq_make_failed(
            condition,
            actual_value="nearest_pool=None",
            reason="No nearest liquidity pool detected",
        )
    if nearest.status == LiquidityPoolStatus.ACTIVE:
        return _liq_make_passed(
            condition,
            actual_value=f"pool_id={nearest.pool_id}, state=active",
            reason=f"Nearest pool '{nearest.pool_id}' is active",
            evidence=[f"Pool: {nearest.pool_id}, side: {nearest.side.value}, strength: {nearest.strength.value}"],
        )
    return _liq_make_failed(
        condition,
        actual_value=f"pool_id={nearest.pool_id}, state={nearest.status.value}",
        reason=f"Nearest pool '{nearest.pool_id}' is {nearest.status.value}, not active",
    )


# ---------------------------------------------------------------------------
# Liquidity condition evaluator registry
# ---------------------------------------------------------------------------

_LIQUIDITY_EVALUATORS = {
    "liq_active_pool_presence": _eval_liq_active_pool_presence,
    "liq_required_side": _eval_liq_required_side,
    "liq_pool_type": _eval_liq_pool_type,
    "liq_min_strength": _eval_liq_min_strength,
    "liq_equal_highs": _eval_liq_equal_highs,
    "liq_equal_lows": _eval_liq_equal_lows,
    "liq_sweep_presence": _eval_liq_sweep_presence,
    "liq_sweep_direction": _eval_liq_sweep_direction,
    "liq_post_sweep_reaction": _eval_liq_post_sweep_reaction,
    "liq_max_proximity": _eval_liq_max_proximity,
    "liq_nearest_pool_state": _eval_liq_nearest_pool_state,
}


def evaluate_liquidity_conditions(
    strategy: StrategyDefinition,
    liquidity: Optional[LiquidityAnalysisResult],
    direction: StrategyDirection,
) -> LiquidityConditionSummary:
    """
    Evaluate all liquidity conditions for a strategy.

    Handles policy (REQUIRED / OPTIONAL / NOT_USED) and unavailable data.
    Returns a structured LiquidityConditionSummary.
    """
    results: list[LiquidityConditionResult] = []

    for lcond in strategy.liquidity_conditions:
        # Skip NOT_USED conditions
        if lcond.policy == LiquidityConditionPolicy.NOT_USED:
            results.append(LiquidityConditionResult(
                condition_id=lcond.condition_id,
                condition_name=lcond.condition_name,
                description=lcond.description,
                policy=lcond.policy,
                status=ConditionStatus.PASSED,
                expected_value="not_used",
                actual_value="not_used",
                reason="Condition is NOT_USED — skipped",
            ))
            continue

        evaluator = _LIQUIDITY_EVALUATORS.get(lcond.condition_id)
        if evaluator is None:
            results.append(_liq_make_unavailable(lcond, f"No evaluator for liquidity condition '{lcond.condition_id}'"))
            continue

        result = evaluator(lcond, liquidity, direction)
        results.append(result)

    # Compute aggregates
    required_results = [r for r in results if r.policy == LiquidityConditionPolicy.REQUIRED]
    optional_results = [r for r in results if r.policy == LiquidityConditionPolicy.OPTIONAL]

    required_passed = sum(1 for r in required_results if r.status == ConditionStatus.PASSED)
    required_failed = sum(1 for r in required_results if r.status == ConditionStatus.FAILED)
    required_unavailable = sum(1 for r in required_results if r.status == ConditionStatus.UNAVAILABLE)
    optional_passed = sum(1 for r in optional_results if r.status == ConditionStatus.PASSED)
    optional_failed = sum(1 for r in optional_results if r.status == ConditionStatus.FAILED)
    optional_unavailable = sum(1 for r in optional_results if r.status == ConditionStatus.UNAVAILABLE)

    any_required_failed = required_failed > 0

    # Determine overall availability
    if liquidity is None or liquidity.status != "available":
        avail_status = LiquidityAvailabilityStatus(
            status=LiquidityAvailability.UNAVAILABLE,
            reason="Liquidity analysis data not provided or unavailable",
        )
        available = False
    elif not strategy.liquidity_conditions:
        avail_status = LiquidityAvailabilityStatus(
            status=LiquidityAvailability.NOT_EVALUATED,
            reason="No liquidity conditions defined for this strategy",
        )
        available = False
    else:
        avail_status = LiquidityAvailabilityStatus(
            status=LiquidityAvailability.AVAILABLE,
            reason="Liquidity data available and conditions evaluated",
        )
        available = True

    return LiquidityConditionSummary(
        available=available,
        availability_status=avail_status,
        condition_results=results,
        required_passed=required_passed,
        required_failed=required_failed,
        required_unavailable=required_unavailable,
        optional_passed=optional_passed,
        optional_failed=optional_failed,
        optional_unavailable=optional_unavailable,
        any_required_failed=any_required_failed,
    )
