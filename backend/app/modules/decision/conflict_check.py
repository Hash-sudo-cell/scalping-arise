"""
Scalping Arise — Conflict Detection

Detects conflicts between signal evaluation, trade plans,
and intelligence decisions.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.decision.models import (
    ConflictDetail,
    ConflictReport,
    ConflictType,
    FinalDecisionDirection,
)

logger = logging.getLogger(__name__)


def check_direction_conflict(
    signal_direction: Optional[str],
    plan_side: Optional[str],
) -> Optional[ConflictDetail]:
    """
    Check for direction mismatch between signal and plan.

    Args:
        signal_direction: Signal direction (buy/sell).
        plan_side: Plan side (long/short).

    Returns:
        ConflictDetail if conflict detected, None otherwise.
    """
    if signal_direction is None or plan_side is None:
        return None

    # Normalize: buy=long, sell=short
    direction_map = {"buy": "long", "sell": "short", "long": "long", "short": "short"}
    norm_signal = direction_map.get(signal_direction.lower(), signal_direction.lower())
    norm_plan = direction_map.get(plan_side.lower(), plan_side.lower())

    if norm_signal != norm_plan:
        return ConflictDetail(
            conflict_type=ConflictType.DIRECTION_MISMATCH,
            description=(
                f"Signal direction '{signal_direction}' contradicts "
                f"plan side '{plan_side}'"
            ),
            severity=0.9,
            involved_components=["signal_engine", "trade_planning"],
            resolution="Blocked — direction mismatch is a critical conflict",
        )

    return None


def check_confidence_contradiction(
    signal_confidence: Optional[int],
    plan_risk_reward: Optional[float],
    min_confidence: int = 50,
    min_rr: float = 1.5,
) -> Optional[ConflictDetail]:
    """
    Check for confidence/quality contradiction.

    High confidence but low R:R or vice versa suggests contradictory signals.
    """
    if signal_confidence is None or plan_risk_reward is None:
        return None

    high_conf = signal_confidence >= 70
    low_rr = plan_risk_reward < min_rr

    if high_conf and low_rr:
        return ConflictDetail(
            conflict_type=ConflictType.CONFIDENCE_CONTRADICTION,
            description=(
                f"High signal confidence ({signal_confidence}%) but "
                f"low R:R ({plan_risk_reward:.2f} < {min_rr})"
            ),
            severity=0.6,
            involved_components=["signal_engine", "trade_planning"],
            resolution="Logged as warning — confidence and risk assessment disagree",
        )

    return None


def check_intelligence_veto(
    event_decision: Optional[str],
    strategy_state: Optional[str],
) -> Optional[ConflictDetail]:
    """
    Check if intelligence has vetoed the trade.
    """
    if event_decision == "block":
        return ConflictDetail(
            conflict_type=ConflictType.INTELLIGENCE_VETO,
            description="Event intelligence issued a BLOCK decision",
            severity=0.95,
            involved_components=["news_intelligence"],
            resolution="Blocked — intelligence veto is authoritative",
        )

    if strategy_state == "disabled":
        return ConflictDetail(
            conflict_type=ConflictType.STRATEGY_STATE_BLOCK,
            description=f"Strategy is in DISABLED state",
            severity=1.0,
            involved_components=["news_intelligence"],
            resolution="Blocked — disabled strategy cannot trade",
        )

    return None


def detect_conflicts(
    *,
    signal_direction: Optional[str] = None,
    plan_side: Optional[str] = None,
    signal_confidence: Optional[int] = None,
    plan_risk_reward: Optional[float] = None,
    event_decision: Optional[str] = None,
    strategy_state: Optional[str] = None,
    plan_within_risk_limits: Optional[bool] = None,
    min_confidence: int = 50,
    min_rr: float = 1.5,
) -> ConflictReport:
    """
    Run all conflict checks and produce an aggregated report.

    Returns:
        ConflictReport with all detected conflicts and overall severity.
    """
    conflicts: list[ConflictDetail] = []

    # Direction conflict
    direction_conflict = check_direction_conflict(signal_direction, plan_side)
    if direction_conflict:
        conflicts.append(direction_conflict)

    # Confidence contradiction
    confidence_conflict = check_confidence_contradiction(
        signal_confidence, plan_risk_reward, min_confidence, min_rr
    )
    if confidence_conflict:
        conflicts.append(confidence_conflict)

    # Intelligence veto
    veto_conflict = check_intelligence_veto(event_decision, strategy_state)
    if veto_conflict:
        conflicts.append(veto_conflict)

    # Risk limit breach
    if plan_within_risk_limits is False:
        conflicts.append(ConflictDetail(
            conflict_type=ConflictType.RISK_LIMIT_BREACH,
            description="Trade plan exceeds configured risk limits",
            severity=0.8,
            involved_components=["trade_planning"],
            resolution="Blocked — risk limits are hard constraints",
        ))

    # Aggregate severity
    overall_severity = 0.0
    if conflicts:
        overall_severity = max(c.severity for c in conflicts)

    # Determine resolution
    resolution = ""
    if not conflicts:
        resolution = "No conflicts detected"
    elif overall_severity >= 0.8:
        resolution = "Critical conflict — decision blocked"
    else:
        resolution = "Minor conflicts — decision allowed with caution"

    return ConflictReport(
        has_conflicts=len(conflicts) > 0,
        conflicts=conflicts,
        overall_severity=overall_severity,
        resolution_applied=resolution,
    )
