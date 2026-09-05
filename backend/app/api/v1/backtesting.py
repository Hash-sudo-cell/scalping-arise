"""
Scalping Arise — Backtesting API Endpoints

Phase 9 API for backtest execution, result querying,
paper trading, and health checks.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.modules.backtesting.config import get_backtesting_settings
from app.modules.backtesting.models import (
    AccountConfig,
    BacktestConfig,
    BacktestMode,
    FillMethod,
    MonteCarloConfig,
    SlippageModel,
    WalkForwardConfig,
    WalkForwardMethod,
)
from app.modules.backtesting.service import BacktestingService

router = APIRouter(prefix="/backtesting", tags=["backtesting"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    """Request to run a backtest."""

    instrument: str = Field(default="XAU/USD", description="Instrument to backtest")
    timeframe: str = Field(default="1h", description="Primary timeframe")
    candle_limit: int = Field(default=1000, ge=100, le=10000, description="Number of candles to load")
    mode: str = Field(default="historical", description="Backtest mode: historical, walk_forward, monte_carlo")

    # Account
    initial_balance: float = Field(default=10000.0, gt=0)
    max_positions: int = Field(default=3, ge=1, le=50)
    risk_per_trade_pct: float = Field(default=1.0, gt=0, le=100)

    # Simulation
    fill_method: str = Field(default="next_bar_open")
    slippage_pips: float = Field(default=1.0, ge=0)
    spread_pips: float = Field(default=3.0, ge=0)

    # Strategies
    strategy_ids: list[str] | None = Field(default=None, description="Strategies to test (None = all)")
    timeframes: list[str] = Field(default_factory=lambda: ["1m", "5m", "15m"])

    # Walk-forward
    train_window: int | None = Field(default=None, ge=100)
    test_window: int | None = Field(default=None, ge=10)
    step_size: int | None = Field(default=None, ge=10)

    # Robustness
    monte_carlo_simulations: int | None = Field(default=None, ge=100, le=10000)

    # Determinism
    random_seed: int | None = Field(default=None, description="Seed for reproducibility")

    # Limits
    max_trades: int | None = Field(default=None, ge=1)


class RunSummary(BaseModel):
    """Compact backtest run summary."""

    run_id: str
    status: str
    instrument: str
    timeframe: str
    mode: str
    candles_loaded: int
    trades_count: int
    net_profit: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown_pct: float | None = None
    created_at: str | None = None
    duration_seconds: float | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run", summary="Run a backtest")
async def run_backtest(request: BacktestRequest) -> dict:
    """
    Execute a backtest with the given configuration.

    Returns the complete result including metrics, trades, and equity curve.
    """
    settings = get_backtesting_settings()
    if not settings.is_enabled:
        raise HTTPException(status_code=503, detail="Backtesting engine is disabled")

    # Build config
    fill_method_map = {
        "next_bar_open": FillMethod.NEXT_BAR_OPEN,
        "current_close": FillMethod.CURRENT_CLOSE,
        "current_close_with_slippage": FillMethod.CURRENT_CLOSE_WITH_SLIPPAGE,
        "next_bar_with_slippage": FillMethod.NEXT_BAR_WITH_SLIPPAGE,
    }

    mode_map = {
        "historical": BacktestMode.HISTORICAL,
        "walk_forward": BacktestMode.WALK_FORWARD,
        "monte_carlo": BacktestMode.MONTE_CARLO,
        "paper_trading": BacktestMode.PAPER_TRADING,
        "stress_test": BacktestMode.STRESS_TEST,
    }

    config = BacktestConfig(
        mode=mode_map.get(request.mode, BacktestMode.HISTORICAL),
        instrument=request.instrument,
        timeframe=request.timeframe,
        candle_limit=request.candle_limit,
        fill_method=fill_method_map.get(request.fill_method, FillMethod.NEXT_BAR_OPEN),
        slippage_pips=request.slippage_pips,
        spread_pips=request.spread_pips,
        account=AccountConfig(
            initial_balance=request.initial_balance,
            max_positions=request.max_positions,
        ),
        strategy_ids=request.strategy_ids,
        timeframes=request.timeframes,
        random_seed=request.random_seed,
        max_trades=request.max_trades,
    )

    # Walk-forward config
    if request.mode == "walk_forward" and request.train_window and request.test_window:
        config.walk_forward = WalkForwardConfig(
            train_window_candles=request.train_window,
            test_window_candles=request.test_window,
            step_size_candles=request.step_size or request.test_window,
        )

    # Monte Carlo config
    if request.mode == "monte_carlo" and request.monte_carlo_simulations:
        config.monte_carlo_config = MonteCarloConfig(
            num_simulations=request.monte_carlo_simulations,
        )

    # Run backtest
    service = BacktestingService()
    result = await service.run_backtest(config)

    return _result_to_dict(result)


@router.get("/runs", summary="List backtest runs")
async def list_runs(
    limit: int = Query(default=50, ge=1, le=100),
    status: str | None = Query(default=None, description="Filter by status"),
) -> list[dict]:
    """List recent backtest runs."""
    service = BacktestingService()
    return service.list_runs(limit=limit, status=status)


@router.get("/runs/{run_id}", summary="Get backtest run details")
async def get_run(run_id: str) -> dict:
    """Get detailed results for a specific backtest run."""
    service = BacktestingService()
    result = service.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _result_to_dict(result)


@router.get("/runs/{run_id}/trades", summary="Get trades from a run")
async def get_trades(run_id: str) -> list[dict]:
    """Get all trades from a specific backtest run."""
    service = BacktestingService()
    result = service.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return [_trade_to_dict(t) for t in result.trades]


@router.get("/runs/{run_id}/analytics", summary="Get performance analytics")
async def get_analytics(run_id: str) -> dict:
    """Get performance analytics for a specific backtest run."""
    service = BacktestingService()
    result = service.get_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if result.metrics is None:
        raise HTTPException(status_code=404, detail="No metrics available")
    return result.metrics.model_dump()


@router.delete("/runs/{run_id}", summary="Delete a backtest run")
async def delete_run(run_id: str) -> dict:
    """Delete a stored backtest run."""
    service = BacktestingService()
    deleted = service.delete_result(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"status": "deleted", "run_id": run_id}


@router.post("/compare", summary="Compare two backtest runs")
async def compare_runs(run_id_a: str, run_id_b: str) -> dict:
    """Compare two backtest runs side by side."""
    service = BacktestingService()
    comparison = service.compare_runs(run_id_a, run_id_b)
    if comparison is None:
        raise HTTPException(status_code=404, detail="One or both runs not found")
    return comparison


@router.post("/paper-trading/start", summary="Start paper trading")
async def start_paper_trading() -> dict:
    """Start a new paper trading session."""
    service = BacktestingService()
    return service.start_paper_trading()


@router.post("/paper-trading/{session_id}/stop", summary="Stop paper trading")
async def stop_paper_trading(session_id: str) -> dict:
    """Stop a paper trading session."""
    service = BacktestingService()
    result = service.stop_paper_trading(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return result


@router.get("/paper-trading/sessions", summary="List paper trading sessions")
async def list_paper_sessions() -> list[dict]:
    """List all paper trading sessions."""
    service = BacktestingService()
    return service.list_paper_sessions()


@router.get("/health", summary="Backtesting health check")
async def health_check() -> dict:
    """Check if the backtesting engine is operational."""
    service = BacktestingService()
    return await service.health_check()


@router.get("/capabilities", summary="Backtesting capabilities")
async def capabilities() -> dict:
    """Return backtesting engine capabilities."""
    service = BacktestingService()
    return await service.get_capabilities()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _result_to_dict(result: "BacktestResult") -> dict:
    """Convert a BacktestResult to a JSON-serializable dict."""
    return {
        "run_id": result.run_id,
        "status": result.status.value,
        "config": {
            "instrument": result.config.instrument,
            "timeframe": result.config.timeframe,
            "mode": result.config.mode.value,
            "candle_limit": result.config.candle_limit,
            "fill_method": result.config.fill_method.value,
            "slippage_pips": result.config.slippage_pips,
            "spread_pips": result.config.spread_pips,
            "initial_balance": result.config.account.initial_balance,
        },
        "candles_loaded": result.candles_loaded,
        "trades_count": len(result.trades),
        "data_quality": result.data_quality.model_dump() if result.data_quality else None,
        "metrics": result.metrics.model_dump() if result.metrics else None,
        "equity_curve": {
            "timestamps": [t.isoformat() for t in result.equity_curve.timestamps],
            "equity_values": result.equity_curve.equity_values,
            "balance_values": result.equity_curve.balance_values,
            "drawdown_values": result.equity_curve.drawdown_values,
        } if result.equity_curve.length > 0 else None,
        "look_ahead_violations": len(result.look_ahead_violations),
        "error_message": result.error_message,
        "started_at": result.started_at.isoformat() if result.started_at else None,
        "completed_at": result.completed_at.isoformat() if result.completed_at else None,
        "duration_seconds": result.duration_seconds,
        "random_seed_used": result.random_seed_used,
    }


def _trade_to_dict(trade: "ClosedTrade") -> dict:
    """Convert a ClosedTrade to a JSON-serializable dict."""
    return {
        "trade_id": trade.trade_id,
        "instrument": trade.instrument,
        "side": trade.side.value,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "lots": trade.lots,
        "entry_time": trade.entry_time.isoformat(),
        "exit_time": trade.exit_time.isoformat(),
        "close_reason": trade.close_reason.value,
        "gross_pnl": trade.gross_pnl,
        "net_pnl": trade.net_pnl,
        "total_costs": trade.total_costs,
        "is_winner": trade.is_winner,
        "signal_id": trade.signal_id,
        "strategy_id": trade.strategy_id,
        "plan_id": trade.plan_id,
    }
