"""
Scalping Arise — Historical Data Provider

Wraps the MarketDataService to load and validate historical candle data
for backtesting. Supports in-memory loading, data quality checks,
and time-range filtering.

This module does NOT duplicate Phase 2 logic — it wraps it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.models import (
    DataGranularity,
    DataQualityReport,
    DataSource,
    HistoricalCandle,
)
from app.modules.market_data.models import Instrument, Timeframe
from app.modules.market_data.service import MarketDataService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timeframe → seconds mapping for gap detection
# ---------------------------------------------------------------------------

_TF_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


class HistoricalDataProvider:
    """
    Loads and validates historical candle data for backtesting.

    Wraps MarketDataService.get_candles() to provide:
    - Time-range filtering
    - Data quality assessment
    - Gap detection
    - Deduplication
    - OHLCV validation
    """

    def __init__(
        self,
        market_data_service: Optional[MarketDataService] = None,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._market_data = market_data_service or MarketDataService()
        self._settings = settings or get_backtesting_settings()

    async def load_candles(
        self,
        instrument: str,
        timeframe: str,
        limit: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> tuple[list[HistoricalCandle], DataSource]:
        """
        Load historical candles from the market data service.

        Returns sorted, deduplicated candles with metadata.
        """
        inst = Instrument(instrument)
        tf = Timeframe(timeframe)

        raw_candles = await self._market_data.get_candles(
            instrument=inst,
            timeframe=tf,
            limit=limit,
        )

        # Convert to HistoricalCandle
        candles: list[HistoricalCandle] = []
        for c in raw_candles:
            hc = HistoricalCandle(
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
                instrument=instrument,
                timeframe=timeframe,
            )
            candles.append(hc)

        # Sort by timestamp
        candles.sort(key=lambda x: x.timestamp)

        # Deduplicate (keep last occurrence)
        candles = self._deduplicate(candles)

        # Time-range filter
        if start_time is not None:
            candles = [c for c in candles if c.timestamp >= start_time]
        if end_time is not None:
            candles = [c for c in candles if c.timestamp <= end_time]

        # Build data source metadata
        source = DataSource(
            provider="market_data_service",
            source_type="api",
            instrument=instrument,
            timeframe=timeframe,
            start_time=candles[0].timestamp if candles else datetime.now(timezone.utc),
            end_time=candles[-1].timestamp if candles else datetime.now(timezone.utc),
            candle_count=len(candles),
            has_volume=any(c.volume > 0 for c in candles),
            has_gaps=self._detect_gaps(candles, timeframe),
            gap_count=self._count_gaps(candles, timeframe),
        )

        logger.info(
            "Loaded %d candles for %s %s (range: %s to %s)",
            len(candles),
            instrument,
            timeframe,
            source.start_time.isoformat(),
            source.end_time.isoformat(),
        )

        return candles, source

    def validate_data_quality(
        self,
        candles: list[HistoricalCandle],
        timeframe: str,
    ) -> DataQualityReport:
        """Assess the quality of loaded candle data."""
        total = len(candles)
        valid = 0
        invalid = 0
        missing_volume = 0
        price_anomalies = 0
        volume_anomalies = 0
        warnings: list[str] = []

        for c in candles:
            is_valid = True

            # OHLCV validation
            if c.high < c.low:
                invalid += 1
                price_anomalies += 1
                continue
            if c.open <= 0 or c.close <= 0 or c.high <= 0 or c.low <= 0:
                invalid += 1
                price_anomalies += 1
                continue

            # Volume check
            if c.volume <= 0:
                missing_volume += 1

            # Extreme price movement (> 50% in one candle)
            if c.open > 0:
                pct_change = abs(c.close - c.open) / c.open
                if pct_change > 0.50:
                    price_anomalies += 1
                    warnings.append(
                        f"Extreme price movement at {c.timestamp.isoformat()}: "
                        f"{pct_change:.1%} change"
                    )

            valid += 1

        # Gap detection
        gaps = self._find_time_gaps(candles, timeframe)
        duplicate_count = total - len(self._deduplicate(candles))

        # Quality score
        if total == 0:
            score = 0.0
        else:
            issues = invalid + price_anomalies + volume_anomalies + len(gaps) + duplicate_count
            score = max(0.0, 1.0 - (issues / total))

        return DataQualityReport(
            total_candles=total,
            valid_candles=valid,
            invalid_candles=invalid,
            missing_volume_candles=missing_volume,
            gap_count=len(gaps),
            duplicate_count=duplicate_count,
            price_anomalies=price_anomalies,
            volume_anomalies=volume_anomalies,
            time_gaps=gaps,
            quality_score=score,
            warnings=warnings,
        )

    def create_candle_store(
        self,
        candles: list[HistoricalCandle],
    ) -> dict[datetime, HistoricalCandle]:
        """Create a timestamp-indexed lookup for O(1) candle access."""
        return {c.timestamp: c for c in candles}

    def get_candles_in_window(
        self,
        candles: list[HistoricalCandle],
        end_time: datetime,
        max_count: Optional[int] = None,
    ) -> list[HistoricalCandle]:
        """
        Get candles visible up to end_time (look-ahead safe).

        Returns candles with timestamp <= end_time, most recent first.
        """
        visible = [c for c in candles if c.timestamp <= end_time]
        if max_count is not None:
            visible = visible[-max_count:]
        return visible

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(candles: list[HistoricalCandle]) -> list[HistoricalCandle]:
        """Remove duplicate candles (same timestamp), keeping last occurrence."""
        seen: dict[datetime, int] = {}
        result: list[HistoricalCandle] = []
        for i, c in enumerate(candles):
            seen[c.timestamp] = i
        for i, c in enumerate(candles):
            if seen[c.timestamp] == i:
                result.append(c)
        return result

    @staticmethod
    def _detect_gaps(candles: list[HistoricalCandle], timeframe: str) -> bool:
        """Check if there are time gaps in the candle series."""
        expected_interval = _TF_SECONDS.get(timeframe, 3600)
        # Allow 50% tolerance for weekends/holidays
        tolerance = expected_interval * 1.5
        for i in range(1, len(candles)):
            delta = (candles[i].timestamp - candles[i - 1].timestamp).total_seconds()
            if delta > tolerance:
                return True
        return False

    @staticmethod
    def _count_gaps(candles: list[HistoricalCandle], timeframe: str) -> int:
        """Count the number of time gaps exceeding expected interval."""
        expected_interval = _TF_SECONDS.get(timeframe, 3600)
        tolerance = expected_interval * 1.5
        gap_count = 0
        for i in range(1, len(candles)):
            delta = (candles[i].timestamp - candles[i - 1].timestamp).total_seconds()
            if delta > tolerance:
                gap_count += 1
        return gap_count

    @staticmethod
    def _find_time_gaps(
        candles: list[HistoricalCandle],
        timeframe: str,
    ) -> list[datetime]:
        """Find timestamps where gaps occur."""
        expected_interval = _TF_SECONDS.get(timeframe, 3600)
        tolerance = expected_interval * 1.5
        gaps: list[datetime] = []
        for i in range(1, len(candles)):
            delta = (candles[i].timestamp - candles[i - 1].timestamp).total_seconds()
            if delta > tolerance:
                gaps.append(candles[i - 1].timestamp)
        return gaps
