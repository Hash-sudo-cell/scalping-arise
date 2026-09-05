"""
Scalping Arise — Signal Qualification

Final gate that determines whether a signal evaluation produces
a QUALIFIED, REJECTED, CONFLICT, or INSUFFICIENT_CONTEXT result.

Phase 6 additions:
- Computes independent SignalQuality (0–100) score
- Maps qualification to state machine transitions
- Produces structured DecisionReason codes
"""

from __future__ import annotations

import logging

from app.modules.signal_engine.config import SignalEngineSettings
from app.modules.signal_engine.models import (
    ConfidenceBreakdown,
    ConfidenceScore,
    ConflictResolution,
    DirectionalConflict,
    DecisionReason,
    DecisionReasonCode,
    MTFConfirmationResult,
    SignalCandidate,
    SignalDirection,
    SignalQuality,
    SignalStatus,
)

logger = logging.getLogger(__name__)


def compute_signal_quality(
    candidates: list[SignalCandidate],
    direction: SignalDirection,
    evidence_count: int,
    confidence: ConfidenceScore,
) -> SignalQuality:
    """
    Compute independent signal quality score (0–100).

    Quality measures the structural strength of the signal setup:
    - Weighted condition pass rate across contributing strategies
    - Number of independent evidence sources
    - Fraction of strategies aligned on the direction
    """
    if not candidates:
        return SignalQuality(
            score=0,
            condition_pass_rate=0.0,
            evidence_depth=0,
            strategy_alignment=0.0,
        )

    # Weighted condition pass rate (by quality score)
    total_weight = sum(c.quality_score_normalized for c in candidates)
    if total_weight > 0:
        weighted_pass_rate = sum(
            c.condition_pass_rate * c.quality_score_normalized
            for c in candidates
        ) / total_weight
    else:
        weighted_pass_rate = sum(c.condition_pass_rate for c in candidates) / len(candidates)

    # Evidence depth (number of independent supporting sources)
    evidence_depth = evidence_count

    # Strategy alignment (fraction of candidates on the winning direction)
    directional = [c for c in candidates if c.direction != SignalDirection.NONE]
    if directional:
        aligned = [c for c in directional if c.direction == direction]
        strategy_alignment = len(aligned) / len(directional)
    else:
        strategy_alignment = 0.0

    # Compute composite quality score (0–100)
    # Components: condition_pass_rate (40%), evidence_depth (25%), strategy_alignment (35%)
    condition_component = weighted_pass_rate * 40.0
    evidence_component = min(evidence_depth / 10.0, 1.0) * 25.0  # cap at 10 evidence items
    alignment_component = strategy_alignment * 35.0

    quality_score = round(condition_component + evidence_component + alignment_component)
    quality_score = max(0, min(100, quality_score))

    breakdown = [
        ConfidenceBreakdown(
            factor="condition_pass_rate",
            score=weighted_pass_rate,
            weight=0.40,
            contribution=condition_component,
            description=f"Weighted condition pass rate: {weighted_pass_rate:.2f}",
        ),
        ConfidenceBreakdown(
            factor="evidence_depth",
            score=min(evidence_depth / 10.0, 1.0),
            weight=0.25,
            contribution=evidence_component,
            description=f"Evidence depth: {evidence_depth} sources",
        ),
        ConfidenceBreakdown(
            factor="strategy_alignment",
            score=strategy_alignment,
            weight=0.35,
            contribution=alignment_component,
            description=f"Strategy alignment: {strategy_alignment:.2f}",
        ),
    ]

    return SignalQuality(
        score=quality_score,
        condition_pass_rate=weighted_pass_rate,
        evidence_depth=evidence_depth,
        strategy_alignment=strategy_alignment,
        breakdown=breakdown,
    )


