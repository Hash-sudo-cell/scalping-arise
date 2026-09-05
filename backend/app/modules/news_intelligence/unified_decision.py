"""
Scalping Arise — Unified Intelligence Decision Engine

Combines event risk and strategy performance state into a single
ALLOW / RESTRICT / BLOCK decision with explicit reasons.

This is the core synthesis layer of Phase 8 — it produces
the decision that Phase 7 consumes before trade planning.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.modules.news_intelligence.config import NewsIntelligenceSettings, get_news_intelligence_settings
from app.modules.news_intelligence.models import (
    EventDataStatus,
    EventDecision,
    EventIntelligenceSummaryAgg,
    EventRiskResult,
    FailPolicy,
    IntelligenceContext,
    IntelligenceDecision,
    OverallDecision,
    StrategyPerformanceMetrics,
    StrategyPerformanceState,
    StrategyStateRecord,
)


def synthesize_decision(
    instrument: str,
    context: IntelligenceContext,
    signal_id: Optional[str] = None,
    strategy_id: Optional[str] = None,
    settings: NewsIntelligenceSettings | None = None,
) -> IntelligenceDecision:
    """
    Synthesize a unified intelligence decision from event and strategy context.

    Decision matrix:
        Event=BLOCK  → BLOCK (always — events are time-critical)
        Strategy=DISABLED → BLOCK (strategy too risky)
        Event=RESTRICT + Strategy=RESTRICTED → BLOCK
        Event=RESTRICT + Strategy=ACTIVE/MONITORED → RESTRICT
        Strategy=RESTRICTED + Event=ALLOW → RESTRICT
        Event=RESTRICT only → RESTRICT
        Strategy=RESTRICTED only → RESTRICT
        All clear → ALLOW
    """
    settings = settings or get_news_intelligence_settings()
    reasons: list[str] = []
    restrictions: list[str] = []

    # --- Extract decisions ---
    event_decision = EventDecision.ALLOW
    strategy_state = StrategyPerformanceState.ACTIVE

    if context.event_summary is not None:
        event_decision = context.event_summary.event_decision

    if context.strategy_state is not None:
        strategy_state = context.strategy_state.state

    # --- Resolve fail policy for unavailable data ---
    if context.event_data_status in (EventDataStatus.UNAVAILABLE, EventDataStatus.STALE):
        fallback = context.fallback_policy
        if fallback == FailPolicy.FAIL_CLOSED:
            reasons.append(
                f"Event data {context.event_data_status.value} — fail_closed policy active"
            )
            restrictions.append("No recent event data — operating under caution")
            return IntelligenceDecision(
                instrument=instrument,
                signal_id=signal_id,
                strategy_id=strategy_id,
                overall_decision=OverallDecision.RESTRICT,
                event_decision=event_decision,
                strategy_state=strategy_state,
                event_context=context.event_summary,
                strategy_performance_context=(
                    context.strategy_state.metrics if context.strategy_state else None
                ),
                restrictions=restrictions,
                reasons=reasons,
                event_data_status=context.event_data_status,
            )
        else:
            reasons.append(
                f"Event data {context.event_data_status.value} — fail_open policy — allowing"
            )
            # Fall through to normal decision logic

    # --- Decision matrix ---

    # Event BLOCK → always BLOCK
    if event_decision == EventDecision.BLOCK:
        reasons.append("Event decision is BLOCK — overriding all")
        return IntelligenceDecision(
            instrument=instrument,
            signal_id=signal_id,
            strategy_id=strategy_id,
            overall_decision=OverallDecision.BLOCK,
            event_decision=event_decision,
            strategy_state=strategy_state,
            event_context=context.event_summary,
            strategy_performance_context=(
                context.strategy_state.metrics if context.strategy_state else None
            ),
            restrictions=restrictions,
            reasons=reasons,
            event_data_status=context.event_data_status,
        )

    # Strategy DISABLED → always BLOCK
    if strategy_state == StrategyPerformanceState.DISABLED:
        reasons.append("Strategy state is DISABLED — blocking")
        return IntelligenceDecision(
            instrument=instrument,
            signal_id=signal_id,
            strategy_id=strategy_id,
            overall_decision=OverallDecision.BLOCK,
            event_decision=event_decision,
            strategy_state=strategy_state,
            event_context=context.event_summary,
            strategy_performance_context=(
                context.strategy_state.metrics if context.strategy_state else None
            ),
            restrictions=restrictions,
            reasons=reasons,
            event_data_status=context.event_data_status,
        )

    # Both RESTRICT → BLOCK
    if (
        event_decision == EventDecision.RESTRICT
        and strategy_state == StrategyPerformanceState.RESTRICTED
    ):
        reasons.append("Both event RESTRICT and strategy RESTRICTED → BLOCK")
        return IntelligenceDecision(
            instrument=instrument,
            signal_id=signal_id,
            strategy_id=strategy_id,
            overall_decision=OverallDecision.BLOCK,
            event_decision=event_decision,
            strategy_state=strategy_state,
            event_context=context.event_summary,
            strategy_performance_context=(
                context.strategy_state.metrics if context.strategy_state else None
            ),
            restrictions=restrictions,
            reasons=reasons,
            event_data_status=context.event_data_status,
        )

    # Event RESTRICT alone → RESTRICT
    if event_decision == EventDecision.RESTRICT:
        restrictions.append("Event risk — exercise caution")
        reasons.append("Event decision is RESTRICT")
        return IntelligenceDecision(
            instrument=instrument,
            signal_id=signal_id,
            strategy_id=strategy_id,
            overall_decision=OverallDecision.RESTRICT,
            event_decision=event_decision,
            strategy_state=strategy_state,
            event_context=context.event_summary,
            strategy_performance_context=(
                context.strategy_state.metrics if context.strategy_state else None
            ),
            restrictions=restrictions,
            reasons=reasons,
            event_data_status=context.event_data_status,
        )

    # Strategy RESTRICTED alone → RESTRICT
    if strategy_state == StrategyPerformanceState.RESTRICTED:
        restrictions.append("Strategy underperforming — reduced exposure recommended")
        reasons.append("Strategy state is RESTRICTED")
        return IntelligenceDecision(
            instrument=instrument,
            signal_id=signal_id,
            strategy_id=strategy_id,
            overall_decision=OverallDecision.RESTRICT,
            event_decision=event_decision,
            strategy_state=strategy_state,
            event_context=context.event_summary,
            strategy_performance_context=(
                context.strategy_state.metrics if context.strategy_state else None
            ),
            restrictions=restrictions,
            reasons=reasons,
            event_data_status=context.event_data_status,
        )

    # Strategy MONITORED — include observation but ALLOW
    if strategy_state == StrategyPerformanceState.MONITORED:
        restrictions.append("Strategy performance being monitored")
        reasons.append("Strategy state is MONITORED — allowed with observation")

    # Default: ALLOW
    reasons.append("No blocking or restricting conditions detected")
    return IntelligenceDecision(
        instrument=instrument,
        signal_id=signal_id,
        strategy_id=strategy_id,
        overall_decision=OverallDecision.ALLOW,
        event_decision=event_decision,
        strategy_state=strategy_state,
        event_context=context.event_summary,
        strategy_performance_context=(
            context.strategy_state.metrics if context.strategy_state else None
        ),
        restrictions=restrictions,
        reasons=reasons,
        event_data_status=context.event_data_status,
    )
