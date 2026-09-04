"""
Scalping Arise — BOS and CHOCH Detection

Break of Structure (BOS) and Change of Character (CHOCH) detection.

BOS: Price breaks a relevant confirmed structural swing in the direction
     of the existing trend.

CHOCH: Price breaks a relevant confirmed structural swing against the
       existing trend, signaling a potential structural shift.

Both require close-based confirmation by default (configurable).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_analysis.models import (
    BOSDirection,
    BOSEvent,
    CHOCHDirection,
    CHOCHEvent,
    StructureLabel,
    StructurePoint,
    SwingType,
    TrendState,
)
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


def detect_bos(
    candles: list[NormalizedCandle],
    structure_points: list[StructurePoint],
    current_trend: TrendState,
    confirmation_mode: str = "close",
    min_break_pct: float = 0.0,
) -> list[BOSEvent]:
    """
    Detect Break of Structure events.

    Logic:
        - For each candle after the last structure point:
        - BULLISH BOS: Price closes above the most recent swing high
          when the trend is BULLISH or UNCLEAR.
        - BEARISH BOS: Price closes below the most recent swing low
          when the trend is BEARISH or UNCLEAR.

    Args:
        candles: Sorted candle list.
        structure_points: Classified structure points.
        current_trend: Current trend state.
        confirmation_mode: 'close' for close-based, 'wick' for wick-based.
        min_break_pct: Minimum break distance as % of broken level.

    Returns:
        List of BOSEvent objects.
    """
    if not structure_points or not candles:
        return []

    events: list[BOSEvent] = []
    timeframe = candles[0].timeframe.value

    # Find the last swing high and swing low from structure
    last_high_point: Optional[StructurePoint] = None
    last_low_point: Optional[StructurePoint] = None

    for sp in reversed(structure_points):
        if sp.swing.swing_type == SwingType.SWING_HIGH and last_high_point is None:
            last_high_point = sp
        if sp.swing.swing_type == SwingType.SWING_LOW and last_low_point is None:
            last_low_point = sp
        if last_high_point and last_low_point:
            break

    if not last_high_point and not last_low_point:
        return []

    # Check candles after the latest structure point
    latest_structure_idx = max(
        sp.swing.index for sp in structure_points
    )

    for candle in candles[latest_structure_idx + 1:]:
        # Bullish BOS: close above swing high
        if last_high_point is not None:
            level = last_high_point.swing.price
            break_price = candle.close if confirmation_mode == "close" else candle.high
            min_distance = level * (1 + min_break_pct / 100)

            if break_price > min_distance:
                if current_trend in (TrendState.BULLISH, TrendState.UNCLEAR, TrendState.RANGING):
                    event = BOSEvent(
                        direction=BOSDirection.BULLISH_BOS,
                        broken_level=level,
                        break_price=break_price,
                        break_timestamp=candle.timestamp,
                        confirmation_basis=f"{confirmation_mode}_above",
                        timeframe=timeframe,
                        evidence=(
                            f"Closed above swing high at {level:.2f} "
                            f"(break price: {break_price:.2f})"
                        ),
                    )
                    events.append(event)
                    logger.debug("Bullish BOS at %s: broke %.2f", candle.timestamp, level)
                    last_high_point = None  # Consumed — need fresh swing

        # Bearish BOS: close below swing low
        if last_low_point is not None:
            level = last_low_point.swing.price
            break_price = candle.close if confirmation_mode == "close" else candle.low
            min_distance = level * (1 - min_break_pct / 100)

            if break_price < min_distance:
                if current_trend in (TrendState.BEARISH, TrendState.UNCLEAR, TrendState.RANGING):
                    event = BOSEvent(
                        direction=BOSDirection.BEARISH_BOS,
                        broken_level=level,
                        break_price=break_price,
                        break_timestamp=candle.timestamp,
                        confirmation_basis=f"{confirmation_mode}_below",
                        timeframe=timeframe,
                        evidence=(
                            f"Closed below swing low at {level:.2f} "
                            f"(break price: {break_price:.2f})"
                        ),
                    )
                    events.append(event)
                    logger.debug("Bearish BOS at %s: broke %.2f", candle.timestamp, level)
                    last_low_point = None  # Consumed

    return events


def detect_choch(
    candles: list[NormalizedCandle],
    structure_points: list[StructurePoint],
    current_trend: TrendState,
    confirmation_mode: str = "close",
    min_break_pct: float = 0.0,
) -> list[CHOCHEvent]:
    """
    Detect Change of Character events.

    CHOCH occurs when price breaks a structural level AGAINST the current trend,
    signaling a potential structural shift.

    Logic:
        - BULLISH CHOCH: During BEARISH trend, price closes above a recent swing high.
        - BEARISH CHOCH: During BULLISH trend, price closes below a recent swing low.

    BOS and CHOCH are mutually exclusive for the same candle — if a break
    qualifies as BOS, it is NOT also CHOCH.

    Args:
        candles: Sorted candle list.
        structure_points: Classified structure points.
        current_trend: Current trend state.
        confirmation_mode: 'close' for close-based, 'wick' for wick-based.
        min_break_pct: Minimum break distance as % of broken level.

    Returns:
        List of CHOCHEvent objects.
    """
    if not structure_points or not candles:
        return []

    # CHOCH only applies when we have a clear directional trend
    if current_trend not in (TrendState.BULLISH, TrendState.BEARISH):
        return []

    events: list[CHOCHEvent] = []
    timeframe = candles[0].timeframe.value

    # Find relevant swing points for CHOCH detection
    last_high_point: Optional[StructurePoint] = None
    last_low_point: Optional[StructurePoint] = None

    for sp in reversed(structure_points):
        if sp.swing.swing_type == SwingType.SWING_HIGH and last_high_point is None:
            last_high_point = sp
        if sp.swing.swing_type == SwingType.SWING_LOW and last_low_point is None:
            last_low_point = sp
        if last_high_point and last_low_point:
            break

    if not last_high_point and not last_low_point:
        return []

    latest_structure_idx = max(sp.swing.index for sp in structure_points)

    # Get the sequence of structure labels for context
    recent_labels = [sp.label for sp in structure_points[-6:]]
    prior_structure_desc = " -> ".join(l.value for l in recent_labels) if recent_labels else "none"

    for candle in candles[latest_structure_idx + 1:]:
        # BULLISH CHOCH: bearish trend, price breaks above swing high
        if current_trend == TrendState.BEARISH and last_high_point is not None:
            level = last_high_point.swing.price
            break_price = candle.close if confirmation_mode == "close" else candle.high
            min_distance = level * (1 + min_break_pct / 100)

            if break_price > min_distance:
                event = CHOCHEvent(
                    direction=CHOCHDirection.BULLISH_CHOCH,
                    broken_level=level,
                    break_price=break_price,
                    break_timestamp=candle.timestamp,
                    confirmation_basis=f"{confirmation_mode}_above",
                    prior_structure=prior_structure_desc,
                    timeframe=timeframe,
                    evidence=(
                        f"Bearish context broken: closed above swing high at {level:.2f} "
                        f"(break price: {break_price:.2f})"
                    ),
                )
                events.append(event)
                logger.debug("Bullish CHOCH at %s: broke %.2f", candle.timestamp, level)
                last_high_point = None

        # BEARISH CHOCH: bullish trend, price breaks below swing low
        if current_trend == TrendState.BULLISH and last_low_point is not None:
            level = last_low_point.swing.price
            break_price = candle.close if confirmation_mode == "close" else candle.low
            min_distance = level * (1 - min_break_pct / 100)

            if break_price < min_distance:
                event = CHOCHEvent(
                    direction=CHOCHDirection.BEARISH_CHOCH,
                    broken_level=level,
                    break_price=break_price,
                    break_timestamp=candle.timestamp,
                    confirmation_basis=f"{confirmation_mode}_below",
                    prior_structure=prior_structure_desc,
                    timeframe=timeframe,
                    evidence=(
                        f"Bullish context broken: closed below swing low at {level:.2f} "
                        f"(break price: {break_price:.2f})"
                    ),
                )
                events.append(event)
                logger.debug("Bearish CHOCH at %s: broke %.2f", candle.timestamp, level)
                last_low_point = None

    return events
