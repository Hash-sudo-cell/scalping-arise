"""
Scalping Arise — Market Data Validation

Validates candles, timestamps, duplicates, gaps, and freshness
before data enters the internal hub.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.modules.market_data.models import (
    Instrument,
    NormalizedCandle,
    Timeframe,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OHLC validation
# ---------------------------------------------------------------------------

class CandleValidationError(Exception):
    """Raised when a candle fails validation."""

    def __init__(self, message: str, candle: Optional[NormalizedCandle] = None):
        super().__init__(message)
        self.candle = candle


def validate_ohlc(candle: NormalizedCandle) -> None:
    """
    Validate OHLC price relationships.

    Rules:
        - All prices > 0
        - High >= Low
        - High >= Open, High >= Close
        - Low <= Open, Low <= Close
        - All prices are finite
    """
    prices = {"open": candle.open, "high": candle.high, "low": candle.low, "close": candle.close}

    for name, price in prices.items():
        if price <= 0:
            raise CandleValidationError(
                f"{name} price must be > 0, got {price}",
                candle=candle,
            )
        if not (price == price):  # NaN check
            raise CandleValidationError(
                f"{name} price is NaN",
                candle=candle,
            )

    if candle.high < candle.low:
        raise CandleValidationError(
            f"High ({candle.high}) < Low ({candle.low})",
            candle=candle,
        )
    if candle.high < candle.open:
        raise CandleValidationError(
            f"High ({candle.high}) < Open ({candle.open})",
            candle=candle,
        )
    if candle.high < candle.close:
        raise CandleValidationError(
            f"High ({candle.high}) < Close ({candle.close})",
            candle=candle,
        )
    if candle.low > candle.open:
        raise CandleValidationError(
            f"Low ({candle.low}) > Open ({candle.open})",
            candle=candle,
        )
    if candle.low > candle.close:
        raise CandleValidationError(
            f"Low ({candle.low}) > Close ({candle.close})",
            candle=candle,
        )


# ---------------------------------------------------------------------------
# Timestamp validation
# ---------------------------------------------------------------------------

def validate_timestamp(candle: NormalizedCandle, tolerance_future_seconds: int = 300) -> None:
    """
    Validate candle timestamp.

    - Must not be None (already guaranteed by model)
    - Must not be excessively in the future (> tolerance)
    - Must be a valid datetime
    """
    now = datetime.now(timezone.utc)
    ts = candle.timestamp

    if ts > now + timedelta(seconds=tolerance_future_seconds):
        raise CandleValidationError(
            f"Timestamp {ts.isoformat()} is too far in the future (now={now.isoformat()})",
            candle=candle,
        )


# ---------------------------------------------------------------------------
# Full candle validation
# ---------------------------------------------------------------------------

def validate_candle(
    candle: NormalizedCandle,
    allowed_instruments: Optional[list[Instrument]] = None,
    allowed_timeframes: Optional[list[Timeframe]] = None,
) -> list[str]:
    """
    Run all validation checks on a candle.

    Returns a list of warning messages (empty = valid).
    Raises CandleValidationError on hard failures.
    """
    warnings: list[str] = []

    # OHLC validation (hard fail)
    validate_ohlc(candle)

    # Timestamp validation (hard fail)
    validate_timestamp(candle)

    # Instrument check
    if allowed_instruments is not None and candle.instrument not in allowed_instruments:
        raise CandleValidationError(
            f"Instrument {candle.instrument.value} not in allowed list",
            candle=candle,
        )

    # Timeframe check
    if allowed_timeframes is not None and candle.timeframe not in allowed_timeframes:
        raise CandleValidationError(
            f"Timeframe {candle.timeframe.value} not in allowed list",
            candle=candle,
        )

    # Volume warning (soft)
    if candle.volume is not None and candle.volume < 0:
        warnings.append(f"Negative volume: {candle.volume}")

    return warnings


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

class DuplicateType(str):
    EXACT = "exact"
    FORMING_UPDATE = "forming_update"
    CONFLICTING = "conflicting"


def classify_duplicate(
    existing: NormalizedCandle,
    incoming: NormalizedCandle,
) -> str:
    """
    Classify the relationship between an existing and incoming candle.

    Returns:
        "exact" - Same OHLCV, can be ignored
        "forming_update" - Same timestamp, incoming is forming (update allowed)
        "conflicting" - Same timestamp, different OHLC on closed candle
    """
    same_timestamp = existing.timestamp == incoming.timestamp
    if not same_timestamp:
        return "different"

    same_ohlc = (
        existing.open == incoming.open
        and existing.high == incoming.high
        and existing.low == incoming.low
        and existing.close == incoming.close
    )
    same_volume = existing.volume == incoming.volume

    if same_ohlc and same_volume:
        return DuplicateType.EXACT

    if not existing.is_closed and incoming.is_closed:
        return DuplicateType.FORMING_UPDATE

    if existing.is_closed and not incoming.is_closed:
        return DuplicateType.FORMING_UPDATE

    if same_ohlc:
        return DuplicateType.FORMING_UPDATE

    return DuplicateType.CONFLICTING


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

def detect_gaps(
    candles: list[NormalizedCandle],
    tolerance_factor: float = 1.5,
) -> list[dict]:
    """
    Detect gaps in a sorted candle sequence.

    A gap exists when the time between consecutive candles exceeds
    the expected interval * tolerance_factor.

    Returns a list of gap descriptors:
        [{"expected": datetime, "actual": datetime, "gap_seconds": float, "severity": str}]
    """
    if len(candles) < 2:
        return []

    sorted_candles = sorted(candles, key=lambda c: c.timestamp)
    expected_interval = sorted_candles[0].timeframe.interval_seconds
    max_gap = expected_interval * tolerance_factor

    gaps = []
    for i in range(1, len(sorted_candles)):
        prev = sorted_candles[i - 1]
        curr = sorted_candles[i]
        diff = (curr.timestamp - prev.timestamp).total_seconds()

        if diff > max_gap:
            severity = "suspected" if diff < max_gap * 3 else "unexpected"
            gaps.append({
                "after_timestamp": prev.timestamp.isoformat(),
                "before_timestamp": curr.timestamp.isoformat(),
                "gap_seconds": diff,
                "expected_seconds": expected_interval,
                "severity": severity,
            })

    return gaps


# ---------------------------------------------------------------------------
# Freshness validation
# ---------------------------------------------------------------------------

def check_freshness(
    latest_timestamp: datetime,
    timeframe: Timeframe,
    tolerance_map: dict[str, int],
) -> tuple[bool, int]:
    """
    Check if data is fresh enough for the given timeframe.

    Returns:
        (is_fresh, age_seconds)
    """
    now = datetime.now(timezone.utc)
    age = (now - latest_timestamp).total_seconds()
    tolerance = tolerance_map.get(timeframe.value, 3600)
    return age <= tolerance, int(age)


# ---------------------------------------------------------------------------
# Candle deduplication
# ---------------------------------------------------------------------------

def deduplicate_candles(candles: list[NormalizedCandle]) -> list[NormalizedCandle]:
    """
    Remove duplicate candles from a list.

    Policy:
        - Exact duplicates: keep first occurrence
        - Conflicting duplicates: keep the one with is_closed=True
        - If both closed, keep the first (earlier received)
    """
    seen: dict[tuple[datetime, Instrument, Timeframe], NormalizedCandle] = {}

    for candle in candles:
        key = (candle.timestamp, candle.instrument, candle.timeframe)

        if key not in seen:
            seen[key] = candle
            continue

        existing = seen[key]
        classification = classify_duplicate(existing, candle)

        if classification == DuplicateType.EXACT:
            continue
        elif classification == DuplicateType.FORMING_UPDATE:
            seen[key] = candle
        elif classification == DuplicateType.CONFLICTING:
            if candle.is_closed and not existing.is_closed:
                seen[key] = candle
            # Otherwise keep existing

    return list(seen.values())
