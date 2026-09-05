"""
Scalping Arise — Candle Replay Engine

Chronological candle-by-candle iteration engine for backtesting.
Provides deterministic, time-ordered iteration through historical
candle data with look-ahead protection built in.

Each iteration yields a ReplaySlice containing only the data
visible at the current simulation time.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Optional

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.look_ahead_guard import LookAheadGuard
from app.modules.backtesting.models import (
    HistoricalCandle,
    ReplaySlice,
    ReplayState,
)

logger = logging.getLogger(__name__)


class CandleReplayEngine:
    """
    Deterministic, chronological candle-by-candle replay engine.

    Iterates through historical candles in time order, providing
    each downstream component with only the data visible at the
    current simulation time.

    Usage:
        engine = CandleReplayEngine(candles)
        for slice in engine:
            # slice.current_candle is the candle at sim time
            # slice.visible_candles is all candles up to sim time
            # Use slice for strategy evaluation, signal generation, etc.
    """

    def __init__(
        self,
        candles: list[HistoricalCandle],
        look_ahead_guard: Optional[LookAheadGuard] = None,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()
        self._candles = sorted(candles, key=lambda c: c.timestamp)
        self._index = 0
        self._signals_generated = 0
        self._trades_executed = 0
        self._plan_rejections = 0

        # Look-ahead guard
        self._guard = look_ahead_guard or LookAheadGuard(
            simulation_time=self._candles[0].timestamp if self._candles else datetime.now(timezone.utc),
            strict_mode=self._settings.strict_lookahead,
            settings=self._settings,
        )

        # Callbacks
        self._on_candle_callbacks: list[Callable[[ReplaySlice], None]] = []

    @property
    def total_candles(self) -> int:
        return len(self._candles)

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def is_complete(self) -> bool:
        return self._index >= len(self._candles)

    @property
    def progress_pct(self) -> float:
        if not self._candles:
            return 100.0
        return (self._index / len(self._candles)) * 100.0

    @property
    def current_timestamp(self) -> Optional[datetime]:
        if 0 <= self._index < len(self._candles):
            return self._candles[self._index].timestamp
        return None

    @property
    def guard(self) -> LookAheadGuard:
        """Access the look-ahead guard for external validation."""
        return self._guard

    def record_signal(self) -> None:
        """Record that a signal was generated at this candle."""
        self._signals_generated += 1

    def record_trade(self) -> None:
        """Record that a trade was executed at this candle."""
        self._trades_executed += 1

    def record_plan_rejection(self) -> None:
        """Record that a plan was rejected at this candle."""
        self._plan_rejections += 1

    def get_state(self) -> ReplayState:
        """Get current replay state."""
        return ReplayState(
            current_index=self._index,
            total_candles=self._candles[self._index].timestamp if self._index < len(self._candles) else self._candles[-1].timestamp if self._candles else datetime.now(timezone.utc),
            current_timestamp=self.current_timestamp or datetime.now(timezone.utc),
            progress_pct=self.progress_pct,
            is_complete=self.is_complete,
            candles_processed=self._index,
            signals_generated=self._signals_generated,
            trades_executed=self._trades_executed,
            plan_rejections=self._plan_rejections,
        )

    def on_candle(self, callback: Callable[[ReplaySlice], None]) -> None:
        """Register a callback to be called on each candle iteration."""
        self._on_candle_callbacks.append(callback)

    def reset(self) -> None:
        """Reset the replay engine to the beginning."""
        self._index = 0
        self._signals_generated = 0
        self._trades_executed = 0
        self._plan_rejections = 0
        if self._candles:
            self._guard.reset(self._candles[0].timestamp)

    def seek_to(self, timestamp: datetime) -> bool:
        """Seek to a specific timestamp. Returns True if found."""
        for i, c in enumerate(self._candles):
            if c.timestamp >= timestamp:
                self._index = i
                self._guard.advance(c.timestamp)
                return True
        return False

    def get_slice_at(self, index: int) -> Optional[ReplaySlice]:
        """Get a replay slice at a specific index without advancing."""
        if index < 0 or index >= len(self._candles):
            return None
        candle = self._candles[index]
        visible = [c for c in self._candles[:index + 1]]
        return ReplaySlice(
            current_candle=candle,
            visible_candles=visible,
            window_start=visible[0].timestamp if visible else None,
            window_end=candle.timestamp,
            candle_count=len(visible),
        )

    def get_slice_for_candle(self, candle: HistoricalCandle) -> ReplaySlice:
        """Build a replay slice for a specific candle from all available data."""
        visible = [c for c in self._candles if c.timestamp <= candle.timestamp]
        return ReplaySlice(
            current_candle=candle,
            visible_candles=visible,
            window_start=visible[0].timestamp if visible else None,
            window_end=candle.timestamp,
            candle_count=len(visible),
        )

    def __iter__(self):
        return self

    def __next__(self) -> ReplaySlice:
        if self._index >= len(self._candles):
            raise StopIteration

        candle = self._candles[self._index]

        # Advance the guard
        self._guard.advance(candle.timestamp)

        # Build visible window
        visible = self._candles[:self._index + 1]

        # Build slice
        slice_obj = ReplaySlice(
            current_candle=candle,
            visible_candles=visible,
            window_start=visible[0].timestamp if visible else None,
            window_end=candle.timestamp,
            candle_count=len(visible),
        )

        # Fire callbacks
        for cb in self._on_candle_callbacks:
            cb(slice_obj)

        # Advance index
        self._index += 1

        return slice_obj

    def __len__(self) -> int:
        return len(self._candles)

    def __getitem__(self, index: int) -> HistoricalCandle:
        return self._candles[index]

    def summary(self) -> dict:
        """Return a summary of the replay engine state."""
        return {
            "total_candles": self.total_candles,
            "current_index": self._index,
            "progress_pct": round(self.progress_pct, 2),
            "is_complete": self.is_complete,
            "signals_generated": self._signals_generated,
            "trades_executed": self._trades_executed,
            "plan_rejections": self._plan_rejections,
            "start_time": self._candles[0].timestamp.isoformat() if self._candles else None,
            "end_time": self._candles[-1].timestamp.isoformat() if self._candles else None,
            "look_ahead_guard": self._guard.summary(),
        }