def qualify_signal(
    candidates: list[SignalCandidate],
    direction: SignalDirection,
    confidence: ConfidenceScore,
    mtf_result: MTFConfirmationResult | None,
    conflicts: list[DirectionalConflict],
    resolution: ConflictResolution | None,
    settings: SignalEngineSettings,
) -> tuple[SignalStatus, str, list[DecisionReason]]:
    """
    Determine the final signal status.

    Logic:
    1. No candidates or NONE direction → INSUFFICIENT_CONTEXT
    2. Conflicts with resolution → check resolution confidence
    3. Unresolved conflicts → CONFLICT
    4. Confidence below threshold → REJECTED
    5. MTF required but not confirmed → REJECTED
    6. All checks pass → QUALIFIED

    Phase 6: Also returns structured DecisionReason codes.
    """
    reasons: list[DecisionReason] = []

    # No candidates at all
    if not candidates:
        reasons.append(DecisionReason(
            code=DecisionReasonCode.NO_CANDIDATES,
            detail="No qualified strategy candidates produced a directional signal",
        ))
        return (
            SignalStatus.INSUFFICIENT_CONTEXT,
            "No qualified strategy candidates produced a directional signal",
            reasons,
        )

    # Direction is NONE after resolution
    if direction == SignalDirection.NONE:
        reasons.append(DecisionReason(
            code=DecisionReasonCode.DIRECTION_NONE,
            detail="No clear directional bias — candidates produced conflicting or no direction",
        ))
        return (
            SignalStatus.INSUFFICIENT_CONTEXT,
            "No clear directional bias — candidates produced conflicting or no direction",
            reasons,
        )

    # Check if resolution dropped confidence below threshold
    if resolution and resolution.confidence < settings.minimum_confidence_threshold:
        reasons.append(DecisionReason(
            code=DecisionReasonCode.CONFLICT_UNRESOLVED,
            detail=(
                f"Conflicts resolved but confidence ({resolution.confidence:.2f}) "
                f"below threshold ({settings.minimum_confidence_threshold:.2f}). "
                f"Resolution method: {resolution.resolution_method}"
            ),
            contributing_factors=[resolution.resolution_method],
        ))
        return (
            SignalStatus.CONFLICT,
            (
                f"Conflicts resolved but confidence ({resolution.confidence:.2f}) "
                f"below threshold ({settings.minimum_confidence_threshold:.2f}). "
                f"Resolution method: {resolution.resolution_method}"
            ),
            reasons,
        )

    # Unresolved high-severity conflicts
    high_severity = [c for c in conflicts if c.severity >= 0.7]
    if high_severity and not resolution:
        reasons.append(DecisionReason(
            code=DecisionReasonCode.CONFLICT_UNRESOLVED,
            detail=f"Unresolved high-severity conflicts: {high_severity[0].description}",
            contributing_factors=[c.conflict_type.value for c in high_severity],
        ))
        return (
            SignalStatus.CONFLICT,
            f"Unresolved high-severity conflicts: {high_severity[0].description}",
            reasons,
        )

    # Confidence threshold check
    if confidence.overall < settings.minimum_confidence_threshold:
        reasons.append(DecisionReason(
            code=DecisionReasonCode.LOW_CONFIDENCE,
            detail=(
                f"Confidence {confidence.overall:.2f} below threshold "
                f"{settings.minimum_confidence_threshold:.2f}"
            ),
        ))
        return (
            SignalStatus.REJECTED,
            (
                f"Confidence {confidence.overall:.2f} below threshold "
                f"{settings.minimum_confidence_threshold:.2f}"
            ),
            reasons,
        )

    # MTF confirmation check
    if settings.require_mtf_confirmation and mtf_result:
        if not mtf_result.confirmed:
            reasons.append(DecisionReason(
                code=DecisionReasonCode.MTF_NOT_CONFIRMED,
                detail=(
                    f"Multi-timeframe confirmation required but not met: "
                    f"{mtf_result.aligned_count}/{mtf_result.total_count} aligned "
                    f"(need {settings.mtf_min_aligned_timeframes})"
                ),
            ))
            return (
                SignalStatus.REJECTED,
                (
                    f"Multi-timeframe confirmation required but not met: "
                    f"{mtf_result.aligned_count}/{mtf_result.total_count} aligned "
                    f"(need {settings.mtf_min_aligned_timeframes})"
                ),
                reasons,
            )

    # All checks pass — build positive reasons
    strength_label = (
        "STRONG" if confidence.overall >= settings.strong_confidence_threshold
        else "MODERATE"
    )

    reasons.append(DecisionReason(
        code=DecisionReasonCode.STRONG_CONSENSUS if len(candidates) > 1 else DecisionReasonCode.QUALITY_WEIGHTED_WINNER,
        detail=f"{len(candidates)} candidate(s) contributing",
        contributing_factors=[c.strategy_id for c in candidates],
    ))

    if mtf_result and mtf_result.confirmed:
        reasons.append(DecisionReason(
            code=DecisionReasonCode.MTF_CONFIRMED,
            detail=f"{mtf_result.aligned_count}/{mtf_result.total_count} timeframes aligned",
        ))

    reasons.append(DecisionReason(
        code=DecisionReasonCode.EVIDENCE_SUPPORTED,
        detail="Sufficient evidence supporting signal direction",
    ))

    # Check regime consistency
    regimes = {c.market_regime for c in candidates if c.market_regime}
    if regimes:
        reasons.append(DecisionReason(
            code=DecisionReasonCode.REGIME_ALIGNED,
            detail=f"Market regimes: {', '.join(sorted(regimes))}",
        ))

    return (
        SignalStatus.QUALIFIED,
        (
            f"{strength_label} {direction.value.upper()} signal — "
            f"confidence {confidence.overall:.2f}, "
            f"{len(candidates)} candidate(s), "
            f"{mtf_result.aligned_count if mtf_result else 0} timeframe(s) aligned"
        ),
        reasons,
    )
