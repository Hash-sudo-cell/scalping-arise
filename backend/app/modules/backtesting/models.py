"""
Scalping Arise — Backtesting & Forward Testing Models

Strongly typed models for historical data replay, trade simulation,
account simulation, portfolio tracking, performance analytics,
robustness testing, walk-forward evaluation, and paper trading.

Phase 9 simulates trades only — no real broker execution.
All models enforce determinism: no datetime.now() in calculations,
optional seed fields for reproducibility.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ===========================================================================
# Enums — type-safe backtesting states
# ===========================================================================

class BacktestStatus(str, Enum):
    """Lifecycle status of a backtest run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BacktestMode(str, Enum):
    """Type of backtest execution."""

    HISTORICAL = "historical"
    WALK_FORWARD = "walk_forward"
    PAPER_TRADING = "paper_trading"
    MONTE_CARLO = "monte_carlo"
    STRESS_TEST = "stress_test"


class OrderType(str, Enum):
    """Order type for simulation."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    """Order direction."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order lifecycle status."""

    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionStatus(str, Enum):
    """Position lifecycle status."""

    OPEN = "open"
    CLOSED = "closed"
    PARTIALLY_CLOSED = "partially_closed"


class CloseReason(str, Enum):
    """How a position was closed."""

    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TIME_EXIT = "time_exit"
    SIGNAL_EXIT = "signal_exit"
    MANUAL = "manual"
    MARGIN_CALL = "margin_call"
    EXPIRED = "expired"


class FillMethod(str, Enum):
    """How orders are filled in simulation."""

    NEXT_BAR_OPEN = "next_bar_open"
    CURRENT_CLOSE = "current_close"
    CURRENT_CLOSE_WITH_SLIPPAGE = "current_close_with_slippage"
    NEXT_BAR_WITH_SLIPPAGE = "next_bar_with_slippage"


class SlippageModel(str, Enum):
    """Slippage calculation model."""

    FIXED = "fixed"
    PERCENTAGE = "percentage"
    ATR_MULTIPLE = "atr_multiple"
    SPREAD_BASED = "spread_based"


class DataGranularity(str, Enum):
    """Granularity of historical data loading."""

    DAILY = "daily"
    HOURLY = "hourly"
    MINUTE = "minute"
    TICK = "tick"


class WalkForwardMethod(str, Enum):
    """Walk-forward evaluation method."""

    ANCHORED = "anchored"
    ROLLING = "rolling"
    EXPANDING = "expanding"


class RobustnessMethod(str, Enum):
    """Robustness testing method."""

    MONTE_CARLO = "monte_carlo"
    BOOTSTRAP = "bootstrap"
    PARAMETER_SENSITIVITY = "parameter_sensitivity"
    REGIME_PARTITION = "regime_partition"


class RegimeType(str, Enum):
    """Market regime for partition testing."""

    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


# ===========================================================================
# Historical Data Models
# ===========================================================================

class HistoricalCandle(BaseModel):
    """A single historical candle with simulation metadata."""

    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    instrument: str
    timeframe: str

    @field_validator("high")
    @classmethod
    def high_gte_low(cls, v: float, info) -> float:  # noqa: ANN001
        """High must be >= low."""
        low = info.data.get("low", 0)
        if v < low and low > 0:
            raise ValueError(f"High ({v}) must be >= Low ({low})")
        return v

    @field_validator("high")
    @classmethod
    def high_gte_open_close(cls, v: float, info) -> float:  # noqa: ANN001
        """High must be >= open and close."""
        open_ = info.data.get("open", 0)
        close = info.data.get("close", 0)
        if v < open_ and open_ > 0:
            raise ValueError(f"High ({v}) must be >= Open ({open_})")
        if v < close and close > 0:
            raise ValueError(f"High ({v}) must be >= Close ({close})")
        return v

    @field_validator("low")
    @classmethod
    def low_lte_open_close(cls, v: float, info) -> float:  # noqa: ANN001
        """Low must be <= open and close."""
        open_ = info.data.get("open", 0)
        close = info.data.get("close", 0)
        if open_ > 0 and v > open_:
            raise ValueError(f"Low ({v}) must be <= Open ({open_})")
        if close > 0 and v > close:
            raise ValueError(f"Low ({v}) must be <= Close ({close})")
        return v


