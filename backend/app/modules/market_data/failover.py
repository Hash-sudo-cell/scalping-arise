"""
Scalping Arise — Provider Health & Failover Logic

Manages provider selection, health monitoring, bounded retries,
and fallback consistency validation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.modules.market_data.config import MarketDataSettings
from app.modules.market_data.models import (
    Instrument,
    NormalizedCandle,
    ProviderHealth,
    ProviderHealthStatus,
    SourceType,
    Timeframe,
)

logger = logging.getLogger(__name__)


class FailoverManager:
    """
    Manages primary/fallback provider selection with health-based
    failover and bounded retries.
    """

    def __init__(self, settings: MarketDataSettings) -> None:
        self._settings = settings
        self._primary_health: Optional[ProviderHealth] = None
        self._fallback_health: Optional[ProviderHealth] = None
        self._consecutive_primary_failures: int = 0
        self._max_consecutive_before_fallback: int = 3

    @property
    def primary_health(self) -> Optional[ProviderHealth]:
        return self._primary_health

    @property
    def fallback_health(self) -> Optional[ProviderHealth]:
        return self._fallback_health

    def _is_primary_healthy(self) -> bool:
        """Determine if primary should be used based on recent health."""
        if self._primary_health is None:
            return True  # Unknown = try primary
        return self._primary_health.status == ProviderHealthStatus.HEALTHY

    def update_primary_health(self, health: ProviderHealth) -> None:
        """Update primary provider health and track failure count."""
        self._primary_health = health
        if health.status == ProviderHealthStatus.UNAVAILABLE:
            self._consecutive_primary_failures += 1
            logger.warning(
                "Primary provider failure #%d: %s",
                self._consecutive_primary_failures,
                health.message,
            )
        elif health.status == ProviderHealthStatus.HEALTHY:
            if self._consecutive_primary_failures > 0:
                logger.info("Primary provider recovered after %d failures", self._consecutive_primary_failures)
            self._consecutive_primary_failures = 0

    def update_fallback_health(self, health: ProviderHealth) -> None:
        """Update fallback provider health."""
        self._fallback_health = health
        if health.status == ProviderHealthStatus.HEALTHY:
            logger.info("Fallback provider is healthy")
        elif health.status == ProviderHealthStatus.UNAVAILABLE:
            logger.warning("Fallback provider unavailable: %s", health.message)

    def should_use_fallback(self) -> bool:
        """Determine if fallback should be used instead of primary."""
        if self._consecutive_primary_failures >= self._max_consecutive_before_fallback:
            return True
        if self._primary_health and self._primary_health.status == ProviderHealthStatus.UNAVAILABLE:
            return True
        return False

    def validate_fallback_consistency(
        self,
        primary_candles: list[NormalizedCandle],
        fallback_candles: list[NormalizedCandle],
        tolerance_pct: float = 0.5,
    ) -> tuple[bool, str]:
        """
        Validate consistency between primary and fallback data.

        Compares the most recent closed candle from each source.
        Returns (is_consistent, message).

        When source types differ (e.g. SPOT vs FUTURES_PROXY), price
        divergence is expected and only timestamp proximity is validated.
        """
        if not primary_candles or not fallback_candles:
            return False, "Cannot validate: one or both sources returned no data"

        # Find the most recent closed candle from each source
        primary_closed = [c for c in primary_candles if c.is_closed]
        fallback_closed = [c for c in fallback_candles if c.is_closed]

        if not primary_closed or not fallback_closed:
            return False, "Cannot validate: no closed candles in one or both sources"

        p_latest = max(primary_closed, key=lambda c: c.timestamp)
        f_latest = max(fallback_closed, key=lambda c: c.timestamp)

        # Check timestamp proximity (within 2x expected interval)
        expected_secs = p_latest.timeframe.interval_seconds
        time_diff = abs((p_latest.timestamp - f_latest.timestamp).total_seconds())
        if time_diff > expected_secs * 2:
            return False, (
                f"Timestamp mismatch: {time_diff:.0f}s apart "
                f"(expected <{expected_secs * 2}s)"
            )

        # If source types differ (e.g. SPOT vs FUTURES_PROXY), skip price
        # comparison — basis and contract differences make direct price
        # equivalence invalid. Timestamp proximity is sufficient.
        if p_latest.source_type != f_latest.source_type:
            return True, (
                f"Timestamps consistent, but source types differ "
                f"({p_latest.source_type.value} vs {f_latest.source_type.value}) "
                f"— price comparison skipped"
            )

        # Same source type: check price difference
        avg_price = (p_latest.close + f_latest.close) / 2
        if avg_price == 0:
            return False, "Cannot validate: zero price"

        price_diff_pct = abs(p_latest.close - f_latest.close) / avg_price * 100
        if price_diff_pct > tolerance_pct:
            return False, (
                f"Price divergence: {price_diff_pct:.3f}% "
                f"(tolerance: {tolerance_pct}%)"
            )

        return True, f"Consistent within {price_diff_pct:.4f}%"


async def bounded_retry(
    func,
    max_retries: int = 2,
    delay: float = 1.0,
) -> tuple[Optional[object], Optional[Exception]]:
    """
    Execute a function with bounded retries and exponential backoff.

    Returns (result, last_error).
    """
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            result = await func()
            return result, None
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = delay * (2 ** attempt)
                logger.debug("Retry %d/%d after %.1fs: %s", attempt + 1, max_retries, wait, e)
                await asyncio.sleep(wait)

    return None, last_error
