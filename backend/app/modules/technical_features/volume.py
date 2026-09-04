"""
Scalping Arise — Volume Features

Deterministic volume analysis with SMA and relative volume.
Volume is optional — must not fail other features if unavailable.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.technical_features.config import TechnicalFeaturesSettings, get_technical_features_settings
from app.modules.technical_features.models import (
    FeatureAvailability,
    VolumeResult,
    VolumeState,
)
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


def has_volume_data(candles: list[NormalizedCandle]) -> bool:
    """Check if any candles have volume data."""
    return any(c.volume is not None and c.volume > 0 for c in candles)


def calculate_volume_features(
    candles: list[NormalizedCandle],
    sma_period: int = 20,
    settings: Optional[TechnicalFeaturesSettings] = None,
) -> VolumeResult:
    """
    Calculate volume features: SMA, relative volume, and state.

    Relative Volume = Current Volume / SMA Volume

    Volume is optional — if no volume data exists, returns UNAVAILABLE
    without raising errors, allowing other features to continue.

    Args:
        candles: Chronologically sorted candle list.
        sma_period: Volume SMA period.
        settings: Optional settings for threshold configuration.

    Returns:
        VolumeResult with current volume, average, relative, and state.
    """
    cfg = settings or get_technical_features_settings()
    required_history = sma_period

    # Check if volume data exists at all
    if not has_volume_data(candles):
        return VolumeResult(
            sma_period=sma_period,
            current_volume=None,
            average_volume=None,
            relative_volume=None,
            availability=FeatureAvailability.UNAVAILABLE,
            state=VolumeState.UNAVAILABLE,
            required_history=required_history,
            evidence=["Volume data not available from provider — volume features skipped"],
        )

    if len(candles) < required_history:
        return VolumeResult(
            sma_period=sma_period,
            current_volume=None,
            average_volume=None,
            relative_volume=None,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            state=VolumeState.UNAVAILABLE,
            required_history=required_history,
        )

    # Extract volume values, treating None as 0
    volumes = [c.volume if c.volume is not None else 0.0 for c in candles]

    current_volume = volumes[-1]
    sma_window = volumes[-sma_period:]
    average_volume = sum(sma_window) / sma_period

    # Relative volume
    relative_volume = (current_volume / average_volume) if average_volume > 0 else 0.0

    # Classify state
    if relative_volume >= cfg.volume_high_threshold:
        state = VolumeState.HIGH
    elif relative_volume <= cfg.volume_low_threshold:
        state = VolumeState.LOW
    else:
        state = VolumeState.NORMAL

    evidence = [
        f"Current volume: {current_volume:.0f}",
        f"Volume SMA({sma_period}): {average_volume:.0f}",
        f"Relative volume: {relative_volume:.2f}x",
        f"Volume state: {state.value} "
        f"(high>{cfg.volume_high_threshold}x, low<{cfg.volume_low_threshold}x)",
    ]

    return VolumeResult(
        sma_period=sma_period,
        current_volume=round(current_volume, 2),
        average_volume=round(average_volume, 2),
        relative_volume=round(relative_volume, 4),
        availability=FeatureAvailability.AVAILABLE,
        state=state,
        required_history=required_history,
        evidence=evidence,
    )