class DataSource(BaseModel):
    """Metadata about the source of historical data."""

    provider: str = Field(description="Data provider name")
    source_type: str = Field(description="e.g. 'api', 'csv', 'parquet', 'synthetic'")
    instrument: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    candle_count: int = Field(ge=0)
    has_volume: bool = True
    has_gaps: bool = False
    gap_count: int = Field(default=0, ge=0)


class DataQualityReport(BaseModel):
    """Data quality assessment for loaded historical data."""

    total_candles: int = Field(ge=0)
    valid_candles: int = Field(ge=0)
    invalid_candles: int = Field(ge=0)
    missing_volume_candles: int = Field(default=0, ge=0)
    gap_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    price_anomalies: int = Field(default=0, ge=0)
    volume_anomalies: int = Field(default=0, ge=0)
    time_gaps: list[datetime] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0, description="0.0 = poor, 1.0 = perfect")
    warnings: list[str] = Field(default_factory=list)


# ===========================================================================
# Look-Ahead Protection Models
# ===========================================================================

class TimeGate(BaseModel):
    """Time gate for look-ahead bias protection."""

    simulation_time: datetime = Field(description="Current simulation timestamp")
    max_lookahead_seconds: int = Field(
        default=0,
        ge=0,
        description="Maximum allowed future offset (0 = strict, no future data)",
    )
    strict_mode: bool = Field(
        default=True,
        description="If True, any future data access raises error. If False, logs warning.",
    )

    def is_accessible(self, data_timestamp: datetime) -> bool:
        """Check if data at given timestamp is accessible."""
        from datetime import timedelta
        max_future = self.simulation_time + timedelta(seconds=self.max_lookahead_seconds)
        return data_timestamp <= max_future

    def gate_violation(self, data_timestamp: datetime) -> Optional[str]:
        """Return violation message if access is denied, None if OK."""
        if self.is_accessible(data_timestamp):
            return None
        from datetime import timedelta
        overshoot = (data_timestamp - self.simulation_time).total_seconds()
        return (
            f"Look-ahead violation: data at {data_timestamp.isoformat()} "
            f"exceeds simulation time {self.simulation_time.isoformat()} "
            f"by {overshoot:.0f}s (max lookahead: {self.max_lookahead_seconds}s)"
        )


class LookAheadViolation(BaseModel):
    """Record of a look-ahead bias violation."""

    violation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    simulation_time: datetime
    data_timestamp: datetime
    overshoot_seconds: float
    component: str = Field(description="Which module detected the violation")
    detail: str = ""
    severity: str = Field(default="critical", description="critical, warning, info")


# ===========================================================================
# Candle Replay Models
# ===========================================================================

class ReplayState(BaseModel):
    """Current state of a candle replay iteration."""

    current_index: int = Field(ge=0, description="Index of current candle in dataset")
    total_candles: int = Field(ge=0)
    current_timestamp: datetime
    progress_pct: float = Field(ge=0.0, le=100.0)
    is_complete: bool = False
    candles_processed: int = Field(default=0, ge=0)
    signals_generated: int = Field(default=0, ge=0)
    trades_executed: int = Field(default=0, ge=0)
    plan_rejections: int = Field(default=0, ge=0)


class ReplaySlice(BaseModel):
    """A time-bounded slice of candle data available to strategies."""

    current_candle: HistoricalCandle
    visible_candles: list[HistoricalCandle] = Field(
        default_factory=list,
        description="All candles with timestamp <= current_candle.timestamp",
    )
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    candle_count: int = Field(ge=0)

    @property
    def prices(self) -> list[float]:
        """Extract close prices from visible candles."""
        return [c.close for c in self.visible_candles]

    @property
    def volumes(self) -> list[float]:
        """Extract volumes from visible candles."""
        return [c.volume for c in self.visible_candles]

    @property
    def highs(self) -> list[float]:
        """Extract highs from visible candles."""
        return [c.high for c in self.visible_candles]

    @property
    def lows(self) -> list[float]:
        """Extract lows from visible candles."""
        return [c.low for c in self.visible_candles]

    @property
    def opens(self) -> list[float]:
        """Extract opens from visible candles."""
        return [c.open for c in self.visible_candles]


