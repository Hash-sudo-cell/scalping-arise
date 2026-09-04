"""
Scalping Arise — Basic Price Features

Deterministic price context features derived from candle data.
No look-ahead bias.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.technical_features.config import TechnicalFeaturesSettings, get_technical_features_settings
from app.modules.technical_features.models import (
    FeatureAvailability,
    PriceFeatures,
)
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


def calculate_price_features(
    candles: list[NormalizedCandle],
    lookback: int = 20,
    settings: Optional[TechnicalFeaturesSettings] = None,
) -> PriceFeatures:
    """
    Calculate basic price context features.

    - Current price and previous close
    - Absolute and percentage change
    - Recent high, low, and range
    - Position in range (0.0 = at low, 1.0 = at high)

    No look-ahead — uses only candles available at calculation time.

    Args:
        candles: Chronologically sorted candle list.
        lookback: Number of candles for recent range calculation.
        settings: Optional settings override.

    Returns:
        PriceFeatures with price context data.
    """
    cfg = settings or get_technical_features_settings()
    effective_lookback = min(lookback, cfg.price_lookback)
    required_history = 2  # Need at least 2 candles for change calculation

    if len(candles) < required_history:
        return PriceFeatures(
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            lookback=effective_lookback,
        )

    current_price = candles[-1].close
    previous_close = candles[-2].close

    # Changes
    absolute_change = current_price - previous_close
    percentage_change = (absolute_change / previous_close * 100) if previous_close != 0 else 0.0

    # Recent high/low over lookback window
    window = candles[-effective_lookback:]
    recent_high = max(c.high for c in window)
    recent_low = min(c.low for c in window)
    recent_range = recent_high - recent_low

    # Position in range
    if recent_range > 0:
        position_in_range = (current_price - recent_low) / recent_range
    else:
        position_in_range = 0.5  # Default to middle if no range

    evidence = [
        f"Current price: {current_price:.2f}",
        f"Previous close: {previous_close:.2f}",
        f"Change: {absolute_change:+.2f} ({percentage_change:+.3f}%)",
        f"Recent {effective_lookback} range: {recent_low:.2f} – {recent_high:.2f} (width: {recent_range:.2f})",
        f"Position in range: {position_in_range:.2%}",
    ]

    return PriceFeatures(
        current_price=round(current_price, 6),
        previous_close=round(previous_close, 6),
        absolute_change=round(absolute_change, 6),
        percentage_change=round(percentage_change, 4),
        recent_high=round(recent_high, 6),
        recent_low=round(recent_low, 6),
        recent_range=round(recent_range, 6),
        position_in_range=round(position_in_range, 4),
        availability=FeatureAvailability.AVAILABLE,
        lookback=effective_lookback,
        evidence=evidence,
    )
