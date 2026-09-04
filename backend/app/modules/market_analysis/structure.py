"""
Scalping Arise — Market Structure Classification

Classifies each confirmed swing point as HH, HL, LH, LL, or INITIAL
based on comparison with the prior swing of the same type.

Only confirmed swings should be passed to this module.
"""

from __future__ import annotations

import logging

from app.modules.market_analysis.models import (
    StructureLabel,
    StructurePoint,
    SwingPoint,
    SwingType,
)

logger = logging.getLogger(__name__)


def classify_structure(swings: list[SwingPoint]) -> list[StructurePoint]:
    """
    Classify a sequence of confirmed swings into market structure labels.

    Logic:
        - The first swing of each type gets INITIAL.
        - Each subsequent swing_high is compared to the prior swing_high:
            higher -> HH, lower -> LH, equal -> LH (conservative).
        - Each subsequent swing_low is compared to the prior swing_low:
            higher -> HL, lower -> LL, equal -> LL (conservative).

    Args:
        swings: Chronologically sorted list of confirmed SwingPoints.

    Returns:
        List of StructurePoint objects with labels assigned.
    """
    if not swings:
        return []

    points: list[StructurePoint] = []

    # Track the last swing of each type for comparison
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None

    for swing in swings:
        if swing.swing_type == SwingType.SWING_HIGH:
            if last_high is None:
                label = StructureLabel.INITIAL
                reason = "First swing high — no prior swing to compare"
            elif swing.price > last_high.price:
                label = StructureLabel.HH
                reason = f"Price {swing.price:.2f} > prior high {last_high.price:.2f}"
            else:
                label = StructureLabel.LH
                reason = f"Price {swing.price:.2f} <= prior high {last_high.price:.2f}"

            points.append(StructurePoint(
                swing=swing,
                label=label,
                reason=reason,
            ))
            last_high = swing

        elif swing.swing_type == SwingType.SWING_LOW:
            if last_low is None:
                label = StructureLabel.INITIAL
                reason = "First swing low — no prior swing to compare"
            elif swing.price > last_low.price:
                label = StructureLabel.HL
                reason = f"Price {swing.price:.2f} > prior low {last_low.price:.2f}"
            else:
                label = StructureLabel.LL
                reason = f"Price {swing.price:.2f} <= prior low {last_low.price:.2f}"

            points.append(StructurePoint(
                swing=swing,
                label=label,
                reason=reason,
            ))
            last_low = swing

    logger.debug("Classified %d structure points", len(points))
    return points
