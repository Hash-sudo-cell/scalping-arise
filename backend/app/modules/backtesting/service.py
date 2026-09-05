"""
Scalping Arise — Backtesting Service

FastAPI-facing service layer for the backtesting module.
Orchestrates backtest runs, result storage, and health checks.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.models import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    RobustnessMethod,
    WalkForwardConfig,
)
from app.modules.backtesting.paper_trading import PaperTradingService
from app.modules.backtesting.runner import BacktestRunner
from app.modules.backtesting.versioning import ResultVersionManager

logger = logging.getLogger(__name__)


class BacktestingService:
    """
    Service layer for the backtesting module.

    Provides a clean API for:
    - Running backtests
    - Querying results
    - Managing paper trading sessions
    - Module health checks
    """

    def __init__(
        self,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()
        self._runner = BacktestRunner(settings=self._settings)
        self._version_manager = ResultVersionManager(settings=self._settings)
        self._paper_trading = PaperTradingService(settings=self._settings)

    async def run_backtest(self, config: BacktestConfig) -> BacktestResult:
        """
        Execute a backtest with the given configuration.

        Returns the complete result including metrics, trades, and equity curve.
        """
        if not self._settings.is_enabled:
            result = BacktestResult(config=config)
            result.status = BacktestStatus.FAILED
            result.error_message = "Backtesting engine is disabled"
            return result

        # Create metadata
        metadata = self._version_manager.create_metadata(
            config=config.model_dump(),
            description=f"Backtest: {config.instrument} {config.timeframe}",
            tags=[config.instrument, config.timeframe, config.mode.value],
        )

        # Run the backtest
        result = await self._runner.run(config)

        # Store result
        self._version_manager.store_result(result, metadata)

        return result

    def get_result(self, run_id: str) -> Optional[BacktestResult]:
        """Get a backtest result by run ID."""
        return self._version_manager.get_result(run_id)

    def list_runs(
        self,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> list[dict]:
        """List recent backtest runs."""
        return self._version_manager.list_runs(limit=limit, status=status)

    def compare_runs(
        self,
        run_id_a: str,
        run_id_b: str,
    ) -> Optional[dict]:
        """Compare two backtest runs."""
        return self._version_manager.compare_runs(run_id_a, run_id_b)

    def delete_result(self, run_id: str) -> bool:
        """Delete a stored result."""
        return self._version_manager.delete_result(run_id)

    # ------------------------------------------------------------------
    # Paper Trading
    # ------------------------------------------------------------------

    def start_paper_trading(self, config: Optional[object] = None) -> dict:
        """Start a paper trading session."""
        session = self._paper_trading.start_session(config)
        return {
            "session_id": session.session_id,
            "status": session.status,
            "balance": session.balance,
        }

    def stop_paper_trading(self, session_id: str) -> Optional[dict]:
        """Stop a paper trading session."""
        session = self._paper_trading.stop_session(session_id)
        if session is None:
            return None
        return {
            "session_id": session.session_id,
            "status": session.status,
            "total_trades": len(session.trades),
            "net_pnl": session.net_pnl,
        }

    def list_paper_sessions(self) -> list[dict]:
        """List all paper trading sessions."""
        sessions = self._paper_trading.list_sessions()
        return [
            {
                "session_id": s.session_id,
                "status": s.status,
                "total_trades": len(s.trades),
                "net_pnl": s.net_pnl,
            }
            for s in sessions
        ]

    # ------------------------------------------------------------------
    # Health & Capabilities
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """Check if the backtesting engine is operational."""
        try:
            return {
                "status": "healthy",
                "module": "backtesting",
                "configuration": {
                    "enabled": self._settings.is_enabled,
                    "enforce_determinism": self._settings.enforce_determinism,
                    "strict_lookahead": self._settings.strict_lookahead,
                    "max_trades_per_backtest": self._settings.max_trades_per_backtest,
                },
                "results_stored": self._version_manager.total_stored,
                "paper_sessions": len(self._paper_trading.list_sessions()),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "module": "backtesting",
                "error": str(e),
            }

    async def get_capabilities(self) -> dict:
        """Return backtesting capabilities."""
        return {
            "module": "backtesting",
            "status": "active" if self._settings.is_enabled else "disabled",
            "features": {
                "historical_backtest": True,
                "walk_forward": True,
                "monte_carlo": True,
                "bootstrap": True,
                "paper_trading": True,
                "look_ahead_protection": True,
                "deterministic_results": True,
                "result_versioning": True,
                "result_comparison": True,
            },
            "supported_modes": ["historical", "walk_forward", "paper_trading", "monte_carlo", "stress_test"],
            "supported_fill_methods": ["next_bar_open", "current_close", "current_close_with_slippage", "next_bar_with_slippage"],
            "supported_slippage_models": ["fixed", "percentage", "atr_multiple", "spread_based"],
        }