# ===========================================================================
# Trade Simulation Models
# ===========================================================================

class SimulatedOrder(BaseModel):
    """A simulated order to be filled by the trade simulator."""

    order_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    instrument: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    lots: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0, description="Limit/stop price")
    stop_loss_price: Optional[float] = Field(default=None, gt=0)
    take_profit_price: Optional[float] = Field(default=None, gt=0)
    slippage_pips: float = Field(default=0.0, ge=0)
    signal_id: Optional[str] = None
    strategy_id: Optional[str] = None
    plan_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


class SimulatedFill(BaseModel):
    """A simulated fill (execution) of an order."""

    fill_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    instrument: str
    side: OrderSide
    lots: float = Field(gt=0)
    fill_price: float = Field(gt=0)
    slippage_pips: float = Field(ge=0)
    slippage_cost: float = Field(ge=0, description="Cost of slippage in account currency")
    spread_cost: float = Field(ge=0, description="Spread cost at fill time")
    commission: float = Field(default=0.0, ge=0)
    total_cost: float = Field(ge=0, description="slippage + spread + commission")
    fill_method: FillMethod
    timestamp: datetime
    is_live_price: bool = Field(
        default=False,
        description="Whether fill used live price (paper trading) vs simulated",
    )


class SimulatedPosition(BaseModel):
    """A simulated open position."""

    position_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    instrument: str
    side: OrderSide
    entry_price: float = Field(gt=0)
    current_price: float = Field(gt=0)
    lots: float = Field(gt=0)
    initial_lots: float = Field(gt=0)
    unrealized_pnl: float = Field(default=0.0)
    realized_pnl: float = Field(default=0.0)
    margin_used: float = Field(ge=0)
    stop_loss_price: Optional[float] = Field(default=None, gt=0)
    take_profit_price: Optional[float] = Field(default=None, gt=0)
    trailing_stop_active: bool = False
    trailing_stop_distance: Optional[float] = None
    signal_id: Optional[str] = None
    strategy_id: Optional[str] = None
    plan_id: Optional[str] = None
    opened_at: datetime
    last_price_update: datetime
    status: PositionStatus = PositionStatus.OPEN

    @property
    def holding_duration_seconds(self) -> float:
        """Duration the position has been open."""
        delta = self.last_price_update - self.opened_at
        return delta.total_seconds()

    def update_price(self, new_price: float) -> None:
        """Update current price and recalculate unrealized P&L."""
        self.current_price = new_price
        self.last_price_update = datetime.now(timezone.utc)
        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (new_price - self.entry_price) * self.lots * self._contract_size
        else:
            self.unrealized_pnl = (self.entry_price - new_price) * self.lots * self._contract_size

    @property
    def _contract_size(self) -> float:
        """Contract size — defaults to 100 for XAU/USD."""
        from app.modules.trade_planning.instrument_specs import get_spec
        spec = get_spec(self.instrument)
        return spec.contract_size if spec else 100.0


class ClosedTrade(BaseModel):
    """A completed (closed) simulated trade."""

    trade_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    instrument: str
    side: OrderSide
    entry_price: float = Field(gt=0)
    exit_price: float = Field(gt=0)
    lots: float = Field(gt=0)
    entry_time: datetime
    exit_time: datetime
    close_reason: CloseReason
    gross_pnl: float = Field(description="P&L before costs")
    net_pnl: float = Field(description="P&L after costs")
    total_costs: float = Field(ge=0, description="Total transaction costs")
    slippage_cost: float = Field(default=0.0, ge=0)
    spread_cost: float = Field(default=0.0, ge=0)
    commission: float = Field(default=0.0, ge=0)
    max_favorable_excursion: float = Field(default=0.0, description="Peak unrealized profit")
    max_adverse_excursion: float = Field(default=0.0, description="Peak unrealized loss")
    signal_id: Optional[str] = None
    strategy_id: Optional[str] = None
    plan_id: Optional[str] = None
    risk_reward_achieved: Optional[float] = Field(default=None, ge=0)
    holding_bars: int = Field(default=0, ge=0)

    @property
    def is_winner(self) -> bool:
        """Whether this trade was profitable."""
        return self.net_pnl > 0

    @property
    def holding_duration_seconds(self) -> float:
        """Duration of the trade."""
        return (self.exit_time - self.entry_time).total_seconds()

    @property
    def risk_reward_actual(self) -> float:
        """Actual risk-to-reward ratio."""
        risk = abs(self.entry_price - self.exit_price) if self.net_pnl < 0 else 0
        if risk <= 0:
            return float("inf") if self.net_pnl > 0 else 0.0
        return abs(self.net_pnl) / (risk * self.lots * self._contract_size)

    @property
    def _contract_size(self) -> float:
        from app.modules.trade_planning.instrument_specs import get_spec
        spec = get_spec(self.instrument)
        return spec.contract_size if spec else 100.0


