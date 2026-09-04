"""
Scalping Arise — Invalidation Evaluator

Evaluates strategy-specific invalidation rules against current market data
and liquidity context.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.market_analysis.models import (
    AnalysisResult,
    BOSDirection,
    LiquidityAnalysisResult,
    LiquidityPool,
    LiquidityPoolStatus,
    LiquiditySide,
    LiquidityStrength,
    PostSweepReaction,
    StructureLabel,
)
from app.modules.market_analysis.models import (
    MarketRegime,
    TrendState,
)
from app.modules.strategies.models import (
    InvalidationResult,
    InvalidationRule,
    StrategyDefinition,
    StrategyDirection,
)

logger = logging.getLogger(__name__)


def evaluate_invalidation_rules(
    strategy: StrategyDefinition,
    analysis: Optional[AnalysisResult],
    direction: StrategyDirection,
    regime_state: Optional[str],
    liquidity: Optional[LiquidityAnalysisResult] = None,
) -> list[InvalidationResult]:
    """
    Evaluate all invalidation rules for a strategy.

    Now includes liquidity context for liquidity-aware invalidation.
    Returns a list of InvalidationResult for each rule.
    """
    results: list[InvalidationResult] = []

    # Evaluate core invalidation rules
    for rule in strategy.invalidation_rules:
        result = _evaluate_rule(rule, strategy, analysis, direction, regime_state, liquidity)
        results.append(result)

    # Evaluate liquidity-specific invalidation rules
    for rule in strategy.liquidity_invalidation_rules:
        result = _evaluate_rule(rule, strategy, analysis, direction, regime_state, liquidity)
        results.append(result)

    return results


def _evaluate_rule(
    rule: InvalidationRule,
    strategy: StrategyDefinition,
    analysis: Optional[AnalysisResult],
    direction: StrategyDirection,
    regime_state: Optional[str],
    liquidity: Optional[LiquidityAnalysisResult] = None,
) -> InvalidationResult:
    """Dispatch to the appropriate rule evaluator."""
    evaluator = _RULE_EVALUATORS.get(rule.rule_id)
    if evaluator is None:
        # Unknown rule — not triggered
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="No evaluator for this rule",
        )
    # Liquidity evaluators receive liquidity parameter
    if rule.rule_id.startswith("tc_liq_") or rule.rule_id.startswith("pc_liq_") or rule.rule_id.startswith("rr_liq_"):
        return evaluator(rule, strategy, analysis, direction, regime_state, liquidity)
    return evaluator(rule, strategy, analysis, direction, regime_state)


def _eval_tc_inval_choch(rule, strategy, analysis, direction, regime_state):
    """Trend Continuation: CHOCH against trend direction."""
    if analysis is None or analysis.events is None:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="Events analysis not available",
        )
    choch_events = analysis.events.choch
    if not choch_events:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="No CHOCH events detected",
        )
    if direction == StrategyDirection.BULLISH:
        bearish_choch = [e for e in choch_events if e.direction == BOSDirection.BEARISH_BOS or "bearish" in e.direction.value]
        if bearish_choch:
            return InvalidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                description=rule.description,
                triggered=True,
                reason=f"Bearish CHOCH detected against bullish trend",
                evidence=[f"CHOCH: {e.direction.value} at {e.break_price}" for e in bearish_choch],
            )
    elif direction == StrategyDirection.BEARISH:
        bullish_choch = [e for e in choch_events if e.direction == BOSDirection.BULLISH_BOS or "bullish" in e.direction.value]
        if bullish_choch:
            return InvalidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                description=rule.description,
                triggered=True,
                reason=f"Bullish CHOCH detected against bearish trend",
                evidence=[f"CHOCH: {e.direction.value} at {e.break_price}" for e in bullish_choch],
            )
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=False,
        reason="No CHOCH against trend direction",
    )


def _eval_tc_inval_regime_shift(rule, strategy, analysis, direction, regime_state):
    """Trend Continuation: regime shifted to ranging."""
    if regime_state is None:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="Regime not available",
        )
    if regime_state == "ranging":
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=True,
            reason="Market regime shifted to ranging — trend continuation invalidated",
            evidence=[f"Regime: {regime_state}"],
        )
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=False,
        reason=f"Regime is {regime_state} — still trending",
    )


def _eval_pc_inval_structure_break(rule, strategy, analysis, direction, regime_state):
    """Pullback Continuation: structure break against primary trend."""
    if analysis is None or analysis.events is None:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="Events analysis not available",
        )
    bos_events = analysis.events.bos
    if not bos_events:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="No BOS events detected",
        )
    if direction == StrategyDirection.BULLISH:
        bearish_bos = [e for e in bos_events if e.direction == BOSDirection.BEARISH_BOS]
        if bearish_bos:
            return InvalidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                description=rule.description,
                triggered=True,
                reason="Bearish BOS detected against bullish primary trend",
                evidence=[f"BOS: {e.direction.value} at {e.break_price}" for e in bearish_bos],
            )
    elif direction == StrategyDirection.BEARISH:
        bullish_bos = [e for e in bos_events if e.direction == BOSDirection.BULLISH_BOS]
        if bullish_bos:
            return InvalidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                description=rule.description,
                triggered=True,
                reason="Bullish BOS detected against bearish primary trend",
                evidence=[f"BOS: {e.direction.value} at {e.break_price}" for e in bullish_bos],
            )
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=False,
        reason="No structure break against primary trend",
    )


def _eval_pc_inval_regime_shift(rule, strategy, analysis, direction, regime_state):
    """Pullback Continuation: regime shifted to ranging."""
    if regime_state is None:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="Regime not available",
        )
    if regime_state == "ranging":
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=True,
            reason="Market regime shifted to ranging — pullback continuation invalidated",
            evidence=[f"Regime: {regime_state}"],
        )
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=False,
        reason=f"Regime is {regime_state} — still trending",
    )


def _eval_pc_inval_deep_pullback(rule, strategy, analysis, direction, regime_state):
    """Pullback Continuation: pullback too deep (>61.8%)."""
    # This requires price data to calculate pullback depth
    # With current Phase 3/4 data, we can approximate from structure
    if analysis is None or analysis.structure is None:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="Structure data not available for depth calculation",
        )
    labels = analysis.structure.latest_labels
    if not labels or len(labels) < 4:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="Insufficient structure labels to assess pullback depth",
        )
    # Simplified: if there are many consecutive counter-trend labels, pullback may be deep
    recent = labels[-5:]
    if direction == StrategyDirection.BULLISH:
        counter_count = sum(1 for l in recent if l in (StructureLabel.LH, StructureLabel.LL))
    else:
        counter_count = sum(1 for l in recent if l in (StructureLabel.HH, StructureLabel.HL))
    if counter_count >= 3:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=True,
            reason=f"Pullback may be deep — {counter_count} consecutive counter-trend labels",
            evidence=[f"Counter-trend labels: {counter_count} of {len(recent)}"],
        )
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=False,
        reason=f"Pullback depth appears within range ({counter_count} counter-trend labels)",
    )


def _eval_rr_inval_regime_change(rule, strategy, analysis, direction, regime_state):
    """Range Reversal: regime changed to trending."""
    if regime_state is None:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="Regime not available",
        )
    if regime_state in ("trending_up", "trending_down"):
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=True,
            reason=f"Market regime shifted to {regime_state} — range reversal invalidated",
            evidence=[f"Regime: {regime_state}"],
        )
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=False,
        reason=f"Regime is {regime_state} — still ranging",
    )


def _eval_rr_inval_breakout(rule, strategy, analysis, direction, regime_state):
    """Range Reversal: strong breakout beyond range."""
    if analysis is None or analysis.events is None:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="Events analysis not available",
        )
    bos_events = analysis.events.bos
    if not bos_events:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="No BOS events — no breakout detected",
        )
    # Any BOS in a ranging market suggests a breakout
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=True,
        reason=f"BOS event detected in ranging market — possible breakout",
        evidence=[f"BOS: {e.direction.value} at {e.break_price}" for e in bos_events[:3]],
    )


# ---------------------------------------------------------------------------
# Liquidity-aware invalidation evaluators
# ---------------------------------------------------------------------------

def _eval_tc_liq_inval_opposing_sweep(rule, strategy, analysis, direction, regime_state, liquidity=None):
    """Trend Continuation: opposing sweep against trend direction."""
    if liquidity is None or liquidity.status != "available" or not liquidity.sweeps:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="No liquidity sweep data available",
        )
    # Sweeps against the trend direction
    if direction == StrategyDirection.BULLISH:
        opposing = [s for s in liquidity.sweeps if s.side == LiquiditySide.SELL_SIDE and s.strength in (LiquidityStrength.HIGH, LiquidityStrength.MEDIUM)]
    elif direction == StrategyDirection.BEARISH:
        opposing = [s for s in liquidity.sweeps if s.side == LiquiditySide.BUY_SIDE and s.strength in (LiquidityStrength.HIGH, LiquidityStrength.MEDIUM)]
    else:
        opposing = []
    if opposing:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=True,
            reason=f"Strong opposing liquidity sweep(s) detected against {direction.value} trend",
            evidence=[f"Sweep {s.sweep_id}: {s.side.value}, strength={s.strength.value}" for s in opposing[:3]],
        )
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=False,
        reason="No opposing liquidity sweep detected",
    )


def _eval_pc_liq_inval_opposing_sweep(rule, strategy, analysis, direction, regime_state, liquidity=None):
    """Pullback Continuation: opposing sweep against trend direction."""
    if liquidity is None or liquidity.status != "available" or not liquidity.sweeps:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="No liquidity sweep data available",
        )
    if direction == StrategyDirection.BULLISH:
        opposing = [s for s in liquidity.sweeps if s.side == LiquiditySide.SELL_SIDE and s.strength in (LiquidityStrength.HIGH, LiquidityStrength.MEDIUM)]
    elif direction == StrategyDirection.BEARISH:
        opposing = [s for s in liquidity.sweeps if s.side == LiquiditySide.BUY_SIDE and s.strength in (LiquidityStrength.HIGH, LiquidityStrength.MEDIUM)]
    else:
        opposing = []
    if opposing:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=True,
            reason=f"Strong opposing liquidity sweep(s) detected against {direction.value} trend",
            evidence=[f"Sweep {s.sweep_id}: {s.side.value}, strength={s.strength.value}" for s in opposing[:3]],
        )
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=False,
        reason="No opposing liquidity sweep detected",
    )


def _eval_rr_liq_inval_acceptance_after_sweep(rule, strategy, analysis, direction, regime_state, liquidity=None):
    """Range Reversal: acceptance after sweep (price stays beyond pool level)."""
    if liquidity is None or liquidity.status != "available" or not liquidity.sweeps:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=False,
            reason="No liquidity sweep data available",
        )
    # Check for sweeps with ACCEPTANCE reaction (invalidation signal)
    acceptance_sweeps = [
        s for s in liquidity.sweeps
        if s.reaction == PostSweepReaction.ACCEPTANCE
    ]
    if acceptance_sweeps:
        return InvalidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            description=rule.description,
            triggered=True,
            reason=f"Sweep with ACCEPTANCE reaction detected — price may have accepted beyond pool level",
            evidence=[f"Sweep {s.sweep_id}: {s.side.value}, reaction={s.reaction.value}" for s in acceptance_sweeps[:3]],
        )
    return InvalidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        description=rule.description,
        triggered=False,
        reason="No sweep with acceptance reaction detected",
    )


# ---------------------------------------------------------------------------
# Rule evaluator registry
# ---------------------------------------------------------------------------

_RULE_EVALUATORS = {
    "tc_inval_choch": _eval_tc_inval_choch,
    "tc_inval_regime_shift": _eval_tc_inval_regime_shift,
    "tc_liq_inval_opposing_sweep": _eval_tc_liq_inval_opposing_sweep,
    "pc_inval_structure_break": _eval_pc_inval_structure_break,
    "pc_inval_regime_shift": _eval_pc_inval_regime_shift,
    "pc_inval_deep_pullback": _eval_pc_inval_deep_pullback,
    "pc_liq_inval_opposing_sweep": _eval_pc_liq_inval_opposing_sweep,
    "rr_inval_regime_change": _eval_rr_inval_regime_change,
    "rr_inval_breakout": _eval_rr_inval_breakout,
    "rr_liq_inval_acceptance_after_sweep": _eval_rr_liq_inval_acceptance_after_sweep,
}
