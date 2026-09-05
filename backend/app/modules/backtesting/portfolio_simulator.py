"""
Scalping Arise — Portfolio Simulator

Multi-position tracking and portfolio-level risk management
during backtesting. Handles position correlation, portfolio-level
drawdown, and concurrent position limits.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.backtesting.account_simulator import AccountSimulator
from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.models import (
    AccountConfig,
    ClosedTrade,
    CloseReason,
    HistoricalCandle,
    OrderSide,
    SimulatedPosition,
)

logger = logging.getLogger(__name__)


class PortfolioSimulator:
    """
    Manages multiple concurrent positions during backtesting.

    Responsibilities:
    - Track all open positions
    - Enforce max position limits
    - Update position prices on each candle
    - Check SL/TP hits across all positions
    - Close positions and record trades
    - Calculate portfolio-level metrics
    """

    def __init__(
        self,
        account: AccountSimulator,
        trade_simulator: Optional[object] = None,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()
        self._account = account
        self._trade_simulator = trade_simulator
        self._open_positions: list[SimulatedPosition] = []
        self._closed_trades: list[ClosedTrade] = []
        self._position_counter = 0

    @property
    def open_positions(self) -> list[SimulatedPosition]:
        return list(self._open_positions)

    @property
    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed_trades)

    @property
    def position_count(self) -> int:
        return len(self._open_positions)

    @property
    def total_trades(self) -> int:
        return len(self._closed_trades)

    def can_open_position(self) -> bool:
        """Check if a new position can be opened."""
        return self._account.can_open_position(self.position_count)

    def open_position(self, position: SimulatedPosition) -> bool:
        """
        Open a new position if limits allow.

        Returns True if position was opened.
        """
        if not self.can_open_position():
            logger.warning(
                "Cannot open position: limit reached (%d/%d)",
                self.position_count,
                self._account._config.max_positions,
            )
            return False

        self._open_positions.append(position)
        self._position_counter += 1
        logger.debug(
            "Position opened: %s %s %.4f @ %.2f",
            position.side.value,
            position.instrument,
            position.lots,
            position.entry_price,
        )
        return True

    def update_prices(self, candle: HistoricalCandle) -> None:
        """Update all open position prices from candle data."""
        for pos in self._open_positions:
            if pos.instrument == candle.instrument:
                pos.update_price(candle.close)

    def check_exits(self, candle: HistoricalCandle) -> list[tuple[SimulatedPosition, CloseReason]]:
        """
        Check all positions for SL/TP hits.

        Returns list of (position, reason) tuples for positions to close.
        """
        exits: list[tuple[SimulatedPosition, CloseReason]] = []

        for pos in self._open_positions:
            if pos.instrument != candle.instrument:
                continue

            if self._trade_simulator is not None:
                reason = self._trade_simulator.check_sl_tp_hit(pos, candle)
                if reason is not None:
                    exits.append((pos, reason))

        return exits

    def close_position(
        self,
        position: SimulatedPosition,
        reason: CloseReason,
        exit_price: float,
        timestamp: datetime,
        exit_lots: Optional[float] = None,
    ) -> ClosedTrade:
        """
        Close a position and record the trade.

        If exit_lots is less than position.lots, partial close is performed.
        """
        close_lots = exit_lots or position.lots
        close_lots = min(close_lots, position.lots)

        # Calculate P&L
        from app.modules.trade_planning.instrument_specs import get_spec
        spec = get_spec(position.instrument)
        contract_size = spec.contract_size if spec else 100.0

        if position.side == OrderSide.BUY:
            gross_pnl = (exit_price - position.entry_price) * close_lots * contract_size
        else:
            gross_pnl = (position.entry_price - exit_price) * close_lots * contract_size

        # Calculate costs
        from app.modules.backtesting.trade_simulator import TradeSimulator
        if self._trade_simulator is not None and isinstance(self._trade_simulator, TradeSimulator):
            pip_value = self._trade_simulator._get_pip_value_per_lot(position.instrument)
            spread_cost = self._trade_simulator._spread_pips * close_lots * pip_value
            slippage_cost = 0.0  # Assume no additional slippage on exit for simplicity
        else:
            spread_cost = 0.0
            slippage_cost = 0.0

        total_costs = spread_cost + slippage_cost
        net_pnl = gross_pnl - total_costs

        # Calculate holding bars
        holding_bars = 0
        if hasattr(self, '_current_bar_index'):
            # This would be set by the runner
            pass

        trade = ClosedTrade(
            instrument=position.instrument,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            lots=close_lots,
            entry_time=position.opened_at,
            exit_time=timestamp,
            close_reason=reason,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            total_costs=total_costs,
            slippage_cost=slippage_cost,
            spread_cost=spread_cost,
            signal_id=position.signal_id,
            strategy_id=position.strategy_id,
            plan_id=position.plan_id,
        )

        self._closed_trades.append(trade)

        # Handle partial close
        if close_lots < position.lots:
            position.lots -= close_lots
            position.status = "partially_closed"
        else:
            # Remove from open positions
            self._open_positions = [
                p for p in self._open_positions
                if p.position_id != position.position_id
            ]

        logger.debug(
            "Position closed: %s %s %.4f @ %.2f → %.2f | P&L: %.2f | Reason: %s",
            position.side.value,
            position.instrument,
            close_lots,
            position.entry_price,
            exit_price,
            net_pnl,
            reason.value,
        )

        return trade

    def close_all_positions(
        self,
        candle: HistoricalCandle,
        reason: CloseReason = CloseReason.MANUAL,
    ) -> list[ClosedTrade]:
        """Close all open positions at candle close price."""
        trades: list[ClosedTrade] = []
        for pos in list(self._open_positions):
            if pos.instrument == candle.instrument:
                trade = self.close_position(
                    pos,
                    reason=reason,
                    exit_price=candle.close,
                    timestamp=candle.timestamp,
                )
                trades.append(trade)
        return trades

    def get_positions_by_instrument(self, instrument: str) -> list[SimulatedPosition]:
        """Get all open positions for a specific instrument."""
        return [p for p in self._open_positions if p.instrument == instrument]

    def get_positions_by_strategy(self, strategy_id: str) -> list[SimulatedPosition]:
        """Get all open positions for a specific strategy."""
        return [p for p in self._open_positions if p.strategy_id == strategy_id]

    def get_total_margin_used(self) -> float:
        """Get total margin used across all open positions."""
        return sum(p.margin_used for p in self._open_positions)

    def get_total_unrealized_pnl(self) -> float:
        """Get total unrealized P&L across all open positions."""
        return sum(p.unrealized_pnl for p in self._open_positions)

    def get_portfolio_heat(self) -> float:
        """
        Calculate portfolio heat (total risk as % of balance).

        High portfolio heat (> 5%) indicates over-leveraging.
        """
        total_margin = self.get_total_margin_used()
        if self._account.balance <= 0:
            return 0.0
        return (total_margin / self._account.balance) * 100.0

    def reset(self) -> None:
        """Reset portfolio state."""
        self._open_positions.clear()
        self._closed_trades.clear()
        self._position_counter = 0

    def summary(self) -> dict:
        """Return portfolio summary."""
        return {
            "open_positions": self.position_count,
            "total_trades": self.total_trades,
            "total_margin_used": round(self.get_total_margin_used(), 2),
            "total_unrealized_pnl": round(self.get_total_unrealized_pnl(), 2),
            "portfolio_heat_pct": round(self.get_portfolio_heat(), 2),
            "winning_trades": sum(1 for t in self._closed_trades if t.is_winner),
            "losing_trades": sum(1 for t in self._closed_trades if not t.is_winner),
            "net_pnl": round(sum(t.net_pnl for t in self._closed_trades), 2),
        }
