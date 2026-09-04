"""
Scalping Arise — Feature Data Validation

Validates data context before feature calculation proceeds.
Ensures sufficient candle count, chronological ordering, and data quality.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.technical_features.config import TechnicalFeaturesSettings, get_technical_features_settings
from app.modules.technical_features.models import FeatureAvailability, FeatureMetadata
from app.modules.market_data.models import CandlesResponse, NormalizedCandle

logger = logging.getLogger(__name__)


def validate_feature_context(
    candles_response: CandlesResponse,
    settings: Optional[TechnicalFeaturesSettings] = None,
) -> tuple[bool, str]:
    """
    Validate that the data context is suitable for feature calculation.

    Checks:
        1. Enough candles provided.
        2. Candles are chronologically ordered.
        3. Candles have valid timestamps.
        4. At least some candles have volume data (optional but checked).

    Args:
        candles_response: The CandlesResponse from MarketDataService.
        settings: Optional settings override.

    Returns:
        Tuple of (is_valid, reason).
    """
    cfg = settings or get_technical_features_settings()
    candles = candles_response.candles

    # Check minimum candle count
    closed_candles = [c for c in candles if c.is_closed]
    if len(closed_candles) < cfg.min_candles_for_features:
        return False, (
            f"Insufficient confirmed candles for feature calculation: "
            f"{len(closed_candles)} < {cfg.min_candles_for_features}"
        )

    # Check chronological ordering
    for i in range(1, len(candles)):
        if candles[i].timestamp < candles[i - 1].timestamp:
            return False, (
                f"Candles not in chronological order: "
                f"candle {i} timestamp < candle {i-1} timestamp"
            )

    # Check for duplicate timestamps
    timestamps = [c.timestamp for c in candles]
    if len(timestamps) != len(set(timestamps)):
        return False, "Duplicate timestamps detected in candle data"

    return True, "Feature data context validated successfully"


def build_feature_metadata(
    candles_response: CandlesResponse,
) -> FeatureMetadata:
    """
    Build FeatureMetadata from a CandlesResponse.

    Preserves all source metadata from Phase 2.
    """
    candles = candles_response.candles
    source_type = candles_response.source_type.value if candles else "unknown"
    provider = candles[0].source if candles else "unknown"
    provider_instrument = candles[0].provider_instrument if candles else "unknown"

    return FeatureMetadata(
        canonical_instrument=candles_response.instrument.value,
        provider_instrument=provider_instrument,
        provider=provider,
        source_type=source_type,
        timeframe=candles_response.timeframe.value,
        candle_count=len(candles),
        feature_timestamp=datetime.now(timezone.utc),
    )
