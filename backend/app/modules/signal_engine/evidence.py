"""
Scalping Arise — Evidence Aggregation

Collects and organizes all supporting/opposing evidence from the pipeline
into a unified evidence list with strength scores.
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
from app.modules.market_analysis.models import AnalysisResult, MarketRegime

logger = logging.getLogger(__name__)


def _build_regime_evidence(
    analysis: Optional[AnalysisResult],
    direction: SignalDirection,
) -> list[EvidenceItem]:
    """Build evidence items from market regime context."""
    items: list[EvidenceItem] = []

    if not analysis or not analysis.regime:
        return items

    regime = analysis.regime.state
    evidence_text = analysis.regime.evidence

    # Determine if regime supports direction
    supports = False
    if direction == SignalDirection.LONG and regime in (
        MarketRegime.TRENDING_UP,
    ):
        supports = True
    elif direction == SignalDirection.SHORT and regime in (
        MarketRegime.TRENDING_DOWN,
    ):
        supports = True
    elif direction != SignalDirection.NONE and regime == MarketRegime.RANGING:
        # Ranging can support reversals but doesn't strongly support continuation
        supports = False

    strength = 0.7 if supports else 0.3

    items.append(EvidenceItem(
        source="analysis:regime",
        component="regime",
        direction=direction if supports else SignalDirection.NONE,
        strength=strength,
        description=f"Regime: {regime.value} ({'supports' if supports else 'does not support'} {direction.value})",
    ))

    for e in evidence_text:
        items.append(EvidenceItem(
            source="analysis:regime",
            component="regime",
            direction=direction if supports else SignalDirection.NONE,
            strength=strength * 0.8,
            description=e,
        ))

    return items


def _build_structure_evidence(
    analysis: Optional[AnalysisResult],
    direction: SignalDirection,
) -> list[EvidenceItem]:
    """Build evidence items from market structure."""
    items: list[EvidenceItem] = []

    if not analysis or not analysis.structure:
        return items

    labels = analysis.structure.latest_labels
    if not labels:
        return items

    from app.modules.market_analysis.models import StructureLabel

    bullish_labels = {StructureLabel.HH, StructureLabel.HL}
    bearish_labels = {StructureLabel.LH, StructureLabel.LL}

    recent = labels[-5:] if len(labels) > 5 else labels
    bullish_count = sum(1 for l in recent if l in bullish_labels)
    bearish_count = sum(1 for l in recent if l in bearish_labels)
    total = len(recent)

    if total == 0:
        return items

    if direction == SignalDirection.LONG:
        strength = bullish_count / total
        supports = bullish_count > bearish_count
    elif direction == SignalDirection.SHORT:
        strength = bearish_count / total
        supports = bearish_count > bullish_count
    else:
        strength = 0.5
        supports = False

    items.append(EvidenceItem(
        source="analysis:structure",
        component="structure",
        direction=direction if supports else SignalDirection.NONE,
        strength=strength,
        description=f"Structure labels: {[l.value for l in recent]} ({bullish_count}B/{bearish_count}S)",
    ))

    return items


def _build_liquidity_evidence(
    analysis: Optional[AnalysisResult],
    direction: SignalDirection,
) -> list[EvidenceItem]:
    """Build evidence items from liquidity analysis."""
    items: list[EvidenceItem] = []

    if not analysis or not analysis.liquidity:
        return items

    liq = analysis.liquidity
    if liq.status.value != "available":
        return items

    # Active pools indicate market interest
    if liq.active_pool_count > 0:
        items.append(EvidenceItem(
            source="analysis:liquidity",
            component="liquidity",
            direction=direction,
            strength=min(0.5 + liq.active_pool_count * 0.1, 0.9),
            description=f"{liq.active_pool_count} active liquidity pools",
        ))

    # Sweeps indicate liquidity events
    if liq.swept_pool_count > 0:
        items.append(EvidenceItem(
            source="analysis:liquidity",
            component="liquidity",
            direction=direction,
            strength=min(0.4 + liq.swept_pool_count * 0.15, 0.8),
            description=f"{liq.swept_pool_count} pools swept",
        ))

    # Distance to liquidity
    if direction == SignalDirection.LONG and liq.distance_to_buy_side_pct is not None:
        pct = liq.distance_to_buy_side_pct
        strength = max(0.3, 1.0 - pct / 5.0)  # Closer = stronger
        items.append(EvidenceItem(
            source="analysis:liquidity",
            component="liquidity",
            direction=direction,
            strength=strength,
            description=f"Buy-side liquidity {pct:.2f}% away",
        ))
    elif direction == SignalDirection.SHORT and liq.distance_to_sell_side_pct is not None:
        pct = liq.distance_to_sell_side_pct
        strength = max(0.3, 1.0 - pct / 5.0)
        items.append(EvidenceItem(
            source="analysis:liquidity",
            component="liquidity",
            direction=direction,
            strength=strength,
            description=f"Sell-side liquidity {pct:.2f}% away",
        ))

    return items


def aggregate_evidence(
    candidates: list[SignalCandidate],
    candidate_evidence: list[EvidenceItem],
    mtf_evidence: list[EvidenceItem],
    analysis: Optional[AnalysisResult],
    direction: SignalDirection,
) -> list[EvidenceItem]:
    """
    Aggregate all evidence from the pipeline into a single list.

    Combines candidate evidence, MTF confirmation evidence,
    and analysis-derived evidence (regime, structure, liquidity).
    """
    all_evidence: list[EvidenceItem] = []

    # Strategy candidate evidence
    all_evidence.extend(candidate_evidence)

    # MTF confirmation evidence
    all_evidence.extend(mtf_evidence)

    # Analysis-derived evidence
    all_evidence.extend(_build_regime_evidence(analysis, direction))
    all_evidence.extend(_build_structure_evidence(analysis, direction))
    all_evidence.extend(_build_liquidity_evidence(analysis, direction))

    logger.info("Aggregated %d evidence items", len(all_evidence))
    return all_evidence
