"""
Scalping Arise — Account Simulator

Simulates account state changes during backtesting:
balance, equity curve, margin, drawdown, daily P&L tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.models import (
    AccountConfig,
    AccountSnapshot,
    ClosedTrade,
    CloseReason,
    EquityCurve,
    OrderSide,
    SimulatedPosition,
)

logger = logging.getLogger(__name__)


class AccountSimulator:
    """
    Simulates account state throughout a backtest.

    Tracks:
    - Balance (realized P&L only)
    - Equity (balance + unrealized P&L)
    - Margin usage
    - Drawdown from peak
    - Daily P&L
    - Risk limit enforcement
    """

    def __init__(
        self,
        config: Optional[AccountConfig] = None,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()
        self._config = config or AccountConfig(
            initial_balance=self._settings.default_initial_balance,
            max_positions=self._settings.default_max_positions,
            max_daily_loss_pct=self._settings.default_max_daily_loss_pct,
            max_drawdown_pct=self._settings.default_max_drawdown_pct,
        )

        # State
        self._balance = self._config.initial_balance
        self._peak_balance = self._config.initial_balance
        self._daily_pnl = 0.0
        self._daily_reset_hour = 0  # UTC
        self._last_daily_reset_date: Optional[datetime] = None

        # Equity curve
        self._equity_curve = EquityCurve()

        # Snapshots
        self._snapshots: list[AccountSnapshot] = []

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def equity(self) -> float:
        return self._balance

    @property
    def peak_balance(self) -> float:
        return self._peak_balance

    @property
    def equity_curve(self) -> EquityCurve:
        return self._equity_curve

    @property
    def snapshots(self) -> list[AccountSnapshot]:
        return list(self._snapshots)

    @property
    def current_drawdown_pct(self) -> float:
        """Current drawdown as percentage from peak."""
        if self._peak_balance <= 0:
            return 0.0
        return max(0.0, (self._peak_balance - self._balance) / self._peak_balance * 100.0)

    @property
    def current_drawdown_amount(self) -> float:
        """Current drawdown amount from peak."""
        return max(0.0, self._peak_balance - self._balance)

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def daily_pnl_pct(self) -> float:
        if self._config.initial_balance <= 0:
            return 0.0
        return self._daily_pnl / self._config.initial_balance * 100.0

    def can_open_position(self, open_positions: int) -> bool:
        """Check if a new position can be opened within risk limits."""
        if open_positions >= self._config.max_positions:
            return False
        if self.current_drawdown_pct >= self._config.max_drawdown_pct:
            return False
        if abs(self.daily_pnl_pct) >= self._config.max_daily_loss_pct and self.daily_pnl < 0:
            return False
        return True

    def calculate_max_position_size(
        self,
        risk_per_trade_pct: float,
        open_positions: int,
    ) -> float:
        """Calculate maximum allowed position size based on risk limits."""
        max_risk = self._balance * (risk_per_trade_pct / 100.0)

        # Reduce available risk based on daily loss
        daily_remaining = self._config.max_daily_loss_pct - abs(self.daily_pnl_pct)
        if daily_remaining <= 0:
            return 0.0

        daily_risk_limit = self._balance * (daily_remaining / 100.0)
        max_risk = min(max_risk, daily_risk_limit)

        # Reduce based on drawdown
        drawdown_remaining = self._config.max_drawdown_pct - self.current_drawdown_pct
        if drawdown_remaining <= 0:
            return 0.0

        drawdown_risk_limit = self._balance * (drawdown_remaining / 100.0)
        max_risk = min(max_risk, drawdown_risk_limit)

        return max(0.0, max_risk)

    def process_close(
        self,
        trade: ClosedTrade,
        timestamp: datetime,
        open_positions: list[SimulatedPosition],
    ) -> AccountSnapshot:
        """
        Process a closed trade and update account state.

        Returns the updated account snapshot.
        """
        # Update balance
        self._balance += trade.net_pnl
        self._daily_pnl += trade.net_pnl

        # Update peak
        if self._balance > self._peak_balance:
            self._peak_balance = self._balance

        # Take snapshot
        snapshot = self._take_snapshot(timestamp, open_positions)
        return snapshot

    def take_snapshot(
        self,
        timestamp: datetime,
        open_positions: list[SimulatedPosition],
    ) -> AccountSnapshot:
        """Take a snapshot of the current account state."""
        return self._take_snapshot(timestamp, open_positions)

    def check_daily_reset(self, timestamp: datetime) -> bool:
        """Check if daily P&L should be reset. Returns True if reset occurred."""
        current_date = timestamp.date()
        if self._last_daily_reset_date is None:
            self._last_daily_reset_date = current_date
            return False

        if current_date != self._last_daily_reset_date:
            self._daily_pnl = 0.0
            self._last_daily_reset_date = current_date
            logger.debug("Daily P&L reset at %s", timestamp.isoformat())
            return True
        return False

    def reset(self) -> None:
        """Reset account to initial state."""
        self._balance = self._config.initial_balance
        self._peak_balance = self._config.initial_balance
        self._daily_pnl = 0.0
        self._last_daily_reset_date = None
        self._equity_curve = EquityCurve()
        self._snapshots.clear()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _take_snapshot(
        self,
        timestamp: datetime,
        open_positions: list[SimulatedPosition],
    ) -> AccountSnapshot:
        """Create and record an account snapshot."""
        unrealized_pnl = sum(p.unrealized_pnl for p in open_positions)
        margin_used = sum(p.margin_used for p in open_positions)
        equity = self._balance + unrealized_pnl

        snapshot = AccountSnapshot(
            timestamp=timestamp,
            balance=self._balance,
            equity=equity,
            margin_used=margin_used,
            margin_free=max(0.0, equity - margin_used),
            unrealized_pnl=unrealized_pnl,
            realized_pnl=self._balance - self._config.initial_balance,
            open_positions=len(open_positions),
            drawdown_pct=self.current_drawdown_pct,
            drawdown_amount=self.current_drawdown_amount,
            peak_balance=self._peak_balance,
            daily_pnl=self._daily_pnl,
            daily_pnl_pct=self.daily_pnl_pct,
        )

        self._snapshots.append(snapshot)
        self._equity_curve.append(snapshot)

        return snapshot

    def summary(self) -> dict:
        """Return summary of account state."""
        return {
            "initial_balance": self._config.initial_balance,
            "current_balance": self._balance,
            "peak_balance": self._peak_balance,
            "unrealized_pnl": self._snapshots[-1].unrealized_pnl if self._snapshots else 0.0,
            "realized_pnl": self._balance - self._config.initial_balance,
            "drawdown_pct": round(self.current_drawdown_pct, 2),
            "drawdown_amount": round(self.current_drawdown_amount, 2),
            "daily_pnl": self._daily_pnl,
            "snapshots_count": len(self._snapshots),
            "equity_curve_length": self._equity_curve.length,
        }