# ===========================================================================
# Account Simulation Models
# ===========================================================================

class AccountSnapshot(BaseModel):
    """Point-in-time snapshot of account state."""

    timestamp: datetime
    balance: float = Field(ge=0)
    equity: float = Field(ge=0, description="Balance + unrealized P&L")
    margin_used: float = Field(ge=0)
    margin_free: float = Field(ge=0)
    unrealized_pnl: float = Field(default=0.0)
    realized_pnl: float = Field(default=0.0)
    open_positions: int = Field(ge=0)
    drawdown_pct: float = Field(ge=0, description="Drawdown as percentage from peak")
    drawdown_amount: float = Field(ge=0)
    peak_balance: float = Field(ge=0)
    daily_pnl: float = Field(default=0.0)
    daily_pnl_pct: float = Field(default=0.0)


class AccountConfig(BaseModel):
    """Account configuration for simulation."""

    initial_balance: float = Field(gt=0, default=10000.0)
    currency: str = Field(default="USD")
    max_positions: int = Field(ge=1, default=3)
    max_portfolio_risk_pct: float = Field(gt=0, le=100, default=5.0)
    max_daily_loss_pct: float = Field(gt=0, le=100, default=3.0)
    max_drawdown_pct: float = Field(gt=0, le=100, default=10.0)
    margin_call_pct: float = Field(gt=0, le=100, default=50.0, description="Margin level for margin call")
    allow_partial_closes: bool = Field(default=True)
    enable_trailing_stop: bool = Field(default=False)
    trailing_stop_activation_pct: float = Field(default=1.0, ge=0, description="% profit to activate trailing")
    trailing_stop_distance_pct: float = Field(default=0.5, ge=0, description="Trailing stop distance in %")


class EquityCurve(BaseModel):
    """Complete equity curve for a backtest run."""

    timestamps: list[datetime] = Field(default_factory=list)
    equity_values: list[float] = Field(default_factory=list)
    balance_values: list[float] = Field(default_factory=list)
    drawdown_values: list[float] = Field(default_factory=list)
    unrealized_pnl_values: list[float] = Field(default_factory=list)
    open_position_counts: list[int] = Field(default_factory=list)

    def append(self, snapshot: AccountSnapshot) -> None:
        """Append a snapshot to the curve."""
        self.timestamps.append(snapshot.timestamp)
        self.equity_values.append(snapshot.equity)
        self.balance_values.append(snapshot.balance)
        self.drawdown_values.append(snapshot.drawdown_pct)
        self.unrealized_pnl_values.append(snapshot.unrealized_pnl)
        self.open_position_counts.append(snapshot.open_positions)

    @property
    def length(self) -> int:
        return len(self.timestamps)


# ===========================================================================
# Performance Analytics Models
# ===========================================================================

class TradeStatistics(BaseModel):
    """Aggregate statistics from closed trades."""

    total_trades: int = Field(ge=0)
    winning_trades: int = Field(ge=0)
    losing_trades: int = Field(ge=0)
    breakeven_trades: int = Field(default=0, ge=0)
    win_rate: float = Field(ge=0.0, le=1.0)
    loss_rate: float = Field(ge=0.0, le=1.0)
    avg_win: float = Field(default=0.0)
    avg_loss: float = Field(default=0.0)
    largest_win: float = Field(default=0.0)
    largest_loss: float = Field(default=0.0)
    avg_trade_duration_seconds: float = Field(default=0.0, ge=0)
    avg_holding_bars: float = Field(default=0.0, ge=0)
    profit_factor: float = Field(ge=0.0, description="Gross wins / gross losses")
    expectancy: float = Field(description="Expected value per trade")
    kelly_criterion: float = Field(default=0.0, description="Optimal position size fraction")
    consecutive_wins: int = Field(ge=0)
    consecutive_losses: int = Field(ge=0)
    max_consecutive_wins: int = Field(ge=0)
    max_consecutive_losses: int = Field(ge=0)
    payoff_ratio: float = Field(default=0.0, ge=0, description="Avg win / avg loss")
    recovery_factor: float = Field(default=0.0, description="Net profit / max drawdown")


