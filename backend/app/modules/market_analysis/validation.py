"""
Scalping Arise — Analysis Validation

Validates data context before analysis proceeds.
Ensures sufficient candle count, data freshness, and ordering.
Returns structured unavailable status when analysis cannot safely run.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_analysis.config import MarketAnalysisSettings, get_market_analysis_settings
from app.modules.market_analysis.models import AnalysisContext, AnalysisStatus, AnalysisResult
from app.modules.market_data.models import CandlesResponse, NormalizedCandle

logger = logging.getLogger(__name__)


def validate_analysis_context(
    candles_response: CandlesResponse,
    settings: Optional[MarketAnalysisSettings] = None,
) -> tuple[bool, str]:
    """
    Validate that the data context is suitable for analysis.

    Checks:
        1. Enough candles provided.
        2. Candles are chronologically ordered.
        3. Candles have valid timestamps (not all identical).
        4. Data is not excessively stale.

    Args:
        candles_response: The CandlesResponse from MarketDataService.
        settings: Optional settings override.

    Returns:
        Tuple of (is_valid, reason). If is_valid is False, reason explains why.
    """
    cfg = settings or get_market_analysis_settings()
    candles = candles_response.candles

    # Check minimum candle count
    closed_candles = [c for c in candles if c.is_closed]
    if len(closed_candles) < cfg.min_candles_for_analysis:
        return False, (
            f"Insufficient confirmed candles for analysis: "
            f"{len(closed_candles)} < {cfg.min_candles_for_analysis}"
        )

    # Check chronological ordering
    for i in range(1, len(candles)):
        if candles[i].timestamp < candles[i - 1].timestamp:
            return False, (
                f"Candles not in chronological order: "
                f"candle {i} timestamp {candles[i].timestamp} < candle {i-1} timestamp {candles[i-1].timestamp}"
            )

    # Check for duplicate timestamps (would break analysis)
    timestamps = [c.timestamp for c in candles]
    if len(timestamps) != len(set(timestamps)):
        return False, "Duplicate timestamps detected in candle data"

    # Check for all-same timestamps (degenerate data)
    if len(set(timestamps)) == 1:
        return False, "All candles have identical timestamps — cannot analyze"

    # Check freshness — warn if data is old but don't block
    if candles:
        latest_ts = max(c.timestamp for c in candles)
        age_seconds = (datetime.now(timezone.utc) - latest_ts).total_seconds()
        tolerance = cfg.min_candles_for_analysis * candles[0].timeframe.interval_seconds * 2
        if age_seconds > tolerance:
            logger.warning(
                "Data may be stale: latest candle is %d seconds old (tolerance: %d)",
                int(age_seconds), int(tolerance),
            )

    return True, "Data context validated successfully"


def build_analysis_context(
    candles_response: CandlesResponse,
) -> AnalysisContext:
    """
    Build the AnalysisContext from a CandlesResponse.

    Preserves all source metadata from Phase 2.
    """
    candles = candles_response.candles
    source_type = candles_response.source_type.value if candles_response.candles else "unknown"
    provider = candles[0].source if candles else "unknown"
    provider_instrument = candles[0].provider_instrument if candles else "unknown"

    return AnalysisContext(
        canonical_instrument=candles_response.instrument.value,
        provider_instrument=provider_instrument,
        provider=provider,
        source_type=source_type,
        timeframe=candles_response.timeframe.value,
        candle_count=len(candles),
        analysis_timestamp=datetime.now(timezone.utc),
        data_from_cache=(candles_response.source == "cache"),
    )
