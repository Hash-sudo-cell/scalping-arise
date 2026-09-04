"""
Scalping Arise — Multi-Timeframe Confirmation

Evaluates whether feature data across multiple timeframes confirms
a candidate's directional bias. Uses EMA alignment, trend state,
and momentum context from each timeframe.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.signal_engine.models import (
    ConfirmationLevel,
    EvidenceItem,
    MTFConfirmationResult,
    SignalCandidate,
    SignalDirection,
    TimeframeConfirmation,
)
from app.modules.technical_features.models import (
    EMAAlignment,
    FeatureResult,
    FeatureSetStatus,
)
from app.modules.market_analysis.models import AnalysisResult, TrendState

logger = logging.getLogger(__name__)


def _check_ema_alignment(
    features: FeatureResult,
    direction: SignalDirection,
) -> tuple[bool, Optional[str], list[str]]:
    """
    Check if EMA alignment supports the candidate direction.

    Returns (aligned, alignment_state, evidence).
    """
    if not features.trend:
        return False, None, []

    alignment = features.trend.alignment
    evidence: list[str] = []

    if alignment == EMAAlignment.UNAVAILABLE:
        return False, alignment.value, ["EMA alignment unavailable"]

    if direction == SignalDirection.LONG:
        aligned = alignment == EMAAlignment.BULLISH
        evidence.append(f"EMA alignment: {alignment.value} (need bullish)")
    elif direction == SignalDirection.SHORT:
        aligned = alignment == EMAAlignment.BEARISH
        evidence.append(f"EMA alignment: {alignment.value} (need bearish)")
    else:
        aligned = False
        evidence.append(f"EMA alignment: {alignment.value} (no direction)")

    return aligned, alignment.value, evidence


def _check_trend_state(
    analysis: Optional[AnalysisResult],
    direction: SignalDirection,
) -> tuple[bool, Optional[str], list[str]]:
    """
    Check if the higher-timeframe trend state supports the candidate.

    Returns (aligned, trend_state, evidence).
    """
    if not analysis or not analysis.trend:
        return False, None, []

    trend = analysis.trend.state
    evidence: list[str] = []

    if trend == TrendState.UNCLEAR:
        return False, trend.value, ["Trend unclear"]

    if direction == SignalDirection.LONG:
        aligned = trend == TrendState.BULLISH
        evidence.append(f"Trend state: {trend.value} (need bullish)")
    elif direction == SignalDirection.SHORT:
        aligned = trend == TrendState.BEARISH
        evidence.append(f"Trend state: {trend.value} (need bearish)")
    else:
        aligned = False
        evidence.append(f"Trend state: {trend.value} (no direction)")

    return aligned, trend.value, evidence


def _determine_confirmation_level(
    aligned_features: int,
    total_features: int,
) -> ConfirmationLevel:
    """Determine the confirmation level from feature alignment counts."""
    if total_features == 0:
        return ConfirmationLevel.NONE

    ratio = aligned_features / total_features

    if ratio >= 0.75:
        return ConfirmationLevel.STRONG
    elif ratio >= 0.5:
        return ConfirmationLevel.MODERATE
    elif ratio > 0.0:
        return ConfirmationLevel.WEAK
    else:
        return ConfirmationLevel.NONE


def evaluate_mtf_confirmation(
    candidate: SignalCandidate,
    timeframe_features: dict[str, FeatureResult],
    timeframe_analyses: dict[str, Optional[AnalysisResult]],
    min_aligned: int = 1,
) -> tuple[MTFConfirmationResult, list[EvidenceItem]]:
    """
    Evaluate multi-timeframe confirmation for a signal candidate.

    Checks EMA alignment and trend state across all available timeframes.
    At least `min_aligned` timeframes must confirm the direction.

    Returns the MTF confirmation result and evidence items.
    """
    confirmations: list[TimeframeConfirmation] = []
    evidence_items: list[EvidenceItem] = []
    aligned_count = 0

    for tf, features in timeframe_features.items():
        analysis = timeframe_analyses.get(tf)

        # Skip if features are not ready
        if features.feature_set_status != FeatureSetStatus.READY:
            confirmations.append(TimeframeConfirmation(
                timeframe=tf,
                aligned=False,
                confirmation_level=ConfirmationLevel.NONE,
                supporting_evidence=[f"Features not ready: {features.feature_set_status.value}"],
            ))
            continue

        # Check EMA alignment
        ema_aligned, ema_state, ema_evidence = _check_ema_alignment(
            features, candidate.direction,
        )

        # Check trend state
        trend_aligned, trend_state, trend_evidence = _check_trend_state(
            analysis, candidate.direction,
        )

        # A timeframe is aligned if at least EMA or trend supports it
        aligned = ema_aligned or trend_aligned
        all_evidence = ema_evidence + trend_evidence

        # Determine per-timeframe confirmation level
        features_aligned = sum([ema_aligned, trend_aligned])
        tf_level = _determine_confirmation_level(features_aligned, 2)

        if aligned:
            aligned_count += 1

        confirmations.append(TimeframeConfirmation(
            timeframe=tf,
            aligned=aligned,
            confirmation_level=tf_level,
            supporting_evidence=all_evidence,
            ema_alignment=ema_state,
            trend_state=trend_state,
        ))

        # Build evidence items
        for e in all_evidence:
            evidence_items.append(EvidenceItem(
                source=f"mtf:{tf}",
                component="confirmation",
                direction=candidate.direction if aligned else SignalDirection.NONE,
                strength=0.8 if aligned else 0.2,
                description=e,
            ))

    total_count = len(timeframe_features)
    confirmed = aligned_count >= min_aligned

    # Overall confirmation level
    overall_level = _determine_confirmation_level(aligned_count, total_count)

    result = MTFConfirmationResult(
        confirmed=confirmed,
        confirmation_level=overall_level,
        aligned_count=aligned_count,
        total_count=total_count,
        confirmations=confirmations,
        evidence=[
            f"{aligned_count}/{total_count} timeframes confirm {candidate.direction.value}"
        ],
    )

    logger.info(
        "MTF confirmation: %d/%d aligned, confirmed=%s, level=%s",
        aligned_count,
        total_count,
        confirmed,
        overall_level.value,
    )
    return result, evidence_items
