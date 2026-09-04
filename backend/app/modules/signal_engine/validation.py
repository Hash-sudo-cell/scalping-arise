"""
Scalping Arise — Input Validation

Validates inputs to the signal engine before evaluation begins.
"""

from __future__ import annotations

from app.modules.market_data.models import Instrument, Timeframe


def validate_instrument(instrument: str) -> Instrument:
    """Validate and return a canonical Instrument."""
    try:
        return Instrument(instrument)
    except ValueError:
        allowed = [i.value for i in Instrument]
        raise ValueError(
            f"Unsupported instrument: {instrument}. Allowed: {allowed}"
        )


def validate_timeframes(timeframes: list[str]) -> list[str]:
    """Validate that all timeframes are supported."""
    if not timeframes:
        raise ValueError("No timeframes provided")

    valid_values = {tf.value for tf in Timeframe}
    invalid = [tf for tf in timeframes if tf not in valid_values]
    if invalid:
        raise ValueError(
            f"Invalid timeframes: {invalid}. Valid: {sorted(valid_values)}"
        )
    return timeframes


def validate_candle_limit(limit: int) -> int:
    """Validate candle limit is within acceptable range."""
    if limit < 50 or limit > 5000:
        raise ValueError(f"Candle limit must be 50-5000, got {limit}")
    return limit
