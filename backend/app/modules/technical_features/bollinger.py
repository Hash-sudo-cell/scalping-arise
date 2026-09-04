"""
Scalping Arise — Bollinger Bands Calculation

Deterministic Bollinger Bands with configurable period and std deviation.
No look-ahead bias.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.technical_features.config import TechnicalFeaturesSettings, get_technical_features_settings
from app.modules.technical_features.models import (
    BollingerBandsResult,
    BollingerPosition,
    FeatureAvailability,
)
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


def calculate_bollinger_bands(
    candles: list[NormalizedCandle],
    period: int = 20,
    std_dev: float = 2.0,
    settings: Optional[TechnicalFeaturesSettings] = None,
) -> BollingerBandsResult:
    """
    Calculate Bollinger Bands (SMA ± std_dev * standard deviation).

    Middle Band = SMA(period)
    Upper Band = Middle + (std_dev * StdDev)
    Lower Band = Middle - (std_dev * StdDev)
    Band Width = (Upper - Lower) / Middle as percentage

    No look-ahead — each value uses only candles up to that point.

    Args:
        candles: Chronologically sorted candle list.
        period: SMA period.
        std_dev: Standard deviation multiplier.
        settings: Optional settings override.

    Returns:
        BollingerBandsResult with all bands and price position.
    """
    cfg = settings or get_technical_features_settings()
    required_history = period

    if len(candles) < required_history:
        return BollingerBandsResult(
            period=period,
            std_dev=std_dev,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            required_history=required_history,
        )

    # Use closes from the last `period` candles for SMA
    closes = [c.close for c in candles]
    window = closes[-period:]

    # Middle band = SMA
    middle = sum(window) / period

    # Standard deviation (population)
    variance = sum((c - middle) ** 2 for c in window) / period
    sd = variance ** 0.5

    upper = middle + (std_dev * sd)
    lower = middle - (std_dev * sd)

    # Band width as percentage
    band_width = ((upper - lower) / middle * 100) if middle > 0 else 0.0

    # Price position
    current_price = candles[-1].close
    if sd == 0:
        # Bands collapsed — price is exactly at middle
        position = BollingerPosition.MIDDLE_REGION
    elif current_price > upper:
        position = BollingerPosition.ABOVE_UPPER
    elif current_price > middle + (std_dev * sd * 0.5):
        position = BollingerPosition.UPPER_REGION
    elif current_price > middle - (std_dev * sd * 0.5):
        position = BollingerPosition.MIDDLE_REGION
    elif current_price > lower:
        position = BollingerPosition.LOWER_REGION
    else:
        position = BollingerPosition.BELOW_LOWER

    evidence = [
        f"Bollinger({period}, {std_dev}σ): Middle={middle:.2f}, Upper={upper:.2f}, Lower={lower:.2f}",
        f"Band width: {band_width:.2f}%",
        f"Current price ({current_price:.2f}) position: {position.value}",
    ]

    return BollingerBandsResult(
        period=period,
        std_dev=std_dev,
        middle_band=round(middle, 6),
        upper_band=round(upper, 6),
        lower_band=round(lower, 6),
        band_width=round(band_width, 4),
        price_position=position,
        availability=FeatureAvailability.AVAILABLE,
        required_history=required_history,
        evidence=evidence,
    )
