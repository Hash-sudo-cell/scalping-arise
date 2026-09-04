"""
Scalping Arise — Signal Qualification

Final gate that determines whether a signal evaluation produces
a QUALIFIED, REJECTED, CONFLICT, or INSUFFICIENT_CONTEXT result.
"""

from __future__ import annotations

import logging

from app.modules.signal_engine.config import SignalEngineSettings
from app.modules.signal_engine.models import (
    ConfidenceScore,
    ConflictResolution,
    DirectionalConflict,
    MTFConfirmationResult,
    SignalCandidate,
    SignalDirection,
    SignalStatus,
)

logger = logging.getLogger(__name__)


def qualify_signal(
    candidates: list[SignalCandidate],
    direction: SignalDirection,
    confidence: ConfidenceScore,
    mtf_result: MTFConfirmationResult | None,
    conflicts: list[DirectionalConflict],
    resolution: ConflictResolution | None,
    settings: SignalEngineSettings,
) -> tuple[SignalStatus, str]:
    """
    Determine the final signal status.

    Logic:
    1. No candidates or NONE direction → INSUFFICIENT_CONTEXT
    2. Conflicts with resolution → check resolution confidence
    3. Unresolved conflicts → CONFLICT
    4. Confidence below threshold → REJECTED
    5. MTF required but not confirmed → REJECTED
    6. All checks pass → QUALIFIED
    """
    # No candidates at all
    if not candidates:
        return (
            SignalStatus.INSUFFICIENT_CONTEXT,
            "No qualified strategy candidates produced a directional signal",
        )

    # Direction is NONE after resolution
    if direction == SignalDirection.NONE:
        return (
            SignalStatus.INSUFFICIENT_CONTEXT,
            "No clear directional bias — candidates produced conflicting or no direction",
        )

    # Check if resolution dropped confidence below threshold
    if resolution and resolution.confidence < settings.minimum_confidence_threshold:
        return (
            SignalStatus.CONFLICT,
            (
                f"Conflicts resolved but confidence ({resolution.confidence:.2f}) "
                f"below threshold ({settings.minimum_confidence_threshold:.2f}). "
                f"Resolution method: {resolution.resolution_method}"
            ),
        )

    # Unresolved high-severity conflicts
    high_severity = [c for c in conflicts if c.severity >= 0.7]
    if high_severity and not resolution:
        return (
            SignalStatus.CONFLICT,
            f"Unresolved high-severity conflicts: {high_severity[0].description}",
        )

    # Confidence threshold check
    if confidence.overall < settings.minimum_confidence_threshold:
        return (
            SignalStatus.REJECTED,
            (
                f"Confidence {confidence.overall:.2f} below threshold "
                f"{settings.minimum_confidence_threshold:.2f}"
            ),
        )

    # MTF confirmation check
    if settings.require_mtf_confirmation and mtf_result:
        if not mtf_result.confirmed:
            return (
                SignalStatus.REJECTED,
                (
                    f"Multi-timeframe confirmation required but not met: "
                    f"{mtf_result.aligned_count}/{mtf_result.total_count} aligned "
                    f"(need {settings.mtf_min_aligned_timeframes})"
                ),
            )

    # All checks pass
    strength_label = (
        "STRONG" if confidence.overall >= settings.strong_confidence_threshold
        else "MODERATE"
    )
    return (
        SignalStatus.QUALIFIED,
        (
            f"{strength_label} {direction.value.upper()} signal — "
            f"confidence {confidence.overall:.2f}, "
            f"{len(candidates)} candidate(s), "
            f"{mtf_result.aligned_count if mtf_result else 0} timeframe(s) aligned"
        ),
    )
