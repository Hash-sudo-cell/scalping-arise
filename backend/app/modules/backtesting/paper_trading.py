"""
Scalping Arise — Paper Trading Service

Simulated broker for live-forward testing without real money.
Uses live price feeds but simulates all execution.
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
    OrderSide,
    PaperTradeConfig,
    PaperTradeSession,
    SimulatedPosition,
)

logger = logging.getLogger(__name__)


class PaperTradingService:
    """
    Paper trading service for live-forward testing.

    Uses live market data but simulates all order execution.
    Maintains session state for tracking performance over time.
    """

    def __init__(
        self,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()
        self._sessions: dict[str, PaperTradeSession] = {}

    def start_session(
        self,
        config: Optional[PaperTradeConfig] = None,
    ) -> PaperTradeSession:
        """Start a new paper trading session."""
        cfg = config or PaperTradeConfig()
        account_config = AccountConfig(
            initial_balance=cfg.initial_balance,
            max_positions=cfg.max_positions,
        )

        session = PaperTradeSession(
            config=cfg,
            account_config=account_config,
            balance=cfg.initial_balance,
            equity=cfg.initial_balance,
            total_trades=0,
            win_rate=0.0,
            max_drawdown_pct=0.0,
        )

        self._sessions[session.session_id] = session
        logger.info("Paper trading session started: %s", session.session_id)
        return session

    def get_session(self, session_id: str) -> Optional[PaperTradeSession]:
        """Get a paper trading session by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[PaperTradeSession]:
        """List all paper trading sessions."""
        return list(self._sessions.values())

    def stop_session(self, session_id: str) -> Optional[PaperTradeSession]:
        """Stop a paper trading session."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session.status = "stopped"
        logger.info("Paper trading session stopped: %s", session_id)
        return session

    def record_trade(
        self,
        session_id: str,
        trade: ClosedTrade,
    ) -> Optional[PaperTradeSession]:
        """Record a completed trade in a paper trading session."""
        session = self._sessions.get(session_id)
        if session is None:
            return None

        session.trades.append(trade)
        session.balance += trade.net_pnl
        session.equity = session.balance
        session.total_trades += len(session.trades)
        session.net_pnl = session.balance - session.config.initial_balance
        session.last_update = datetime.now(timezone.utc)

        # Update win rate
        winners = sum(1 for t in session.trades if t.is_winner)
        session.win_rate = winners / len(session.trades) if session.trades else 0.0

        return session

    def get_performance_summary(self, session_id: str) -> Optional[dict]:
        """Get a performance summary for a paper trading session."""
        session = self._sessions.get(session_id)
        if session is None:
            return None

        from app.modules.backtesting.performance_analytics import PerformanceAnalytics
        from app.modules.backtesting.models import EquityCurve

        equity_curve = EquityCurve()
        # Build minimal equity curve from trades
        balance = session.config.initial_balance
        for t in session.trades:
            balance += t.net_pnl

        analytics = PerformanceAnalytics(
            trades=session.trades,
            equity_curve=equity_curve,
            initial_balance=session.config.initial_balance,
            final_balance=session.balance,
        )
        metrics = analytics.compute_all()

        return {
            "session_id": session_id,
            "status": session.status,
            "total_trades": len(session.trades),
            "win_rate": session.win_rate,
            "net_pnl": session.net_pnl,
            "balance": session.balance,
            "metrics": metrics.model_dump(),
        }

    def clear_session(self, session_id: str) -> bool:
        """Clear a session's trade history."""
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.trades.clear()
        session.open_positions.clear()
        session.balance = session.config.initial_balance
        session.equity = session.config.initial_balance
        session.total_trades = 0
        session.win_rate = 0.0
        session.net_pnl = 0.0
        return True

    def summary(self) -> dict:
        """Return summary of all paper trading sessions."""
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": sum(
                1 for s in self._sessions.values() if s.status == "active"
            ),
            "sessions": [
                {
                    "session_id": s.session_id,
                    "status": s.status,
                    "total_trades": len(s.trades),
                    "net_pnl": s.net_pnl,
                }
                for s in self._sessions.values()
            ],
        }
