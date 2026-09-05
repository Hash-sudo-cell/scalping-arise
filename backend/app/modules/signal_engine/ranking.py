"""
Scalping Arise — Signal Priority Ranking

Composite priority scoring for ranking active signals.
Combines confidence, quality, evidence strength, and recency
into a single 0–100 priority score.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.signal_engine.config import SignalEngineSettings
from app.modules.signal_engine.models import (
    SignalPriority,
    SignalRecord,
    SignalState,
)

logger = logging.getLogger(__name__)


def calculate_priority(
    record: SignalRecord,
    settings: Optional[SignalEngineSettings] = None,
) -> SignalPriority:
    """
    Calculate composite priority score for a signal record.

    Components:
    - Confidence (0–100): from ConfidenceScore.confidence_0_100
    - Quality (0–100): from SignalQuality.score
    - Evidence (0–100): normalized evidence strength
    - Recency (0–100): decays with age (100 at creation, 0 at TTL expiry)
    """
    if settings is None:
        weights = {"confidence": 0.35, "quality": 0.30, "evidence": 0.20, "recency": 0.15}
    else:
        weights = settings.priority_weights_normalized

    # Confidence component (0–100)
    confidence_score = 0.0
    if record.confidence:
        confidence_score = float(record.confidence.confidence_0_100)

    # Quality component (0–100)
    quality_score = 0.0
    if record.quality:
        quality_score = float(record.quality.score)

    # Evidence component (0–100)
    evidence_score = 0.0
    if record.evidence:
        supporting = [e for e in record.evidence if e.direction == record.direction]
        if supporting:
            avg_strength = sum(e.strength for e in supporting) / len(supporting)
            evidence_score = avg_strength * 100.0

    # Recency component (0–100): linear decay from 100 to 0 over TTL
    now = datetime.now(timezone.utc)
    elapsed = (now - record.created_at).total_seconds()
    ttl = max(record.ttl_seconds, 1)
    recency_score = max(0.0, 100.0 * (1.0 - elapsed / ttl))

    # Weighted composite
    priority_score = (
        confidence_score * weights["confidence"]
        + quality_score * weights["quality"]
        + evidence_score * weights["evidence"]
        + recency_score * weights["recency"]
    )

    return SignalPriority(
        priority_score=round(priority_score, 2),
        confidence_weight=weights["confidence"],
        quality_weight=weights["quality"],
        evidence_weight=weights["evidence"],
        recency_weight=weights["recency"],
    )


def rank_signals(
    records: list[SignalRecord],
    settings: Optional[SignalEngineSettings] = None,
) -> list[SignalRecord]:
    """
    Rank active signals by priority score.

    Returns signals sorted by priority (highest first), with rank
    assigned to each signal's priority field.
    """
    active = [r for r in records if r.state in (SignalState.ACTIVE, SignalState.CONFIRMED)]

    if not active:
        return []

    # Calculate priority for each
    for record in active:
        record.priority = calculate_priority(record, settings)

    # Sort by priority score descending
    ranked = sorted(active, key=lambda r: r.priority.priority_score, reverse=True)

    # Assign ranks
    for i, record in enumerate(ranked, start=1):
        record.priority.rank = i

    logger.info(
        "Ranked %d active signals, top priority: %.1f",
        len(ranked),
        ranked[0].priority.priority_score if ranked else 0.0,
    )
    return ranked


def get_top_signal(
    records: list[SignalRecord],
    settings: Optional[SignalEngineSettings] = None,
) -> Optional[SignalRecord]:
    """Get the single highest-priority active signal."""
    ranked = rank_signals(records, settings)
    return ranked[0] if ranked else None
