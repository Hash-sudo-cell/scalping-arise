"""
Scalping Arise — Trend Classification

Deterministic trend classification based on market structure.
Uses the most recent structure labels to determine trend state.

No confidence scoring — pure deterministic analysis.
"""

from __future__ import annotations

import logging

from app.modules.market_analysis.models import (
    StructureLabel,
    StructurePoint,
    TrendResult,
    TrendState,
)

logger = logging.getLogger(__name__)


def classify_trend(
    structure_points: list[StructurePoint],
    min_consecutive: int = 2,
) -> TrendResult:
    """
    Classify trend based on the most recent structure labels.

    Rules:
        - Extract the latest labels (skip INITIAL).
        - If the most recent `min_consecutive` labels are all HH or HL -> BULLISH.
        - If the most recent `min_consecutive` labels are all LH or LL -> BEARISH.
        - If mixed HH/HL and LH/LL in recent labels -> RANGING.
        - If insufficient labeled points -> UNCLEAR.

    Args:
        structure_points: Classified structure points from structure module.
        min_consecutive: Minimum consecutive same-direction labels for trend.

    Returns:
        TrendResult with state, reason, and supporting labels.
    """
    # Extract non-initial labels
    labeled = [p for p in structure_points if p.label != StructureLabel.INITIAL]

    if not labeled:
        return TrendResult(
            state=TrendState.UNCLEAR,
            reason="No classified structure points available",
            structure_labels=[],
        )

    # Take the most recent labels
    recent = labeled[-min_consecutive * 2:] if len(labeled) > min_consecutive * 2 else labeled
    recent_labels = [p.label for p in recent]

    # Count bullish vs bearish labels in the recent window
    bullish_labels = {StructureLabel.HH, StructureLabel.HL}
    bearish_labels = {StructureLabel.LH, StructureLabel.LL}

    # Check for consecutive bullish (HH/HL) at the tail
    tail_bullish = 0
    for label in reversed(recent_labels):
        if label in bullish_labels:
            tail_bullish += 1
        else:
            break

    tail_bearish = 0
    for label in reversed(recent_labels):
        if label in bearish_labels:
            tail_bearish += 1
        else:
            break

    # Classify
    if tail_bullish >= min_consecutive:
        labels_used = recent_labels[-tail_bullish:]
        return TrendResult(
            state=TrendState.BULLISH,
            reason=f"Consecutive bullish structure: {' -> '.join(l.value for l in labels_used)}",
            structure_labels=labels_used,
        )

    if tail_bearish >= min_consecutive:
        labels_used = recent_labels[-tail_bearish:]
        return TrendResult(
            state=TrendState.BEARISH,
            reason=f"Consecutive bearish structure: {' -> '.join(l.value for l in labels_used)}",
            structure_labels=labels_used,
        )

    # Mixed labels
    if len(recent_labels) >= 2:
        all_labels = [p.label for p in labeled]
        return TrendResult(
            state=TrendState.RANGING,
            reason=f"Mixed structure in recent labels: {' -> '.join(l.value for l in recent_labels)}",
            structure_labels=all_labels[-6:],
        )

    return TrendResult(
        state=TrendState.UNCLEAR,
        reason="Insufficient structure labels for classification",
        structure_labels=recent_labels,
    )
