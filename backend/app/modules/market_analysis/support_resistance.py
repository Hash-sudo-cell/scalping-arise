"""
Scalping Arise — Support and Resistance Zone Detection

Deterministic S/R zone identification based on confirmed swing points.
Zones are grouped by proximity (configurable tolerance).
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.market_analysis.models import (
    StructurePoint,
    SupportResistanceZone,
    SwingType,
    ZoneType,
)

logger = logging.getLogger(__name__)


def detect_zones(
    structure_points: list[StructurePoint],
    tolerance_pct: float = 0.1,
    min_swings: int = 2,
    timeframe: str = "",
) -> tuple[list[SupportResistanceZone], list[SupportResistanceZone]]:
    """
    Detect support and resistance zones from structure points.

    Algorithm:
        1. Collect all swing highs and swing lows from structure points.
        2. Sort all swing prices.
        3. Group swings within tolerance_pct of each other into zones.
        4. Classify each zone as SUPPORT (built from swing lows) or
           RESISTANCE (built from swing highs).
        5. Zones with >= min_swings are kept.

    Args:
        structure_points: Classified structure points.
        tolerance_pct: Percentage tolerance for grouping swings into zones.
        min_swings: Minimum swings to define a zone.
        timeframe: Timeframe label for the zones.

    Returns:
        Tuple of (support_zones, resistance_zones).
    """
    if not structure_points:
        return [], []

    # Separate swing highs and swing lows
    swing_highs: list[tuple[float, int]] = []
    swing_lows: list[tuple[float, int]] = []

    for sp in structure_points:
        price = sp.swing.price
        idx = sp.swing.index
        if sp.swing.swing_type == SwingType.SWING_HIGH:
            swing_highs.append((price, idx))
        elif sp.swing.swing_type == SwingType.SWING_LOW:
            swing_lows.append((price, idx))

    # Detect zones for highs (resistance) and lows (support)
    resistance_zones = _group_swings_into_zones(
        swing_highs, ZoneType.RESISTANCE, tolerance_pct, min_swings, timeframe,
    )
    support_zones = _group_swings_into_zones(
        swing_lows, ZoneType.SUPPORT, tolerance_pct, min_swings, timeframe,
    )

    logger.debug(
        "Detected %d support and %d resistance zones",
        len(support_zones), len(resistance_zones),
    )
    return support_zones, resistance_zones


def _group_swings_into_zones(
    swings: list[tuple[float, int]],
    zone_type: ZoneType,
    tolerance_pct: float,
    min_swings: int,
    timeframe: str,
) -> list[SupportResistanceZone]:
    """
    Group a list of swing prices into zones.

    Swings within tolerance_pct of each other are merged into one zone.
    """
    if not swings:
        return []

    # Sort by price
    sorted_swings = sorted(swings, key=lambda s: s[0])

    zones: list[SupportResistanceZone] = []
    current_group: list[tuple[float, int]] = [sorted_swings[0]]

    for i in range(1, len(sorted_swings)):
        price, idx = sorted_swings[i]
        group_center = sum(p for p, _ in current_group) / len(current_group)
        tolerance = group_center * (tolerance_pct / 100)

        if abs(price - group_center) <= tolerance:
            current_group.append((price, idx))
        else:
            # Finalize current group
            zone = _create_zone(current_group, zone_type, timeframe)
            if zone is not None and zone.strength >= min_swings:
                zones.append(zone)
            current_group = [(price, idx)]

    # Finalize last group
    zone = _create_zone(current_group, zone_type, timeframe)
    if zone is not None and zone.strength >= min_swings:
        zones.append(zone)

    return zones


def _create_zone(
    swings: list[tuple[float, int]],
    zone_type: ZoneType,
    timeframe: str,
) -> Optional[SupportResistanceZone]:
    """Create a SupportResistanceZone from a group of swings."""
    if not swings:
        return None

    prices = [p for p, _ in swings]
    indices = [i for _, i in swings]

    return SupportResistanceZone(
        zone_type=zone_type,
        lower_bound=min(prices),
        upper_bound=max(prices),
        strength=len(swings),
        source_swings=indices,
        timeframe=timeframe,
    )