class RiskMetrics(BaseModel):
    """Risk-adjusted performance metrics."""

    sharpe_ratio: float = Field(description="Annualized Sharpe ratio")
    sortino_ratio: float = Field(description="Annualized Sortino ratio")
    calmar_ratio: float = Field(description="Annualized return / max drawdown")
    max_drawdown_pct: float = Field(ge=0, description="Maximum drawdown percentage")
    max_drawdown_amount: float = Field(ge=0)
    max_drawdown_duration_seconds: float = Field(ge=0)
    max_drawdown_recovery_seconds: float = Field(ge=0)
    volatility_annual: float = Field(ge=0, description="Annualized volatility")
    downside_deviation: float = Field(ge=0)
    tail_ratio: float = Field(default=0.0, description="95th percentile gain / 5th percentile loss")
    value_at_risk_95: float = Field(default=0.0, description="95% VaR")
    conditional_var_95: float = Field(default=0.0, description="Conditional VaR (expected shortfall)")


class CostAnalysis(BaseModel):
    """Transaction cost analysis."""

    total_slippage_cost: float = Field(ge=0)
    total_spread_cost: float = Field(ge=0)
    total_commission: float = Field(ge=0)
    total_costs: float = Field(ge=0)
    avg_cost_per_trade: float = Field(ge=0)
    cost_as_pct_of_pnl: float = Field(default=0.0, description="Total costs as % of gross P&L")
    slippage_bps: float = Field(default=0.0, description="Average slippage in basis points")


class PerformanceMetrics(BaseModel):
    """Complete performance metrics for a backtest run."""

    # Return metrics
    total_return: float = Field(description="Total return as fraction")
    total_return_pct: float = Field(description="Total return as percentage")
    annualized_return: float = Field(description="Annualized return")
    monthly_avg_return: float = Field(default=0.0)
    daily_avg_return: float = Field(default=0.0)

    # Trade statistics
    trade_stats: TradeStatistics

    # Risk metrics
    risk_metrics: RiskMetrics

    # Cost analysis
    cost_analysis: CostAnalysis

    # Raw data
    net_profit: float = Field(description="Final equity - initial equity")
    gross_profit: float = Field(ge=0)
    gross_loss: float = Field(ge=0)
    initial_balance: float = Field(gt=0)
    final_balance: float = Field(ge=0)
    peak_equity: float = Field(ge=0)
    test_duration_seconds: float = Field(ge=0)
    candles_processed: int = Field(ge=0)


# ===========================================================================
# Robustness Testing Models
# ===========================================================================

class MonteCarloConfig(BaseModel):
    """Configuration for Monte Carlo simulation."""

    num_simulations: int = Field(ge=100, default=1000, le=10000)
    confidence_level: float = Field(ge=0.90, le=0.99, default=0.95)
    random_seed: Optional[int] = None
    resample_with_replacement: bool = True


class BootstrapConfig(BaseModel):
    """Configuration for bootstrap analysis."""

    num_samples: int = Field(ge=100, default=1000, le=10000)
    sample_size_pct: float = Field(gt=0, le=1.0, default=0.8)
    random_seed: Optional[int] = None


class ParameterSensitivityConfig(BaseModel):
    """Configuration for parameter sensitivity testing."""

    parameters: dict[str, list[float]] = Field(
        default_factory=dict,
        description="Parameter name -> list of values to test",
    )
    base_metrics: Optional[PerformanceMetrics] = None


class RegimePartitionConfig(BaseModel):
    """Configuration for regime-based partition testing."""

    regimes: list[RegimeType] = Field(
        default_factory=lambda: list(RegimeType),
        description="Which regimes to test",
    )
    min_candles_per_regime: int = Field(ge=10, default=50)


