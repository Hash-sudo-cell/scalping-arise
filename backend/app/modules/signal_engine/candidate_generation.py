"""
Scalping Arise — Signal Candidate Generation

Extracts directional signal candidates from qualified strategy evaluation results.
Only strategies with QUALIFIED status and a non-NONE direction produce candidates.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.signal_engine.models import (
    ConfidenceScore,
    EvidenceItem,
    SignalCandidate,
    SignalDirection,
)
from app.modules.strategies.models import (
    StrategyDirection,
    StrategyEvaluationResult,
    StrategyEvaluationStatus,
)

logger = logging.getLogger(__name__)

# Map strategy directions to signal directions
_DIRECTION_MAP: dict[StrategyDirection, SignalDirection] = {
    StrategyDirection.BULLISH: SignalDirection.LONG,
    StrategyDirection.BEARISH: SignalDirection.SHORT,
    StrategyDirection.NEUTRAL: SignalDirection.NONE,
    StrategyDirection.NONE: SignalDirection.NONE,
}


def _strategy_direction_to_signal(
    strategy_dir: StrategyDirection,
) -> SignalDirection:
    """Convert a StrategyDirection to a SignalDirection."""
    return _DIRECTION_MAP.get(strategy_dir, SignalDirection.NONE)


def _extract_condition_pass_rate(
    result: StrategyEvaluationResult,
) -> float:
    """Calculate the fraction of required conditions that passed."""
    required = [
        cr for cr in result.condition_results
        if cr.criticality.value in ("critical", "required")
    ]
    if not required:
        return 1.0
    passed = sum(1 for cr in required if cr.status.value == "passed")
    return passed / len(required)


def _collect_evidence(
    result: StrategyEvaluationResult,
    direction: SignalDirection,
) -> list[str]:
    """Collect evidence strings from a strategy evaluation result."""
    evidence: list[str] = []

    # Market regime
    if result.market_regime:
        evidence.append(f"regime:{result.market_regime}")

    # Condition evidence
    for cr in result.condition_results:
        if cr.status.value == "passed" and cr.evidence:
            for e in cr.evidence:
                evidence.append(f"condition:{cr.condition_id}:{e}")

    # Liquidity evidence
    if result.liquidity_summary and result.liquidity_summary.condition_results:
        for lr in result.liquidity_summary.condition_results:
            if lr.status.value == "passed" and lr.evidence:
                for e in lr.evidence:
                    evidence.append(f"liquidity:{lr.condition_id}:{e}")

    # Structure summary
    if result.market_structure_summary:
        evidence.append(f"structure:{result.market_structure_summary}")

    return evidence


def generate_candidates(
    evaluations: list[StrategyEvaluationResult],
) -> tuple[list[SignalCandidate], list[EvidenceItem]]:
    """
    Generate signal candidates from strategy evaluation results.

    Only QUALIFIED strategies with a non-NONE direction produce candidates.
    Returns candidates and a flat list of evidence items.
    """
    candidates: list[SignalCandidate] = []
    evidence_items: list[EvidenceItem] = []

    for ev in evaluations:
        # Only qualified strategies with direction produce candidates
        if ev.status != StrategyEvaluationStatus.QUALIFIED:
            continue

        direction = _strategy_direction_to_signal(ev.direction)
        if direction == SignalDirection.NONE:
            continue

        pass_rate = _extract_condition_pass_rate(ev)
        ev_evidence = _collect_evidence(ev, direction)

        quality_norm = (
            ev.quality_score.normalized_score if ev.quality_score else 0.0
        )
        quality_raw = ev.quality_score.score if ev.quality_score else 0
        quality_max = ev.quality_score.max_score if ev.quality_score else 0

        candidate = SignalCandidate(
            strategy_id=ev.strategy_id,
            strategy_version=ev.strategy_version,
            strategy_name=ev.strategy_name,
            direction=direction,
            quality_score_normalized=quality_norm,
            quality_score_raw=quality_raw,
            quality_score_max=quality_max,
            condition_pass_rate=pass_rate,
            invalidation_triggered=any(ir.triggered for ir in ev.invalidation_results),
            market_regime=ev.market_regime,
            evidence=ev_evidence,
        )
        candidates.append(candidate)

        # Build evidence items from conditions
        for cr in ev.condition_results:
            if cr.status.value == "passed":
                # Determine strength from criticality
                strength_map = {"critical": 0.9, "required": 0.7, "optional": 0.5}
                strength = strength_map.get(cr.criticality.value, 0.5)
                strength *= quality_norm if quality_norm > 0 else 0.5

                evidence_items.append(EvidenceItem(
                    source=f"strategy:{ev.strategy_id}",
                    component="condition",
                    direction=direction,
                    strength=strength,
                    description=f"{cr.condition_name}: {cr.reason}",
                ))

        # Build evidence item from quality score
        if ev.quality_score and quality_norm > 0:
            evidence_items.append(EvidenceItem(
                source=f"strategy:{ev.strategy_id}",
                component="quality",
                direction=direction,
                strength=quality_norm,
                description=f"Quality score: {quality_raw}/{quality_max} ({quality_norm:.0%})",
            ))

    logger.info(
        "Generated %d candidates from %d evaluations",
        len(candidates),
        len(evaluations),
    )
    return candidates, evidence_items
