"""
Scalping Arise — Conflict Resolution

Resolves directional conflicts between signal candidates using
quality-weighted voting. When strategies disagree on direction,
the resolution favors the direction supported by higher-quality candidates.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.modules.signal_engine.models import (
    ConflictResolution,
    DirectionalConflict,
    SignalCandidate,
    SignalDirection,
)

logger = logging.getLogger(__name__)


def resolve_conflicts(
    candidates: list[SignalCandidate],
    conflicts: list[DirectionalConflict],
) -> ConflictResolution:
    """
    Resolve directional conflicts using quality-weighted voting.

    Strategy:
    1. If only one direction exists among candidates → no conflict to resolve
    2. Weight each candidate's vote by its quality_score_normalized * condition_pass_rate
    3. Sum weights per direction → highest weight wins
    4. If weights are tied or very close → NONE direction with low confidence
    """
    if not candidates:
        return ConflictResolution(
            final_direction=SignalDirection.NONE,
            confidence=0.0,
            conflicts=conflicts,
            resolution_method="no_candidates",
        )

    # No conflicts → take the only direction present
    directions_present = {c.direction for c in candidates if c.direction != SignalDirection.NONE}
    if len(directions_present) <= 1:
        direction = directions_present.pop() if directions_present else SignalDirection.NONE
        return ConflictResolution(
            final_direction=direction,
            confidence=0.8 if direction != SignalDirection.NONE else 0.0,
            conflicts=conflicts,
            resolution_method="no_conflict",
        )

    # Quality-weighted vote
    direction_weights: dict[SignalDirection, float] = defaultdict(float)
    for c in candidates:
        if c.direction == SignalDirection.NONE:
            continue
        weight = c.quality_score_normalized * c.condition_pass_rate
        direction_weights[c.direction] += weight

    # Find the winning direction
    if not direction_weights:
        return ConflictResolution(
            final_direction=SignalDirection.NONE,
            confidence=0.0,
            conflicts=conflicts,
            resolution_method="no_valid_directions",
        )

    sorted_directions = sorted(
        direction_weights.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    winner_dir, winner_weight = sorted_directions[0]

    # Check for tie or near-tie
    if len(sorted_directions) > 1:
        runner_up_dir, runner_up_weight = sorted_directions[1]
        total = winner_weight + runner_up_weight
        if total > 0:
            margin = (winner_weight - runner_up_weight) / total
            if margin < 0.1:
                # Near-tie — low confidence
                confidence = 0.3
                method = "quality_weighted_narrow_margin"
            else:
                confidence = min(0.5 + margin * 0.4, 0.9)
                method = "quality_weighted"
        else:
            confidence = 0.3
            method = "quality_weighted_zero_weight"
    else:
        confidence = min(0.5 + winner_weight * 0.4, 0.9)
        method = "quality_weighted_unanimous"

    # Identify dropped candidates (those that voted for the losing direction)
    dropped = [
        c.strategy_id for c in candidates
        if c.direction not in (winner_dir, SignalDirection.NONE)
    ]

    resolution = ConflictResolution(
        final_direction=winner_dir,
        confidence=confidence,
        conflicts=conflicts,
        resolution_method=method,
        dropped_candidates=dropped,
    )

    logger.info(
        "Conflict resolved: %s (confidence=%.2f, method=%s, dropped=%s)",
        winner_dir.value,
        confidence,
        method,
        dropped,
    )
    return resolution