class RobustnessResult(BaseModel):
    """Result of a robustness test."""

    method: RobustnessMethod
    num_simulations: int = Field(ge=0)
    confidence_interval_lower: Optional[float] = None
    confidence_interval_upper: Optional[float] = None
    p_value: Optional[float] = Field(default=None, ge=0, le=1)
    stability_score: float = Field(ge=0.0, le=1.0, description="1.0 = perfectly stable")
    simulations: list[PerformanceMetrics] = Field(default_factory=list)
    percentiles: dict[str, float] = Field(default_factory=dict, description="metric -> percentile value")
    warnings: list[str] = Field(default_factory=list)


# ===========================================================================
# Walk-Forward Models
# ===========================================================================

class WalkForwardFold(BaseModel):
    """A single fold in walk-forward evaluation."""

    fold_id: int = Field(ge=0)
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_candle_count: int = Field(ge=0)
    test_candle_count: int = Field(ge=0)
    in_sample_metrics: Optional[PerformanceMetrics] = None
    out_of_sample_metrics: Optional[PerformanceMetrics] = None
    strategies_used: list[str] = Field(default_factory=list)
    status: str = Field(default="pending", description="pending, running, completed, failed")


class WalkForwardConfig(BaseModel):
    """Configuration for walk-forward evaluation."""

    method: WalkForwardMethod = WalkForwardMethod.ROLLING
    train_window_candles: int = Field(ge=100, default=1000)
    test_window_candles: int = Field(ge=10, default=200)
    step_size_candles: int = Field(ge=10, default=200)
    min_folds: int = Field(ge=2, default=3)
    max_folds: int = Field(ge=3, default=20)
    anchored_start: Optional[datetime] = None
    strategy_ids: Optional[list[str]] = None
    optimization_metric: str = Field(default="sharpe_ratio", description="Metric to optimize in-sample")
    oos_consistency_threshold: float = Field(
        ge=0.0, le=1.0, default=0.5,
        description="Min fraction of OOS folds that must be profitable",
    )


class WalkForwardResult(BaseModel):
    """Complete walk-forward evaluation result."""

    config: WalkForwardConfig
    folds: list[WalkForwardFold] = Field(default_factory=list)
    aggregate_oos_metrics: Optional[PerformanceMetrics] = None
    consistency_ratio: float = Field(ge=0.0, le=1.0, description="Profitable OOS folds / total folds")
    overfit_score: float = Field(
        ge=0.0, le=1.0,
        description="IS vs OOS degradation — 1.0 = no overfit, 0.0 = severe overfit",
    )
    total_folds: int = Field(ge=0)
    completed_folds: int = Field(ge=0)
    status: str = Field(default="pending")


# ===========================================================================
# Paper Trading Models
# ===========================================================================

class PaperTradeConfig(BaseModel):
    """Configuration for paper trading."""

    instrument: str = Field(default="XAU/USD")
    strategy_ids: Optional[list[str]] = None
    check_interval_seconds: int = Field(ge=10, default=60)
    initial_balance: float = Field(gt=0, default=10000.0)
    max_positions: int = Field(ge=1, default=3)
    risk_per_trade_pct: float = Field(gt=0, le=100, default=1.0)
    use_live_price: bool = Field(default=True, description="Use live price feed or simulated")
    max_duration_seconds: Optional[int] = Field(default=None, ge=60, description="Max paper trading duration")


class PaperTradeSession(BaseModel):
    """State of an active paper trading session."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    config: PaperTradeConfig
    status: str = Field(default="active", description="active, paused, stopped")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_update: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trades: list[ClosedTrade] = Field(default_factory=list)
    open_positions: list[SimulatedPosition] = Field(default_factory=list)
    account_config: AccountConfig
    balance: float = Field(ge=0)
    equity: float = Field(ge=0)
    total_trades: int = Field(ge=0)
    win_rate: float = Field(ge=0.0, le=1.0)
    net_pnl: float = Field(default=0.0)
    max_drawdown_pct: float = Field(ge=0)


# ===========================================================================
# Versioning Models
# ===========================================================================

class RunMetadata(BaseModel):
    """Metadata for a backtest run for versioning and comparison."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = Field(default="1.0.0")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="system")
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    parent_run_id: Optional[str] = None
    config_hash: str = Field(default="", description="Deterministic hash of run config")
    data_hash: str = Field(default="", description="Hash of input data metadata")
    is_deterministic: bool = Field(default=True, description="Whether run used seeded RNG")

    def compute_config_hash(self, config: dict[str, Any]) -> str:
        """Compute deterministic hash of configuration."""
        config_str = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]


