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
    MarketRegime,
    StructureLabel,
    TrendState,
)
from app.modules.strategies.models import (
    ConditionCriticality,
    ConditionDefinition,
    ConditionResult,
    ConditionStatus,
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
