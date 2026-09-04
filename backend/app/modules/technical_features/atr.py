"""
Scalping Arise — ATR (Average True Range) Calculation

Deterministic ATR with configurable period.
No look-ahead bias.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.technical_features.config import TechnicalFeaturesSettings, get_technical_features_settings
from app.modules.technical_features.models import (
    ATRResult,
    ATRVolatilityState,
    FeatureAvailability,
)
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


def calculate_true_ranges(candles: list[NormalizedCandle]) -> list[float]:
    """
    Calculate True Range for each candle.

    TR = max(High - Low, |High - Previous Close|, |Low - Previous Close|)

    First candle uses High - Low as TR.

    Args:
        candles: Chronologically sorted candle list.

    Returns:
        List of True Range values.
    """
    if not candles:
        return []

    tr_values: list[float] = []

    for i, candle in enumerate(candles):
        if i == 0:
            tr_values.append(candle.high - candle.low)
        else:
            prev_close = candles[i - 1].close
            hl = candle.high - candle.low
            hc = abs(candle.high - prev_close)
            lc = abs(candle.low - prev_close)
            tr_values.append(max(hl, hc, lc))

    return tr_values


def calculate_atr(
    candles: list[NormalizedCandle],
    period: int = 14,
    settings: Optional[TechnicalFeaturesSettings] = None,
) -> ATRResult:
    """
    Calculate ATR using Wilder smoothing.

    ATR = Wilder Smoothed Average of True Range.

    No look-ahead — each ATR value uses only data up to that candle.

    Args:
        candles: Chronologically sorted candle list.
        period: ATR lookback period.
        settings: Optional settings for threshold configuration.

    Returns:
        ATRResult with value, percentage, and state.
    """
    cfg = settings or get_technical_features_settings()
    required_history = period + 1  # Need period+1 candles for first ATR

    if len(candles) < required_history:
        return ATRResult(
            period=period,
            value=None,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            required_history=required_history,
        )

    tr_values = calculate_true_ranges(candles)

    # Initial ATR = simple average of first `period` true ranges
    initial_atr = sum(tr_values[:period]) / period

    # Wilder smoothing
    atr_values: list[Optional[float]] = [None] * period
    atr_values.append(initial_atr)

    for i in range(period, len(tr_values)):
        smoothed = (atr_values[-1] * (period - 1) + tr_values[i]) / period
        atr_values.append(smoothed)

    latest_atr = atr_values[-1]

    if latest_atr is None:
        return ATRResult(
            period=period,
            value=None,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            required_history=required_history,
        )

    # Calculate ATR as percentage of current price
    current_price = candles[-1].close
    atr_pct = (latest_atr / current_price * 100) if current_price > 0 else 0.0

    # Classify volatility state
    if atr_pct >= cfg.atr_high_threshold_pct:
        state = ATRVolatilityState.HIGH
    elif atr_pct <= cfg.atr_low_threshold_pct:
        state = ATRVolatilityState.LOW
    else:
        state = ATRVolatilityState.NORMAL

    evidence = [
        f"ATR({period}) = {latest_atr:.4f}",
        f"ATR% = {atr_pct:.3f}% of current price ({current_price:.2f})",
        f"Volatility state: {state.value} "
        f"(high>{cfg.atr_high_threshold_pct}%, low<{cfg.atr_low_threshold_pct}%)",
    ]

    return ATRResult(
        period=period,
        value=round(latest_atr, 6),
        percentage=round(atr_pct, 4),
        availability=FeatureAvailability.AVAILABLE,
        state=state,
        required_history=required_history,
        evidence=evidence,
    )