# ===========================================================================
# Backtest Run Models (top-level)
# ===========================================================================

class BacktestConfig(BaseModel):
    """Complete configuration for a backtest run."""

    # Mode
    mode: BacktestMode = BacktestMode.HISTORICAL

    # Data
    instrument: str = Field(default="XAU/USD")
    timeframe: str = Field(default="1h")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    candle_limit: Optional[int] = Field(default=None, ge=100, description="Max candles to load")

    # Simulation
    fill_method: FillMethod = FillMethod.NEXT_BAR_OPEN
    slippage_model: SlippageModel = SlippageModel.FIXED
    slippage_pips: float = Field(default=1.0, ge=0)
    spread_pips: float = Field(default=3.0, ge=0)

    # Account
    account: AccountConfig = Field(default_factory=AccountConfig)

    # Strategies
    strategy_ids: Optional[list[str]] = Field(default=None, description="Strategies to test (None = all enabled)")
    timeframes: list[str] = Field(default_factory=lambda: ["1m", "5m", "15m"])

    # Signal engine params (passed through)
    candle_limit_per_tf: int = Field(default=300, ge=50)

    # Walk-forward
    walk_forward: Optional[WalkForwardConfig] = None

    # Robustness
    robustness_method: Optional[RobustnessMethod] = None
    monte_carlo_config: Optional[MonteCarloConfig] = None
    bootstrap_config: Optional[BootstrapConfig] = None
    parameter_sensitivity: Optional[ParameterSensitivityConfig] = None
    regime_partition: Optional[RegimePartitionConfig] = None

    # Determinism
    random_seed: Optional[int] = Field(default=None, description="Global seed for reproducibility")

    # Look-ahead protection
    look_ahead_strict: bool = Field(default=True)
    max_lookahead_seconds: int = Field(default=0, ge=0)

    # Limits
    max_trades: Optional[int] = Field(default=None, ge=1, description="Max trades to simulate")
    max_duration_seconds: Optional[int] = Field(default=None, ge=60)


class BacktestResult(BaseModel):
    """Complete result of a backtest run."""

    # Identification
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    config: BacktestConfig
    metadata: Optional[RunMetadata] = None

    # Status
    status: BacktestStatus = BacktestStatus.PENDING
    error_message: Optional[str] = None

    # Data
    candles_loaded: int = Field(default=0, ge=0)
    data_quality: Optional[DataQualityReport] = None
    data_source: Optional[DataSource] = None

    # Results
    trades: list[ClosedTrade] = Field(default_factory=list)
    equity_curve: EquityCurve = Field(default_factory=EquityCurve)
    account_snapshots: list[AccountSnapshot] = Field(default_factory=list)

    # Performance
    metrics: Optional[PerformanceMetrics] = None

    # Robustness (if applicable)
    robustness_results: list[RobustnessResult] = Field(default_factory=list)

    # Walk-forward (if applicable)
    walk_forward_result: Optional[WalkForwardResult] = None

    # Look-ahead violations
    look_ahead_violations: list[LookAheadViolation] = Field(default_factory=list)

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = Field(default=None, ge=0)

    # Determinism
    is_deterministic: bool = True
    random_seed_used: Optional[int] = None


# ===========================================================================
# Convenience: Direction/decision mapping (bridges to Phase 6/7)
# ===========================================================================

def order_side_from_decision(decision: str) -> Optional[OrderSide]:
    """Map a Phase 6 DecisionType string to an OrderSide."""
    _map = {
        "buy": OrderSide.BUY,
        "sell": OrderSide.SELL,
    }
    return _map.get(decision)


def order_side_from_plan_side(plan_side: str) -> Optional[OrderSide]:
    """Map a Phase 7 PlanSide string to an OrderSide."""
    _map = {
        "long": OrderSide.BUY,
        "short": OrderSide.SELL,
    }
    return _map.get(plan_side)
