"""
Scalping Arise — Look-Ahead Bias Guard

Enforces strict time-gated data access during backtesting.
Ensures no strategy, feature calculation, or signal evaluation
can access data that would not have been available at the
simulation time.

This is the primary defense against look-ahead bias.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.models import (
    HistoricalCandle,
    LookAheadViolation,
    TimeGate,
)

logger = logging.getLogger(__name__)


class LookAheadGuard:
    """
    Time-gated data access guard.

    Wraps data access to ensure no future data is leaked
    into strategy evaluation, feature calculation, or signal generation.

    Usage:
        guard = LookAheadGuard(simulation_time=current_candle.timestamp)
        guard.check_access(candle.timestamp)  # raises if violation
        visible = guard.filter_candles(all_candles)  # returns only past candles
    """

    def __init__(
        self,
        simulation_time: datetime,
        max_lookahead_seconds: int = 0,
        strict_mode: bool = True,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()
        self._strict_mode = strict_mode if settings is None else settings.strict_lookahead
        self._max_lookahead = max_lookahead_seconds if max_lookahead_seconds > 0 else self._settings.max_lookahead_seconds

        self._gate = TimeGate(
            simulation_time=simulation_time,
            max_lookahead_seconds=self._max_lookahead,
            strict_mode=self._strict_mode,
        )
        self._violations: list[LookAheadViolation] = []

    @property
    def simulation_time(self) -> datetime:
        """Current simulation time."""
        return self._gate.simulation_time

    @property
    def violations(self) -> list[LookAheadViolation]:
        """Recorded violations."""
        return list(self._violations)

    @property
    def violation_count(self) -> int:
        return len(self._violations)

    def advance(self, new_time: datetime) -> None:
        """
        Advance the simulation time gate.

        Call this when the replay engine moves to the next candle.
        """
        self._gate.simulation_time = new_time

    def check_access(self, data_timestamp: datetime, component: str = "unknown") -> bool:
        """
        Check if accessing data at given timestamp is allowed.

        Returns True if access is OK.
        Returns False and records violation if access is denied.
        """
        violation_msg = self._gate.gate_violation(data_timestamp)
        if violation_msg is None:
            return True

        # Record violation
        overshoot = (data_timestamp - self._gate.simulation_time).total_seconds()
        violation = LookAheadViolation(
            simulation_time=self._gate.simulation_time,
            data_timestamp=data_timestamp,
            overshoot_seconds=overshoot,
            component=component,
            detail=violation_msg,
            severity="critical" if self._strict_mode else "warning",
        )
        self._violations.append(violation)

        if self._strict_mode:
            logger.error("LOOK-AHEAD VIOLATION: %s", violation_msg)
            return False
        else:
            logger.warning("Look-ahead warning: %s", violation_msg)
            return True

    def filter_candles(
        self,
        candles: list[HistoricalCandle],
        component: str = "unknown",
    ) -> list[HistoricalCandle]:
        """
        Filter candles to only those accessible at current simulation time.

        Returns candles with timestamp <= simulation_time + max_lookahead.
        Logs any violations encountered.
        """
        result: list[HistoricalCandle] = []
        for c in candles:
            if self._gate.is_accessible(c.timestamp):
                result.append(c)
            else:
                self.check_access(c.timestamp, component)
        return result

    def get_visible_window(
        self,
        candles: list[HistoricalCandle],
        max_count: Optional[int] = None,
        component: str = "unknown",
    ) -> list[HistoricalCandle]:
        """
        Get the visible candle window up to current simulation time.

        Returns sorted candles (oldest first) with timestamp <= simulation_time.
        Optionally limited to max_count most recent candles.
        """
        visible = self.filter_candles(candles, component)
        if max_count is not None and len(visible) > max_count:
            visible = visible[-max_count:]
        return visible

    def get_current_price(
        self,
        candles: list[HistoricalCandle],
        component: str = "unknown",
    ) -> Optional[float]:
        """
        Get the most recent close price at or before simulation time.

        Returns None if no accessible candle exists.
        """
        visible = self.filter_candles(candles, component)
        if not visible:
            return None
        return visible[-1].close

    def get_current_candle(
        self,
        candles: list[HistoricalCandle],
        component: str = "unknown",
    ) -> Optional[HistoricalCandle]:
        """
        Get the candle at or closest before simulation time.

        Returns None if no accessible candle exists.
        """
        visible = self.filter_candles(candles, component)
        if not visible:
            return None
        return visible[-1]

    def validate_no_future_data(
        self,
        data_timestamps: list[datetime],
        component: str = "unknown",
    ) -> bool:
        """
        Validate that none of the provided timestamps are in the future.

        Returns True if all timestamps are valid.
        """
        all_valid = True
        for ts in data_timestamps:
            if not self.check_access(ts, component):
                all_valid = False
        return all_valid

    def reset(self, new_simulation_time: Optional[datetime] = None) -> None:
        """Reset the guard with a new simulation time and clear violations."""
        if new_simulation_time is not None:
            self._gate.simulation_time = new_simulation_time
        self._violations.clear()

    def summary(self) -> dict:
        """Return a summary of guard state."""
        return {
            "simulation_time": self._gate.simulation_time.isoformat(),
            "max_lookahead_seconds": self._max_lookahead,
            "strict_mode": self._strict_mode,
            "total_violations": len(self._violations),
            "critical_violations": sum(
                1 for v in self._violations if v.severity == "critical"
            ),
            "components_with_violations": list({
                v.component for v in self._violations
            }),
        }
