"""
Scalping Arise — RSI (Relative Strength Index) Calculation

Deterministic RSI calculation with configurable period and thresholds.
No look-ahead bias.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.technical_features.config import TechnicalFeaturesSettings, get_technical_features_settings
from app.modules.technical_features.models import (
    FeatureAvailability,
    RSISessionState,
    RSIResult,
)
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


def calculate_rsi(
    candles: list[NormalizedCandle],
    period: int = 14,
    settings: Optional[TechnicalFeaturesSettings] = None,
) -> RSIResult:
    """
    Calculate RSI using the standard Wilder smoothing method.

    RSI = 100 - (100 / (1 + RS))
    RS = Average Gain / Average Loss over `period` candles.

    No look-ahead — each RSI value uses only data up to that candle.

    Args:
        candles: Chronologically sorted candle list.
        period: RSI lookback period.
        settings: Optional settings for threshold configuration.

    Returns:
        RSIResult with value, state, and evidence.
    """
    cfg = settings or get_technical_features_settings()
    required_history = period + 1  # Need period+1 candles for first RS calculation

    if len(candles) < required_history:
        return RSIResult(
            period=period,
            value=None,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            state=RSISessionState.NEUTRAL,
            required_history=required_history,
        )

    # Calculate price changes
    closes = [c.close for c in candles]
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    # Initial average gain/loss (simple average of first `period` changes)
    gains = [max(0, change) for change in changes[:period]]
    losses = [abs(min(0, change)) for change in changes[:period]]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    # Calculate RSI iteratively using Wilder smoothing
    rsi_values: list[Optional[float]] = [None] * period  # Not enough data yet

    if avg_loss == 0:
        rsi_values.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(round(100.0 - (100.0 / (1.0 + rs)), 2))

    # Wilder smoothing for subsequent values
    for i in range(period, len(changes)):
        change = changes[i]
        gain = max(0, change)
        loss = abs(min(0, change))

        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(round(100.0 - (100.0 / (1.0 + rs)), 2))

    latest_rsi = rsi_values[-1]

    if latest_rsi is None:
        return RSIResult(
            period=period,
            value=None,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            state=RSISessionState.NEUTRAL,
            required_history=required_history,
        )

    # Classify state
    if latest_rsi >= cfg.rsi_overbought_threshold:
        state = RSISessionState.OVERBOUGHT
    elif latest_rsi >= cfg.rsi_strong_threshold:
        state = RSISessionState.STRONG
    elif latest_rsi >= cfg.rsi_weak_threshold:
        state = RSISessionState.NEUTRAL
    elif latest_rsi >= cfg.rsi_oversold_threshold:
        state = RSISessionState.WEAK
    else:
        state = RSISessionState.OVERSOLD

    evidence = [
        f"RSI({period}) = {latest_rsi:.2f}",
        f"State: {state.value} (thresholds: <{cfg.rsi_oversold_threshold} oversold, "
        f">{cfg.rsi_overbought_threshold} overbought)",
    ]

    return RSIResult(
        period=period,
        value=latest_rsi,
        availability=FeatureAvailability.AVAILABLE,
        state=state,
        required_history=required_history,
        evidence=evidence,
    )
