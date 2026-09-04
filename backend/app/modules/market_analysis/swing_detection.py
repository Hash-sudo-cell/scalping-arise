"""
Scalping Arise — Swing Detection

Deterministic swing-high and swing-low detection.
A swing high is a candle whose high is higher than the high of
`lookback` candles on each side. A swing low is symmetric.

All logic operates on NormalizedCandle lists — no provider specifics.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.market_analysis.models import SwingPoint, SwingType
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


def detect_swings(
    candles: list[NormalizedCandle],
    lookback: int = 3,
) -> list[SwingPoint]:
    """
    Detect swing highs and swing lows in a sorted candle list.

    Algorithm:
        For each candle at index i (where i >= lookback and i < len - lookback):
        - Swing High: candle.high >= all highs in [i-lookback, i+lookback]
        - Swing Low:  candle.low  <= all lows  in [i-lookback, i+lookback]

    Candles that don't meet the lookback window are skipped.

    Args:
        candles: Chronologically sorted list of NormalizedCandles.
        lookback: Number of candles on each side to confirm the swing.

    Returns:
        List of confirmed SwingPoint objects, ordered by timestamp.
    """
    if len(candles) < (2 * lookback + 1):
        logger.debug(
            "Not enough candles for swing detection: %d < %d",
            len(candles), 2 * lookback + 1,
        )
        return []

    swings: list[SwingPoint] = []
    timeframe = candles[0].timeframe.value

    for i in range(lookback, len(candles) - lookback):
        candle = candles[i]

        # Check swing high
        is_high = True
        for j in range(i - lookback, i + lookback + 1):
            if j == i:
                continue
            if candles[j].high >= candle.high:
                is_high = False
                break

        if is_high:
            swings.append(SwingPoint(
                index=i,
                timestamp=candle.timestamp,
                price=candle.high,
                swing_type=SwingType.SWING_HIGH,
                confirmed=True,
                timeframe=timeframe,
            ))

        # Check swing low
        is_low = True
        for j in range(i - lookback, i + lookback + 1):
            if j == i:
                continue
            if candles[j].low <= candle.low:
                is_low = False
                break

        if is_low:
            swings.append(SwingPoint(
                index=i,
                timestamp=candle.timestamp,
                price=candle.low,
                swing_type=SwingType.SWING_LOW,
                confirmed=True,
                timeframe=timeframe,
            ))

    # Sort by timestamp, then by type (swing_low first at same timestamp)
    swings.sort(key=lambda s: (s.timestamp, s.swing_type.value))

    logger.debug("Detected %d swings in %d candles", len(swings), len(candles))
    return swings
