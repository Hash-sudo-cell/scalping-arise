"""
Scalping Arise — Market Data Validation Tests
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.market_data.models import (
    Instrument,
    NormalizedCandle,
    SourceType,
    Timeframe,
)
from app.modules.market_data.validation import (
    CandleValidationError,
    check_freshness,
    classify_duplicate,
    deduplicate_candles,
    detect_gaps,
    validate_ohlc,
    validate_candle,
    validate_timestamp,
)


def _candle(
    open: float = 2000.0,
    high: float = 2010.0,
    low: float = 1990.0,
    close: float = 2005.0,
    timestamp: datetime | None = None,
    is_closed: bool = True,
    volume: float | None = 1000.0,
    timeframe: Timeframe = Timeframe.H1,
    provider_instrument: str = "XAU/USD",
    source_type: SourceType = SourceType.SPOT,
) -> NormalizedCandle:
    return NormalizedCandle(
        instrument=Instrument.XAU_USD,
        provider_instrument=provider_instrument,
        source_type=source_type,
        timeframe=timeframe,
        timestamp=timestamp or datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=is_closed,
        source="test",
    )


# ---------------------------------------------------------------------------
# OHLC validation
# ---------------------------------------------------------------------------

class TestOHLCValidation:
    def test_valid_candle(self) -> None:
        validate_ohlc(_candle())  # Should not raise

    def test_high_below_low_rejected(self) -> None:
        with pytest.raises(CandleValidationError, match="High.*Low"):
            validate_ohlc(_candle(high=1980, low=1990))

    def test_high_below_open_rejected(self) -> None:
        with pytest.raises(CandleValidationError, match="High.*Open"):
            validate_ohlc(_candle(open=2010, high=2000))

    def test_high_below_close_rejected(self) -> None:
        with pytest.raises(CandleValidationError, match="High.*Close"):
            validate_ohlc(_candle(close=2020, high=2010))

    def test_low_above_open_rejected(self) -> None:
        with pytest.raises(CandleValidationError, match="Low.*Open"):
            validate_ohlc(_candle(open=1980, low=1990))

    def test_low_above_close_rejected(self) -> None:
        with pytest.raises(CandleValidationError, match="Low.*Close"):
            validate_ohlc(_candle(close=1980, low=1990))


# ---------------------------------------------------------------------------
# Timestamp validation
# ---------------------------------------------------------------------------

class TestTimestampValidation:
    def test_valid_timestamp(self) -> None:
        candle = _candle(timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc))
        validate_timestamp(candle)  # Should not raise

    def test_future_timestamp_rejected(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        candle = _candle(timestamp=future)
        with pytest.raises(CandleValidationError, match="future"):
            validate_timestamp(candle)


# ---------------------------------------------------------------------------
# Full candle validation
# ---------------------------------------------------------------------------

class TestCandleValidation:
    def test_valid_candle(self) -> None:
        warnings = validate_candle(_candle())
        assert isinstance(warnings, list)

    def test_instrument_rejected(self) -> None:
        with pytest.raises(CandleValidationError, match="not in allowed"):
            validate_candle(_candle(), allowed_instruments=[])

    def test_timeframe_rejected(self) -> None:
        with pytest.raises(CandleValidationError, match="not in allowed"):
            validate_candle(_candle(), allowed_timeframes=[Timeframe.D1])


# ---------------------------------------------------------------------------
# Duplicate classification
# ---------------------------------------------------------------------------

class TestDuplicateClassification:
    def test_exact_duplicate(self) -> None:
        c1 = _candle()
        c2 = _candle()
        assert classify_duplicate(c1, c2) == "exact"

    def test_forming_update(self) -> None:
        c1 = _candle(is_closed=False)
        c2 = _candle(close=2010, is_closed=False)
        # Same timestamp, different close on forming candle
        assert classify_duplicate(c1, c2) in ("forming_update", "conflicting")

    def test_different_timestamp(self) -> None:
        c1 = _candle(timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc))
        c2 = _candle(timestamp=datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc))
        assert classify_duplicate(c1, c2) == "different"

    def test_conflicting_closed(self) -> None:
        c1 = _candle(close=2000, is_closed=True)
        c2 = _candle(close=2050, is_closed=True)
        assert classify_duplicate(c1, c2) == "conflicting"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_removes_exact_duplicates(self) -> None:
        c1 = _candle()
        c2 = _candle()  # Exact same
        result = deduplicate_candles([c1, c2])
        assert len(result) == 1

    def test_keeps_different_candles(self) -> None:
        c1 = _candle(timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc))
        c2 = _candle(timestamp=datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc))
        result = deduplicate_candles([c1, c2])
        assert len(result) == 2

    def test_closed_overwrites_forming(self) -> None:
        c1 = _candle(is_closed=False, close=2000)
        c2 = _candle(is_closed=True, close=2050)  # Same timestamp, different close, closed
        result = deduplicate_candles([c1, c2])
        assert len(result) == 1
        assert result[0].is_closed is True


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

class TestGapDetection:
    def test_no_gaps(self) -> None:
        candles = [
            _candle(timestamp=datetime(2024, 1, 15, i, 0, 0, tzinfo=timezone.utc))
            for i in range(5)
        ]
        gaps = detect_gaps(candles)
        assert len(gaps) == 0

    def test_gap_detected(self) -> None:
        candles = [
            _candle(timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)),
            _candle(timestamp=datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)),  # 4h gap for 1h candle
        ]
        gaps = detect_gaps(candles)
        assert len(gaps) > 0
        assert gaps[0]["severity"] in ("suspected", "unexpected")

    def test_empty_list(self) -> None:
        gaps = detect_gaps([])
        assert gaps == []

    def test_single_candle(self) -> None:
        gaps = detect_gaps([_candle()])
        assert gaps == []


# ---------------------------------------------------------------------------
# Freshness validation
# ---------------------------------------------------------------------------

class TestFreshnessValidation:
    def test_fresh_data(self) -> None:
        now = datetime.now(timezone.utc)
        tolerance = {"1h": 7200}
        is_fresh, age = check_freshness(now, Timeframe.H1, tolerance)
        assert is_fresh is True
        assert age < 5

    def test_stale_data(self) -> None:
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        tolerance = {"1h": 7200}
        is_fresh, age = check_freshness(old, Timeframe.H1, tolerance)
        assert is_fresh is False
        assert age > 10000
