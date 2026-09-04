"""
Scalping Arise — Confidence Scoring

Calculates composite confidence scores from strategy alignment,
multi-timeframe confirmation, evidence strength, and regime consistency.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.signal_engine.models import (
    ConfidenceBreakdown,
    ConfidenceScore,
    EvidenceItem,
    MTFConfirmationResult,
    SignalCandidate,
    SignalDirection,
)
from app.modules.market_analysis.models import AnalysisResult, MarketRegime

logger = logging.getLogger(__name__)

# Factor weights (must sum to 1.0)
_WEIGHTS = {
    "strategy_alignment": 0.30,
    "mtf_confirmation": 0.25,
    "evidence_strength": 0.25,
    "regime_consistency": 0.20,
}


def _score_strategy_alignment(
    candidates: list[SignalCandidate],
    direction: SignalDirection,
) -> float:
    """
    Score how aligned the candidates are on the given direction.

    Returns 1.0 if all candidates agree, lower if they disagree.
    """
    if not candidates:
        return 0.0

    directional = [c for c in candidates if c.direction != SignalDirection.NONE]
    if not directional:
        return 0.0

    aligned = [c for c in directional if c.direction == direction]
    if not aligned:
        return 0.0

    # Weight by quality score
    aligned_weight = sum(c.quality_score_normalized for c in aligned)
    total_weight = sum(c.quality_score_normalized for c in directional)

    if total_weight == 0:
        return 0.0

    return aligned_weight / total_weight


def _score_mtf_confirmation(
    mtf_result: Optional[MTFConfirmationResult],
) -> float:
    """Score multi-timeframe confirmation strength."""
    if not mtf_result:
        return 0.5  # Neutral if no MTF data

    if mtf_result.total_count == 0:
        return 0.5

    ratio = mtf_result.aligned_count / mtf_result.total_count

    # Boost if higher timeframes are confirmed
    level_map = {
        "strong": 1.0,
        "moderate": 0.7,
        "weak": 0.4,
        "none": 0.1,
    }
    level_score = level_map.get(mtf_result.confirmation_level.value, 0.5)

    return (ratio * 0.6) + (level_score * 0.4)


def _score_evidence_strength(
    evidence: list[EvidenceItem],
    direction: SignalDirection,
) -> float:
    """Score the aggregate strength of supporting evidence."""
    if not evidence:
        return 0.0

    supporting = [
        e for e in evidence
        if e.direction == direction
    ]
    opposing = [
        e for e in evidence
        if e.direction != SignalDirection.NONE and e.direction != direction
    ]

    if not supporting:
        return 0.0 if opposing else 0.3

    support_avg = sum(e.strength for e in supporting) / len(supporting)
    oppose_avg = sum(e.strength for e in opposing) / len(opposing) if opposing else 0.0

    # Net strength: support minus partial opposing penalty
    net = support_avg - (oppose_avg * 0.3)
    return max(0.0, min(1.0, net))


def _score_regime_consistency(
    analysis: Optional[AnalysisResult],
    direction: SignalDirection,
) -> float:
    """Score whether the market regime supports the signal direction."""
    if not analysis or not analysis.regime:
        return 0.5  # Neutral if no regime data

    regime = analysis.regime.state

    # Direct alignment
    if direction == SignalDirection.LONG and regime == MarketRegime.TRENDING_UP:
        return 0.9
    if direction == SignalDirection.SHORT and regime == MarketRegime.TRENDING_DOWN:
        return 0.9

    # Ranging is neutral for most signals
    if regime == MarketRegime.RANGING:
        return 0.5

    # Volatile regime reduces confidence
    if regime == MarketRegime.VOLATILE:
        return 0.4

    # Opposing trend
    if direction == SignalDirection.LONG and regime == MarketRegime.TRENDING_DOWN:
        return 0.2
    if direction == SignalDirection.SHORT and regime == MarketRegime.TRENDING_UP:
        return 0.2

    return 0.5


def calculate_confidence(
    candidates: list[SignalCandidate],
    direction: SignalDirection,
    mtf_result: Optional[MTFConfirmationResult],
    evidence: list[EvidenceItem],
    analysis: Optional[AnalysisResult],
) -> ConfidenceScore:
    """
    Calculate composite confidence score for a signal.

    Combines four factors: strategy alignment, MTF confirmation,
    evidence strength, and regime consistency. Each factor is scored
    0.0–1.0, weighted, and combined into an overall score.
    """
    strategy_alignment = _score_strategy_alignment(candidates, direction)
    mtf_confirmation = _score_mtf_confirmation(mtf_result)
    evidence_strength = _score_evidence_strength(evidence, direction)
    regime_consistency = _score_regime_consistency(analysis, direction)

    breakdown = [
        ConfidenceBreakdown(
            factor="strategy_alignment",
            score=strategy_alignment,
            weight=_WEIGHTS["strategy_alignment"],
            contribution=strategy_alignment * _WEIGHTS["strategy_alignment"],
            description=f"Strategy alignment on {direction.value}: {strategy_alignment:.2f}",
        ),
        ConfidenceBreakdown(
            factor="mtf_confirmation",
            score=mtf_confirmation,
            weight=_WEIGHTS["mtf_confirmation"],
            contribution=mtf_confirmation * _WEIGHTS["mtf_confirmation"],
            description=f"MTF confirmation: {mtf_confirmation:.2f}",
        ),
        ConfidenceBreakdown(
            factor="evidence_strength",
            score=evidence_strength,
            weight=_WEIGHTS["evidence_strength"],
            contribution=evidence_strength * _WEIGHTS["evidence_strength"],
            description=f"Evidence strength: {evidence_strength:.2f}",
        ),
        ConfidenceBreakdown(
            factor="regime_consistency",
            score=regime_consistency,
            weight=_WEIGHTS["regime_consistency"],
            contribution=regime_consistency * _WEIGHTS["regime_consistency"],
            description=f"Regime consistency: {regime_consistency:.2f}",
        ),
    ]

    overall = sum(b.contribution for b in breakdown)

    score = ConfidenceScore(
        overall=round(overall, 4),
        strategy_alignment=round(strategy_alignment, 4),
        mtf_confirmation=round(mtf_confirmation, 4),
        evidence_strength=round(evidence_strength, 4),
        regime_consistency=round(regime_consistency, 4),
        breakdown=breakdown,
    )

    logger.info(
        "Confidence: overall=%.2f (alignment=%.2f, mtf=%.2f, evidence=%.2f, regime=%.2f)",
        overall,
        strategy_alignment,
        mtf_confirmation,
        evidence_strength,
        regime_consistency,
    )
    return score
