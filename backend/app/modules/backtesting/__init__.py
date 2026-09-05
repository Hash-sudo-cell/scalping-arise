"""
Scalping Arise — Backtesting & Forward Testing Module

Provides historical backtesting, walk-forward evaluation,
Monte Carlo simulation, paper trading, and performance analytics.

Phase 9 simulates trades only — no real broker execution.
"""

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.models import (
    AccountConfig,
    BacktestConfig,
    BacktestMode,
    BacktestResult,
    BacktestStatus,
    ClosedTrade,
    CloseReason,
    EquityCurve,
    FillMethod,
    HistoricalCandle,
    LookAheadViolation,
    OrderSide,
    OrderType,
    PerformanceMetrics,
    RiskMetrics,
    SlippageModel,
    SimulatedFill,
    SimulatedOrder,
    SimulatedPosition,
    TradeStatistics,
    WalkForwardConfig,
    WalkForwardMethod,
    WalkForwardResult,
)
from app.modules.backtesting.service import BacktestingService

__all__ = [
    # Config
    "BacktestingSettings",
    "get_backtesting_settings",
    # Models
    "AccountConfig",
    "BacktestConfig",
    "BacktestMode",
    "BacktestResult",
    "BacktestStatus",
    "ClosedTrade",
    "CloseReason",
    "EquityCurve",
    "FillMethod",
    "HistoricalCandle",
    "LookAheadViolation",
    "OrderSide",
    "OrderType",
    "PerformanceMetrics",
    "RiskMetrics",
    "SlippageModel",
    "SimulatedFill",
    "SimulatedOrder",
    "SimulatedPosition",
    "TradeStatistics",
    "WalkForwardConfig",
    "WalkForwardMethod",
    "WalkForwardResult",
    # Service
    "BacktestingService",
]
