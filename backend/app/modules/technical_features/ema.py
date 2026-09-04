"""
Scalping Arise — EMA (Exponential Moving Average) Calculation

Deterministic EMA calculation with configurable periods.
No look-ahead bias — each value uses only candles up to that point.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.technical_features.config import TechnicalFeaturesSettings, get_technical_features_settings
from app.modules.technical_features.models import (
    EMAAlignment,
    EMADirection,
    EMAValue,
    EMAResult,
    FeatureAvailability,
)
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


def calculate_ema_series(candles: list[NormalizedCandle], period: int) -> list[Optional[float]]:
    """
    Calculate EMA for each candle using only data available up to that point.

    Uses SMA as the seed for the first EMA value.

    Args:
        candles: Chronologically sorted candle list.
        period: EMA period.

    Returns:
        List of EMA values (None for candles where EMA is not yet initialized).
    """
    if period <= 0 or len(candles) < period:
        return [None] * len(candles)

    closes = [c.close for c in candles]
    result: list[Optional[float]] = [None] * (period - 1)

    # Seed with SMA of first `period` closes
    sma_seed = sum(closes[:period]) / period
    result.append(sma_seed)

    # Calculate EMA iteratively — no look-ahead
    multiplier = 2.0 / (period + 1)
    prev_ema = sma_seed

    for i in range(period, len(closes)):
        ema = (closes[i] - prev_ema) * multiplier + prev_ema
        result.append(ema)
        prev_ema = ema

    return result


def calculate_ema(
    candles: list[NormalizedCandle],
    period: int,
) -> EMAValue:
    """
    Calculate a single EMA feature.

    Args:
        candles: Chronologically sorted candle list.
        period: EMA period.

    Returns:
        EMAValue with the latest EMA calculation.
    """
    required_history = period

    if len(candles) < required_history:
        return EMAValue(
            period=period,
            value=None,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            direction=EMADirection.UNKNOWN,
            required_history=required_history,
        )

    ema_series = calculate_ema_series(candles, period)
    latest_ema = ema_series[-1]

    if latest_ema is None:
        return EMAValue(
            period=period,
            value=None,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            direction=EMADirection.UNKNOWN,
            required_history=required_history,
        )

    # Determine direction by comparing to previous EMA
    prev_ema = ema_series[-2] if len(ema_series) > 1 else None
    if prev_ema is not None and prev_ema is not None:
        diff_pct = (latest_ema - prev_ema) / prev_ema * 100
        if diff_pct > 0.01:
            direction = EMADirection.RISING
        elif diff_pct < -0.01:
            direction = EMADirection.FALLING
        else:
            direction = EMADirection.FLAT
    else:
        direction = EMADirection.UNKNOWN

    # Price relative to EMA
    current_price = candles[-1].close
    if current_price > latest_ema:
        price_relative = "above"
    elif current_price < latest_ema:
        price_relative = "below"
    else:
        price_relative = "at"

    return EMAValue(
        period=period,
        value=round(latest_ema, 6),
        availability=FeatureAvailability.AVAILABLE,
        direction=direction,
        price_relative=price_relative,
        required_history=required_history,
    )


def calculate_ema_features(
    candles: list[NormalizedCandle],
    settings: Optional[TechnicalFeaturesSettings] = None,
) -> EMAResult:
    """
    Calculate complete EMA feature set (fast, medium, slow) with alignment.

    Args:
        candles: Chronologically sorted candle list.
        settings: Optional settings override.

    Returns:
        EMAResult with all EMA features and alignment.
    """
    cfg = settings or get_technical_features_settings()

    fast = calculate_ema(candles, cfg.ema_fast_period)
    medium = calculate_ema(candles, cfg.ema_medium_period)
    slow = calculate_ema(candles, cfg.ema_slow_period)

    # Determine alignment
    alignment = EMAAlignment.UNAVAILABLE
    alignment_evidence: list[str] = []

    if (fast.availability == FeatureAvailability.AVAILABLE
            and medium.availability == FeatureAvailability.AVAILABLE
            and slow.availability == FeatureAvailability.AVAILABLE
            and fast.value is not None
            and medium.value is not None
            and slow.value is not None):

        current_price = candles[-1].close
        price_above_fast = current_price > fast.value
        fast_above_medium = fast.value > medium.value
        medium_above_slow = medium.value > slow.value

        if price_above_fast and fast_above_medium and medium_above_slow:
            alignment = EMAAlignment.BULLISH
            alignment_evidence = [
                f"Price ({current_price:.2f}) above EMA{cfg.ema_fast_period}",
                f"EMA{cfg.ema_fast_period} ({fast.value:.2f}) above EMA{cfg.ema_medium_period}",
                f"EMA{cfg.ema_medium_period} ({medium.value:.2f}) above EMA{cfg.ema_slow_period}",
            ]
        elif not price_above_fast and not fast_above_medium and not medium_above_slow:
            alignment = EMAAlignment.BEARISH
            alignment_evidence = [
                f"Price ({current_price:.2f}) below EMA{cfg.ema_fast_period}",
                f"EMA{cfg.ema_fast_period} ({fast.value:.2f}) below EMA{cfg.ema_medium_period}",
                f"EMA{cfg.ema_medium_period} ({medium.value:.2f}) below EMA{cfg.ema_slow_period}",
            ]
        else:
            alignment = EMAAlignment.MIXED
            alignment_evidence = ["EMA ordering is mixed — no clean bullish or bearish alignment"]

    return EMAResult(
        fast=fast,
        medium=medium,
        slow=slow,
        alignment=alignment,
        alignment_evidence=alignment_evidence,
    )
