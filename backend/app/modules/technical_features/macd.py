"""
Scalping Arise — MACD (Moving Average Convergence Divergence) Calculation

Deterministic MACD with configurable parameters.
No look-ahead bias.

Staged component availability:
- macd_line: AVAILABLE once both fast and slow EMAs exist (slow_period candles)
- signal_line: AVAILABLE once enough MACD values exist for signal EMA
- histogram: AVAILABLE once both macd_line and signal_line are available
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.technical_features.config import TechnicalFeaturesSettings, get_technical_features_settings
from app.modules.technical_features.models import (
    FeatureAvailability,
    MACDContext,
    MACDResult,
)
from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


def _ema_series(closes: list[float], period: int) -> list[Optional[float]]:
    """Calculate EMA series for MACD internal use."""
    if period <= 0 or len(closes) < period:
        return [None] * len(closes)

    result: list[Optional[float]] = [None] * (period - 1)
    sma_seed = sum(closes[:period]) / period
    result.append(sma_seed)

    multiplier = 2.0 / (period + 1)
    prev_ema = sma_seed

    for i in range(period, len(closes)):
        ema = (closes[i] - prev_ema) * multiplier + prev_ema
        result.append(ema)
        prev_ema = ema

    return result


def calculate_macd(
    candles: list[NormalizedCandle],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    settings: Optional[TechnicalFeaturesSettings] = None,
) -> MACDResult:
    """
    Calculate MACD line, signal line, and histogram with staged availability.

    Staged warm-up:
    1. < slow_period candles: everything INSUFFICIENT_DATA
    2. slow_period <= candles < slow_period + signal_period:
       macd_line AVAILABLE, signal_line/histogram INSUFFICIENT_DATA
    3. >= slow_period + signal_period candles: all AVAILABLE

    No look-ahead — all values use only data up to each point.

    Args:
        candles: Chronologically sorted candle list.
        fast_period: Fast EMA period.
        slow_period: Slow EMA period.
        signal_period: Signal line EMA period.
        settings: Optional settings override.

    Returns:
        MACDResult with all MACD components and staged availability.
    """
    cfg = settings or get_technical_features_settings()
    # MACD line needs slow_period candles (for slow EMA to initialize)
    macd_line_required = slow_period
    # Full MACD needs slow_period + signal_period candles
    full_required = slow_period + signal_period

    closes = [c.close for c in candles]

    # Stage 0: Not enough candles for even the slow EMA
    if len(closes) < macd_line_required:
        return MACDResult(
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=signal_period,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            macd_line_availability=FeatureAvailability.INSUFFICIENT_DATA,
            signal_line_availability=FeatureAvailability.INSUFFICIENT_DATA,
            histogram_availability=FeatureAvailability.INSUFFICIENT_DATA,
            required_history=full_required,
        )

    # Calculate EMAs
    ema_fast = _ema_series(closes, fast_period)
    ema_slow = _ema_series(closes, slow_period)

    # MACD line — only where both EMAs are available
    macd_line_series: list[Optional[float]] = []
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line_series.append(ema_fast[i] - ema_slow[i])
        else:
            macd_line_series.append(None)

    latest_macd = macd_line_series[-1]

    # Stage 1: MACD line available but not enough for signal
    valid_macd = [v for v in macd_line_series if v is not None]

    if len(valid_macd) < signal_period:
        return MACDResult(
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=signal_period,
            macd_line=round(latest_macd, 6) if latest_macd is not None else None,
            availability=FeatureAvailability.INSUFFICIENT_DATA,
            macd_line_availability=FeatureAvailability.AVAILABLE if latest_macd is not None else FeatureAvailability.INSUFFICIENT_DATA,
            signal_line_availability=FeatureAvailability.INSUFFICIENT_DATA,
            histogram_availability=FeatureAvailability.INSUFFICIENT_DATA,
            required_history=full_required,
        )

    # Signal line — EMA of MACD line
    signal_series = _ema_series(valid_macd, signal_period)

    # Align signal series back to original indices
    offset = len(valid_macd) - len(signal_series)
    full_signal: list[Optional[float]] = [None] * offset + signal_series

    latest_signal = full_signal[-1] if full_signal else None
    latest_histogram = (latest_macd - latest_signal) if (latest_macd is not None and latest_signal is not None) else None

    # Context — only when both macd_line and signal_line are available
    context = MACDContext.NEUTRAL
    evidence: list[str] = []

    if latest_macd is not None and latest_signal is not None:
        if latest_macd > 0 and latest_signal > 0 and latest_macd > latest_signal:
            context = MACDContext.BULLISH
            evidence = [
                f"MACD line ({latest_macd:.4f}) above signal ({latest_signal:.4f})",
                f"Both positive — bullish momentum",
            ]
        elif latest_macd < 0 and latest_signal < 0 and latest_macd < latest_signal:
            context = MACDContext.BEARISH
            evidence = [
                f"MACD line ({latest_macd:.4f}) below signal ({latest_signal:.4f})",
                f"Both negative — bearish momentum",
            ]
        else:
            evidence = [
                f"MACD line ({latest_macd:.4f}), signal ({latest_signal:.4f})",
                f"Mixed positioning — neutral context",
            ]

    return MACDResult(
        fast_period=fast_period,
        slow_period=slow_period,
        signal_period=signal_period,
        macd_line=round(latest_macd, 6) if latest_macd is not None else None,
        signal_line=round(latest_signal, 6) if latest_signal is not None else None,
        histogram=round(latest_histogram, 6) if latest_histogram is not None else None,
        availability=FeatureAvailability.AVAILABLE,
        macd_line_availability=FeatureAvailability.AVAILABLE,
        signal_line_availability=FeatureAvailability.AVAILABLE,
        histogram_availability=FeatureAvailability.AVAILABLE,
        context=context,
        required_history=full_required,
        evidence=evidence,
    )
