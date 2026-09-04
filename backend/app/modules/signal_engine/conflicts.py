"""
Scalping Arise — Conflict Detection

Identifies directional conflicts between signal candidates.
Conflicts arise when qualified strategies disagree on direction,
or when MTF confirmation shows misalignment.
"""

from __future__ import annotations

import logging
from collections import Counter

from app.modules.signal_engine.models import (
    ConflictType,
    DirectionalConflict,
    MTFConfirmationResult,
    SignalCandidate,
    SignalDirection,
)

logger = logging.getLogger(__name__)


def detect_strategy_divergence(
    candidates: list[SignalCandidate],
) -> list[DirectionalConflict]:
    """
    Detect conflicts where qualified strategies disagree on direction.

    Returns a conflict for each pair of opposing directions.
    """
    conflicts: list[DirectionalConflict] = []

    if len(candidates) < 2:
        return conflicts

    long_ids = [c.strategy_id for c in candidates if c.direction == SignalDirection.LONG]
    short_ids = [c.strategy_id for c in candidates if c.direction == SignalDirection.SHORT]

    if long_ids and short_ids:
        conflicts.append(DirectionalConflict(
            conflict_type=ConflictType.STRATEGY_DIVERGENCE,
            description=(
                f"Strategy divergence: {len(long_ids)} LONG vs {len(short_ids)} SHORT. "
                f"LONG: {', '.join(long_ids)}. SHORT: {', '.join(short_ids)}."
            ),
            involved_strategies=long_ids + short_ids,
            severity=min(0.5 + len(short_ids) * 0.2 + len(long_ids) * 0.2, 1.0),
        ))

    return conflicts


def detect_timeframe_misalignment(
    mtf_result: MTFConfirmationResult,
    candidate_direction: SignalDirection,
) -> list[DirectionalConflict]:
    """
    Detect conflicts from multi-timeframe misalignment.

    If higher timeframes disagree with lower timeframes, that's a conflict.
    """
    conflicts: list[DirectionalConflict] = []

    if not mtf_result or not mtf_result.confirmations:
        return conflicts

    aligned_tfs = [c.timeframe for c in mtf_result.confirmations if c.aligned]
    unaligned_tfs = [c.timeframe for c in mtf_result.confirmations if not c.aligned]

    # If some timeframes confirm and others don't, that's a misalignment
    if aligned_tfs and unaligned_tfs:
        # Determine severity based on timeframe importance
        # Higher timeframes (15m, 1h) are more significant
        high_tfs = {"15m", "30m", "1h", "4h", "1d"}
        high_aligned = [tf for tf in aligned_tfs if tf in high_tfs]
        high_unaligned = [tf for tf in unaligned_tfs if tf in high_tfs]

        if high_aligned and high_unaligned:
            severity = 0.8  # High timeframe disagreement is serious
        elif high_unaligned:
            severity = 0.6  # Higher TFs not confirming
        else:
            severity = 0.3  # Only lower TFs disagreeing

        conflicts.append(DirectionalConflict(
            conflict_type=ConflictType.TIMEFRAME_MISALIGNMENT,
            description=(
                f"Timeframe misalignment: {len(aligned_tfs)} aligned ({', '.join(aligned_tfs)}) "
                f"vs {len(unaligned_tfs)} unaligned ({', '.join(unaligned_tfs)})"
            ),
            involved_strategies=[],
            severity=severity,
        ))

    return conflicts


def detect_all_conflicts(
    candidates: list[SignalCandidate],
    mtf_result: MTFConfirmationResult | None,
    candidate_direction: SignalDirection,
) -> list[DirectionalConflict]:
    """
    Run all conflict detection routines and return combined results.
    """
    conflicts: list[DirectionalConflict] = []

    # Strategy divergence
    conflicts.extend(detect_strategy_divergence(candidates))

    # Timeframe misalignment
    if mtf_result:
        conflicts.extend(detect_timeframe_misalignment(mtf_result, candidate_direction))

    if conflicts:
        logger.warning("Detected %d conflicts", len(conflicts))
    else:
        logger.info("No conflicts detected")

    return conflicts
