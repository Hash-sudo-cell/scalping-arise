"""
Scalping Arise — Explainability Builder

Constructs human-readable reason chains for FinalDecision outputs.
Every decision gets a full explainability trace.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.decision.models import (
    ExplainabilityChain,
    FinalDecision,
    FinalDecisionDirection,
    FinalDecisionState,
    GateName,
    GateResult,
    GateStatus,
    ProvenanceSource,
    ReasonItem,
)

logger = logging.getLogger(__name__)


def build_explainability(
    decision: FinalDecision,
    *,
    signal_direction: Optional[str] = None,
    signal_instrument: Optional[str] = None,
) -> ExplainabilityChain:
    """
    Build a complete explainability chain for a decision.

    Analyzes the gate results and decision state to construct
    a human-readable explanation of why the decision was made.

    Args:
        decision: The decision to explain.
        signal_direction: The original signal direction (buy/sell).
        signal_instrument: The instrument being traded.

    Returns:
        ExplainabilityChain with reasons, factors, and summary.
    """
    reasons: list[ReasonItem] = []
    contributing: list[str] = []
    blocking: list[str] = []
    confidence_breakdown: dict[str, float] = {}

    # Analyze each gate result
    for gate_result in decision.gates:
        _analyze_gate(gate_result, reasons, contributing, blocking, confidence_breakdown)

    # Build summary
    summary = _build_summary(decision, signal_direction, signal_instrument)

    # Sort reasons by weight (highest first)
    reasons.sort(key=lambda r: r.weight, reverse=True)

    return ExplainabilityChain(
        summary=summary,
        reasons=reasons,
        contributing_factors=contributing,
        blocking_factors=blocking,
        confidence_breakdown=confidence_breakdown,
    )


def _analyze_gate(
    gate: GateResult,
    reasons: list[ReasonItem],
    contributing: list[str],
    blocking: list[str],
    confidence_breakdown: dict[str, float],
) -> None:
    """Analyze a single gate result and add to the reason chain."""
    if gate.status == GateStatus.PASSED:
        reasons.append(ReasonItem(
            code=f"{gate.gate.value}_passed",
            message=gate.reason,
            source=ProvenanceSource.DECISION_ENGINE,
            weight=0.5,
            evidence=[gate.reason],
        ))
        contributing.append(gate.gate.value)

        # Extract confidence/quality signals for breakdown
        if gate.gate in (GateName.SIGNAL_CONFIDENCE, GateName.SIGNAL_QUALITY):
            if "confidence" in gate.details:
                confidence_breakdown[gate.gate.value] = float(gate.details["confidence"])
            elif "quality" in gate.details:
                confidence_breakdown[gate.gate.value] = float(gate.details["quality"])

    elif gate.status == GateStatus.FAILED:
        reasons.append(ReasonItem(
            code=f"{gate.gate.value}_failed",
            message=gate.reason,
            source=ProvenanceSource.DECISION_ENGINE,
            weight=1.0,
            evidence=[gate.reason],
        ))
        blocking.append(gate.gate.value)

    elif gate.status == GateStatus.SKIPPED:
        reasons.append(ReasonItem(
            code=f"{gate.gate.value}_skipped",
            message=gate.reason,
            source=ProvenanceSource.DECISION_ENGINE,
            weight=0.2,
            evidence=[gate.reason],
        ))

    elif gate.status == GateStatus.ERROR:
        reasons.append(ReasonItem(
            code=f"{gate.gate.value}_error",
            message=gate.reason,
            source=ProvenanceSource.DECISION_ENGINE,
            weight=0.8,
            evidence=[gate.reason],
        ))
        blocking.append(gate.gate.value)


def _build_summary(
    decision: FinalDecision,
    signal_direction: Optional[str],
    signal_instrument: Optional[str],
) -> str:
    """Build a one-line summary of the decision rationale."""
    instrument = signal_instrument or decision.instrument
    direction_str = signal_direction or decision.direction.value

    state = decision.state
    if state == FinalDecisionState.ACTIONABLE:
        return (
            f"DECISION: {direction_str.upper()} {instrument} — "
            f"all gates passed, confidence {decision.confidence}%, "
            f"quality {decision.quality}%"
        )
    if state == FinalDecisionState.BLOCKED:
        blocked_by = decision.blocked_by_gate.value if decision.blocked_by_gate else "unknown"
        return (
            f"DECISION: BLOCKED {instrument} — "
            f"gate '{blocked_by}' failed: {decision.rejection_reason or 'unspecified'}"
        )
    if state == FinalDecisionState.NO_TRADE:
        return (
            f"DECISION: NO TRADE {instrument} — "
            f"insufficient quality/confidence or plan invalid"
        )
    if state == FinalDecisionState.INVALID:
        return (
            f"DECISION: INVALID {instrument} — "
            f"{decision.rejection_reason or 'missing required data'}"
        )
    if state == FinalDecisionState.EXPIRED:
        return f"DECISION: EXPIRED {instrument} — TTL elapsed"
    if state == FinalDecisionState.WAITING:
        return f"DECISION: WAITING {instrument} — pending upstream data"
    if state == FinalDecisionState.EVALUATING:
        return f"DECISION: EVALUATING {instrument} — pipeline in progress"
    return f"DECISION: {state.value.upper()} {instrument}"


def add_signal_context(
    chain: ExplainabilityChain,
    signal_record: object,
) -> ExplainabilityChain:
    """
    Enrich the explainability chain with signal-specific context.

    Args:
        chain: The existing explainability chain.
        signal_record: The Phase 6 SignalRecord (typed as object for loose coupling).

    Returns:
        The enriched chain (mutates in-place and returns for chaining).
    """
    try:
        direction = getattr(signal_record, "direction", None)
        if direction:
            chain.reasons.append(ReasonItem(
                code="signal_direction",
                message=f"Signal direction: {direction.value if hasattr(direction, 'value') else direction}",
                source=ProvenanceSource.SIGNAL_ENGINE,
                weight=0.7,
            ))

        confidence = getattr(signal_record, "confidence", None)
        if confidence and hasattr(confidence, "confidence_0_100"):
            chain.confidence_breakdown["signal_engine"] = float(confidence.confidence_0_100)

        quality = getattr(signal_record, "quality", None)
        if quality and hasattr(quality, "score"):
            chain.confidence_breakdown["signal_quality"] = float(quality.score)
    except Exception:
        logger.debug("Failed to extract signal context for explainability")

    return chain


def add_plan_context(
    chain: ExplainabilityChain,
    plan: object,
) -> ExplainabilityChain:
    """
    Enrich the explainability chain with trade plan context.

    Args:
        chain: The existing explainability chain.
        plan: The Phase 7 TradePlan (typed as object for loose coupling).

    Returns:
        The enriched chain (mutates in-place and returns for chaining).
    """
    try:
        side = getattr(plan, "side", None)
        if side:
            chain.reasons.append(ReasonItem(
                code="plan_side",
                message=f"Trade plan side: {side.value if hasattr(side, 'value') else side}",
                source=ProvenanceSource.TRADE_PLANNING,
                weight=0.6,
            ))

        risk_reward = getattr(plan, "risk_reward", None)
        if risk_reward is not None:
            chain.confidence_breakdown["plan_risk_reward"] = float(risk_reward)
    except Exception:
        logger.debug("Failed to extract plan context for explainability")

    return chain
