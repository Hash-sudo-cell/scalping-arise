"""
Scalping Arise — Backtesting & Forward Testing Tests

Comprehensive test suite for Phase 9: models, config, history provider,
look-ahead guard, candle replay, trade simulator, account simulator,
portfolio simulator, performance analytics, robustness, walk-forward,
paper trading, versioning, runner, service, and API.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===========================================================================
# Model Tests
# ===========================================================================

from app.modules.backtesting.models import (
    AccountConfig,
    AccountSnapshot,
    BacktestConfig,
    BacktestMode,
    BacktestResult,
    BacktestStatus,
    BootstrapConfig,
    ClosedTrade,
    CloseReason,
    DataGranularity,
    DataQualityReport,
    DataSource,
    EquityCurve,
    FillMethod,
    HistoricalCandle,
    LookAheadViolation,
    MonteCarloConfig,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperTradeConfig,
    PaperTradeSession,
    PerformanceMetrics,
    PositionStatus,
    RegimeType,
    ReplaySlice,
    ReplayState,
    RiskMetrics,
    RobustnessMethod,
    RobustnessResult,
    SlippageModel,
    SimulatedFill,
    SimulatedOrder,
    SimulatedPosition,
    TimeGate,
    TradeStatistics,
    WalkForwardConfig,
    WalkForwardFold,
    WalkForwardMethod,
    WalkForwardResult,
    order_side_from_decision,
    order_side_from_plan_side,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(
    ts: datetime,
    balance: float = 10000.0,
    equity: float | None = None,
    open_positions: int = 0,
    peak: float = 10000.0,
) -> AccountSnapshot:
    """Create an AccountSnapshot with all required fields."""
    return AccountSnapshot(
        timestamp=ts,
        balance=balance,
        equity=equity if equity is not None else balance,
        margin_used=0.0,
        margin_free=equity if equity is not None else balance,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        open_positions=open_positions,
        drawdown_pct=0.0,
        drawdown_amount=0.0,
        peak_balance=peak,
    )


def _make_candles(count: int = 10, start: datetime | None = None) -> list[HistoricalCandle]:
    """Create test candles with day+hour spacing to avoid hour overflow."""
    base = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        HistoricalCandle(
            timestamp=base + timedelta(hours=i),
            open=2650.0 + i, high=2660.0 + i, low=2640.0 + i, close=2655.0 + i,
            volume=1000 + i * 100, instrument="XAU/USD", timeframe="1h",
        )
        for i in range(count)
    ]


def _make_trades() -> list[ClosedTrade]:
    """Create test trades with known outcomes."""
    return [
        ClosedTrade(
            instrument="XAU/USD", side=OrderSide.BUY,
            entry_price=2650.0, exit_price=2660.0, lots=0.1,
            entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            exit_time=datetime(2024, 1, 1, 2, tzinfo=timezone.utc),
            close_reason=CloseReason.TAKE_PROFIT,
            gross_pnl=100.0, net_pnl=95.0, total_costs=5.0,
            slippage_cost=2.0, spread_cost=3.0,
        ),
        ClosedTrade(
            instrument="XAU/USD", side=OrderSide.SELL,
            entry_price=2660.0, exit_price=2655.0, lots=0.1,
            entry_time=datetime(2024, 1, 1, 3, tzinfo=timezone.utc),
            exit_time=datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
            close_reason=CloseReason.TAKE_PROFIT,
            gross_pnl=50.0, net_pnl=46.0, total_costs=4.0,
            slippage_cost=1.5, spread_cost=2.5,
        ),
        ClosedTrade(
            instrument="XAU/USD", side=OrderSide.BUY,
            entry_price=2655.0, exit_price=2650.0, lots=0.1,
            entry_time=datetime(2024, 1, 1, 6, tzinfo=timezone.utc),
            exit_time=datetime(2024, 1, 1, 8, tzinfo=timezone.utc),
            close_reason=CloseReason.STOP_LOSS,
            gross_pnl=-50.0, net_pnl=-54.0, total_costs=4.0,
            slippage_cost=1.5, spread_cost=2.5,
        ),
        ClosedTrade(
            instrument="XAU/USD", side=OrderSide.SELL,
            entry_price=2650.0, exit_price=2645.0, lots=0.1,
            entry_time=datetime(2024, 1, 1, 9, tzinfo=timezone.utc),
            exit_time=datetime(2024, 1, 1, 11, tzinfo=timezone.utc),
            close_reason=CloseReason.TAKE_PROFIT,
            gross_pnl=50.0, net_pnl=46.0, total_costs=4.0,
            slippage_cost=1.5, spread_cost=2.5,
        ),
    ]


# ===========================================================================
# Model Tests
# ===========================================================================

class TestHistoricalCandle:
    def test_candle_creation(self):
        c = HistoricalCandle(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=2650.0, high=2660.0, low=2640.0, close=2655.0,
            volume=1000, instrument="XAU/USD", timeframe="1h",
        )
        assert c.open == 2650.0
        assert c.high == 2660.0
        assert c.low == 2640.0
        assert c.close == 2655.0
        assert c.volume == 1000

    def test_candle_high_must_be_gte_low(self):
        with pytest.raises(ValueError):
            HistoricalCandle(
                timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                open=2650.0, high=2630.0, low=2640.0, close=2655.0,
                volume=1000, instrument="XAU/USD", timeframe="1h",
            )


class TestTimeGate:
    def test_accessible(self):
        gate = TimeGate(
            simulation_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            max_lookahead_seconds=0,
        )
        assert gate.is_accessible(datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)) is True
        assert gate.is_accessible(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)) is True
        assert gate.is_accessible(datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)) is False

    def test_with_lookahead(self):
        gate = TimeGate(
            simulation_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            max_lookahead_seconds=3600,
        )
        assert gate.is_accessible(datetime(2024, 1, 1, 12, 30, tzinfo=timezone.utc)) is True
        assert gate.is_accessible(datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)) is True
        assert gate.is_accessible(datetime(2024, 1, 1, 13, 1, tzinfo=timezone.utc)) is False

    def test_violation_message(self):
        gate = TimeGate(
            simulation_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            max_lookahead_seconds=0,
        )
        msg = gate.gate_violation(datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc))
        assert msg is not None
        assert "Look-ahead violation" in msg

    def test_no_violation(self):
        gate = TimeGate(
            simulation_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            max_lookahead_seconds=0,
        )
        msg = gate.gate_violation(datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc))
        assert msg is None


class TestEquityCurve:
    def test_append(self):
        ec = EquityCurve()
        snap = _make_snapshot(datetime(2024, 1, 1, tzinfo=timezone.utc))
        ec.append(snap)
        assert ec.length == 1
        assert ec.equity_values[0] == 10000.0


class TestOrderSideMapping:
    def test_buy_mapping(self):
        assert order_side_from_decision("buy") == OrderSide.BUY

    def test_sell_mapping(self):
        assert order_side_from_decision("sell") == OrderSide.SELL

    def test_no_trade_mapping(self):
        assert order_side_from_decision("no_trade") is None

    def test_plan_side_long(self):
        assert order_side_from_plan_side("long") == OrderSide.BUY

    def test_plan_side_short(self):
        assert order_side_from_plan_side("short") == OrderSide.SELL


# ===========================================================================
# Config Tests
# ===========================================================================

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings


class TestBacktestingSettings:
    def test_defaults(self):
        s = BacktestingSettings()
        assert s.backtesting_enabled is True
        assert s.enforce_determinism is True
        assert s.strict_lookahead is True
        assert s.default_initial_balance == 10000.0
        assert s.default_random_seed == 42

    def test_is_enabled(self):
        s = BacktestingSettings()
        assert s.is_enabled is True

    def test_disabled(self):
        s = BacktestingSettings(backtesting_enabled=False)
        assert s.is_enabled is False

    def test_get_settings(self):
        s = get_backtesting_settings()
        assert isinstance(s, BacktestingSettings)


# ===========================================================================
# Look-Ahead Guard Tests
# ===========================================================================

from app.modules.backtesting.look_ahead_guard import LookAheadGuard


class TestLookAheadGuard:
    def test_basic_guard(self):
        guard = LookAheadGuard(
            simulation_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        assert guard.check_access(datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)) is True
        assert guard.check_access(datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)) is False

    def test_advance(self):
        guard = LookAheadGuard(
            simulation_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        guard.advance(datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc))
        assert guard.simulation_time == datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc)
        assert guard.check_access(datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)) is True

    def test_violations_recorded(self):
        guard = LookAheadGuard(
            simulation_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        guard.check_access(datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc))
        assert guard.violation_count == 1

    def test_filter_candles(self):
        guard = LookAheadGuard(
            simulation_time=datetime(2024, 1, 3, 0, 0, tzinfo=timezone.utc),
        )
        # 5 candles: 3 before gate (Jan 1, 2, 3 midnight), 2 after (Jan 4, 5)
        candles = [
            HistoricalCandle(
                timestamp=datetime(2024, 1, 1 + i, tzinfo=timezone.utc),
                open=100, high=110, low=90, close=105,
                volume=100, instrument="XAU/USD", timeframe="1d",
            )
            for i in range(5)
        ]
        visible = guard.filter_candles(candles)
        # simulation_time=Jan 3 00:00 => accessible: Jan 1, Jan 2, Jan 3
        assert len(visible) == 3

    def test_reset(self):
        guard = LookAheadGuard(
            simulation_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        guard.check_access(datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc))
        assert guard.violation_count == 1
        guard.reset(datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc))
        assert guard.violation_count == 0
        assert guard.simulation_time == datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc)

    def test_summary(self):
        guard = LookAheadGuard(
            simulation_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        s = guard.summary()
        assert "simulation_time" in s
        assert "total_violations" in s


# ===========================================================================
# Candle Replay Tests
# ===========================================================================

from app.modules.backtesting.candle_replay import CandleReplayEngine


class TestCandleReplayEngine:
    def test_iteration(self):
        candles = _make_candles(5)
        engine = CandleReplayEngine(candles)
        slices = list(engine)
        assert len(slices) == 5
        assert slices[0].current_candle == candles[0]
        assert slices[-1].current_candle == candles[4]

    def test_visible_candles_grow(self):
        candles = _make_candles(5)
        engine = CandleReplayEngine(candles)
        slices = list(engine)
        assert slices[0].candle_count == 1
        assert slices[1].candle_count == 2
        assert slices[4].candle_count == 5

    def test_progress(self):
        candles = _make_candles(10)
        engine = CandleReplayEngine(candles)
        assert engine.progress_pct == 0.0
        next(engine)
        assert engine.progress_pct == 10.0

    def test_reset(self):
        candles = _make_candles(5)
        engine = CandleReplayEngine(candles)
        list(engine)
        assert engine.is_complete
        engine.reset()
        assert not engine.is_complete
        assert engine.current_index == 0

    def test_seek_to(self):
        candles = _make_candles(10)
        engine = CandleReplayEngine(candles)
        found = engine.seek_to(datetime(2024, 1, 1, 5, 0, tzinfo=timezone.utc))
        assert found is True
        assert engine.current_index == 5

    def test_empty_candles(self):
        engine = CandleReplayEngine([])
        assert engine.is_complete
        assert list(engine) == []

    def test_summary(self):
        candles = _make_candles(5)
        engine = CandleReplayEngine(candles)
        s = engine.summary()
        assert s["total_candles"] == 5
        assert s["signals_generated"] == 0

    def test_callback(self):
        candles = _make_candles(3)
        engine = CandleReplayEngine(candles)
        received = []
        engine.on_candle(lambda s: received.append(s))
        list(engine)
        assert len(received) == 3


# ===========================================================================
# Trade Simulator Tests
# ===========================================================================

from app.modules.backtesting.trade_simulator import TradeSimulator


class TestTradeSimulator:
    def test_market_fill(self):
        sim = TradeSimulator(
            fill_method=FillMethod.NEXT_BAR_OPEN,
            slippage_pips=0,
            spread_pips=0,
        )
        candle = HistoricalCandle(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=2650.0, high=2660.0, low=2640.0, close=2655.0,
            volume=1000, instrument="XAU/USD", timeframe="1h",
        )
        order = SimulatedOrder(
            instrument="XAU/USD",
            side=OrderSide.BUY,
            lots=0.1,
        )
        sim.submit_order(order)
        fills = sim.process_orders(candle)
        assert len(fills) == 1
        assert fills[0].fill_price == 2650.0  # open price for NEXT_BAR_OPEN

    def test_limit_fill(self):
        sim = TradeSimulator(slippage_pips=0, spread_pips=0)
        candle = HistoricalCandle(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=2650.0, high=2660.0, low=2640.0, close=2655.0,
            volume=1000, instrument="XAU/USD", timeframe="1h",
        )
        order = SimulatedOrder(
            instrument="XAU/USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            lots=0.1,
            price=2645.0,
        )
        sim.submit_order(order)
        fills = sim.process_orders(candle)
        assert len(fills) == 1
        assert fills[0].fill_price == 2645.0

    def test_limit_no_fill(self):
        sim = TradeSimulator(slippage_pips=0, spread_pips=0)
        candle = HistoricalCandle(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=2650.0, high=2660.0, low=2645.0, close=2655.0,
            volume=1000, instrument="XAU/USD", timeframe="1h",
        )
        order = SimulatedOrder(
            instrument="XAU/USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            lots=0.1,
            price=2640.0,  # low is 2645, won't touch 2640
        )
        sim.submit_order(order)
        fills = sim.process_orders(candle)
        assert len(fills) == 0

    def test_cancel_order(self):
        sim = TradeSimulator()
        order = SimulatedOrder(
            instrument="XAU/USD",
            side=OrderSide.BUY,
            lots=0.1,
        )
        sim.submit_order(order)
        assert len(sim.pending_orders) == 1
        cancelled = sim.cancel_order(order.order_id)
        assert cancelled is True
        assert len(sim.pending_orders) == 0

    def test_slippage_applied(self):
        # Use NEXT_BAR_WITH_SLIPPAGE to trigger slippage calculation
        sim = TradeSimulator(
            fill_method=FillMethod.NEXT_BAR_WITH_SLIPPAGE,
            slippage_pips=2.0,
            spread_pips=0,
        )
        candle = HistoricalCandle(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=2650.0, high=2660.0, low=2640.0, close=2655.0,
            volume=1000, instrument="XAU/USD", timeframe="1h",
        )
        order = SimulatedOrder(
            instrument="XAU/USD",
            side=OrderSide.BUY,
            lots=0.1,
        )
        sim.submit_order(order)
        fills = sim.process_orders(candle)
        assert len(fills) == 1
        assert fills[0].fill_price > 2650.0  # slippage worsens buy

    def test_position_creation(self):
        sim = TradeSimulator(slippage_pips=0, spread_pips=0)
        candle = HistoricalCandle(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=2650.0, high=2660.0, low=2640.0, close=2655.0,
            volume=1000, instrument="XAU/USD", timeframe="1h",
        )
        order = SimulatedOrder(
            instrument="XAU/USD",
            side=OrderSide.BUY,
            lots=0.1,
        )
        sim.submit_order(order)
        fills = sim.process_orders(candle)
        position = sim.create_position_from_fill(fills[0])
        assert position.entry_price == 2650.0
        assert position.side == OrderSide.BUY
        assert position.lots == 0.1

    def test_sl_tp_check(self):
        sim = TradeSimulator()
        position = SimulatedPosition(
            instrument="XAU/USD",
            side=OrderSide.BUY,
            entry_price=2650.0,
            current_price=2650.0,
            lots=0.1,
            initial_lots=0.1,
            margin_used=100.0,
            stop_loss_price=2640.0,
            take_profit_price=2665.0,
            opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            last_price_update=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        # Candle hits SL
        candle_sl = HistoricalCandle(
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            open=2645.0, high=2648.0, low=2638.0, close=2642.0,
            volume=1000, instrument="XAU/USD", timeframe="1h",
        )
        reason = sim.check_sl_tp_hit(position, candle_sl)
        assert reason == CloseReason.STOP_LOSS

        # Candle hits TP
        candle_tp = HistoricalCandle(
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            open=2655.0, high=2668.0, low=2652.0, close=2660.0,
            volume=1000, instrument="XAU/USD", timeframe="1h",
        )
        reason = sim.check_sl_tp_hit(position, candle_tp)
        assert reason == CloseReason.TAKE_PROFIT

    def test_summary(self):
        sim = TradeSimulator()
        s = sim.summary()
        assert "fill_method" in s
        assert "pending_orders" in s


# ===========================================================================
# Account Simulator Tests
# ===========================================================================

from app.modules.backtesting.account_simulator import AccountSimulator


class TestAccountSimulator:
    def test_initial_state(self):
        acc = AccountSimulator(AccountConfig(initial_balance=10000.0))
        assert acc.balance == 10000.0
        assert acc.peak_balance == 10000.0
        assert acc.current_drawdown_pct == 0.0

    def test_can_open_position(self):
        acc = AccountSimulator(AccountConfig(initial_balance=10000.0, max_positions=3))
        assert acc.can_open_position(0) is True
        assert acc.can_open_position(2) is True
        assert acc.can_open_position(3) is False

    def test_drawdown(self):
        acc = AccountSimulator(AccountConfig(initial_balance=10000.0))
        acc._balance = 9000.0
        assert acc.current_drawdown_pct == 10.0
        assert acc.current_drawdown_amount == 1000.0

    def test_daily_reset(self):
        acc = AccountSimulator()
        # First call initializes _last_daily_reset_date
        reset1 = acc.check_daily_reset(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))
        assert reset1 is False
        # Second call on same day: no reset
        reset2 = acc.check_daily_reset(datetime(2024, 1, 1, 18, 0, tzinfo=timezone.utc))
        assert reset2 is False
        # Third call on new day: reset
        reset3 = acc.check_daily_reset(datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc))
        assert reset3 is True

    def test_reset(self):
        acc = AccountSimulator(AccountConfig(initial_balance=5000.0))
        acc._balance = 3000.0
        acc.reset()
        assert acc.balance == 5000.0
        assert acc.peak_balance == 5000.0

    def test_summary(self):
        acc = AccountSimulator()
        s = acc.summary()
        assert s["initial_balance"] == 10000.0


# ===========================================================================
# Portfolio Simulator Tests
# ===========================================================================

from app.modules.backtesting.portfolio_simulator import PortfolioSimulator


class TestPortfolioSimulator:
    def _make_position(self) -> SimulatedPosition:
        return SimulatedPosition(
            instrument="XAU/USD",
            side=OrderSide.BUY,
            entry_price=2650.0,
            current_price=2650.0,
            lots=0.1,
            initial_lots=0.1,
            margin_used=100.0,
            opened_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            last_price_update=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    def test_open_position(self):
        acc = AccountSimulator(AccountConfig(initial_balance=10000.0, max_positions=3))
        portfolio = PortfolioSimulator(account=acc)
        pos = self._make_position()
        opened = portfolio.open_position(pos)
        assert opened is True
        assert portfolio.position_count == 1

    def test_max_positions(self):
        acc = AccountSimulator(AccountConfig(initial_balance=10000.0, max_positions=2))
        portfolio = PortfolioSimulator(account=acc)
        for _ in range(2):
            portfolio.open_position(self._make_position())
        assert portfolio.position_count == 2
        opened = portfolio.open_position(self._make_position())
        assert opened is False

    def test_close_position(self):
        acc = AccountSimulator(AccountConfig(initial_balance=10000.0))
        portfolio = PortfolioSimulator(account=acc)
        pos = self._make_position()
        portfolio.open_position(pos)

        trade = portfolio.close_position(
            pos,
            reason=CloseReason.TAKE_PROFIT,
            exit_price=2660.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
        assert trade.is_winner is True
        assert trade.net_pnl > 0
        assert portfolio.position_count == 0
        assert portfolio.total_trades == 1

    def test_close_all_positions(self):
        acc = AccountSimulator(AccountConfig(initial_balance=10000.0))
        portfolio = PortfolioSimulator(account=acc)
        for _ in range(3):
            portfolio.open_position(self._make_position())

        candle = HistoricalCandle(
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            open=2650.0, high=2660.0, low=2640.0, close=2655.0,
            volume=1000, instrument="XAU/USD", timeframe="1h",
        )
        trades = portfolio.close_all_positions(candle)
        assert len(trades) == 3
        assert portfolio.position_count == 0

    def test_portfolio_heat(self):
        acc = AccountSimulator(AccountConfig(initial_balance=10000.0))
        portfolio = PortfolioSimulator(account=acc)
        pos = self._make_position()
        portfolio.open_position(pos)
        heat = portfolio.get_portfolio_heat()
        assert heat >= 0

    def test_summary(self):
        acc = AccountSimulator()
        portfolio = PortfolioSimulator(account=acc)
        s = portfolio.summary()
        assert "open_positions" in s
        assert "total_trades" in s


# ===========================================================================
# Performance Analytics Tests
# ===========================================================================

from app.modules.backtesting.performance_analytics import PerformanceAnalytics


class TestPerformanceAnalytics:
    def test_compute_all(self):
        trades = _make_trades()
        ec = EquityCurve()
        analytics = PerformanceAnalytics(
            trades=trades,
            equity_curve=ec,
            initial_balance=10000.0,
            final_balance=10133.0,
        )
        metrics = analytics.compute_all()
        assert metrics.trade_stats.total_trades == 4
        assert metrics.trade_stats.winning_trades == 3
        assert metrics.trade_stats.losing_trades == 1
        assert metrics.trade_stats.win_rate == 0.75
        assert metrics.net_profit == 133.0

    def test_empty_trades(self):
        analytics = PerformanceAnalytics(
            trades=[],
            equity_curve=EquityCurve(),
            initial_balance=10000.0,
            final_balance=10000.0,
        )
        metrics = analytics.compute_all()
        assert metrics.trade_stats.total_trades == 0
        assert metrics.net_profit == 0.0

    def test_profit_factor(self):
        trades = _make_trades()
        analytics = PerformanceAnalytics(
            trades=trades,
            equity_curve=EquityCurve(),
            initial_balance=10000.0,
            final_balance=10133.0,
        )
        metrics = analytics.compute_all()
        # Profit factor = gross_wins / gross_losses
        assert metrics.trade_stats.profit_factor > 1.0

    def test_cost_analysis(self):
        trades = _make_trades()
        analytics = PerformanceAnalytics(
            trades=trades,
            equity_curve=EquityCurve(),
            initial_balance=10000.0,
            final_balance=10133.0,
        )
        metrics = analytics.compute_all()
        assert metrics.cost_analysis.total_costs > 0
        assert metrics.cost_analysis.total_slippage_cost > 0
        assert metrics.cost_analysis.total_spread_cost > 0

    def test_risk_metrics(self):
        trades = _make_trades()
        ec = EquityCurve()
        # Add some equity snapshots using the helper
        for i in range(5):
            snap = _make_snapshot(
                datetime(2024, 1, 1, i, tzinfo=timezone.utc),
                balance=10000 + i * 30,
                peak=10000 + i * 30,
            )
            ec.append(snap)
        analytics = PerformanceAnalytics(
            trades=trades,
            equity_curve=ec,
            initial_balance=10000.0,
            final_balance=10133.0,
        )
        metrics = analytics.compute_all()
        assert isinstance(metrics.risk_metrics.sharpe_ratio, float)
        assert isinstance(metrics.risk_metrics.max_drawdown_pct, float)


# ===========================================================================
# Robustness Tests
# ===========================================================================

from app.modules.backtesting.robustness import RobustnessTester


class TestRobustnessTester:
    def test_monte_carlo(self):
        trades = _make_trades()
        tester = RobustnessTester(trades=trades, random_seed=42)
        result = tester.monte_carlo(MonteCarloConfig(num_simulations=100, random_seed=42))
        assert result.method == RobustnessMethod.MONTE_CARLO
        assert result.num_simulations == 100
        assert len(result.simulations) == 100
        assert result.stability_score >= 0.0

    def test_bootstrap(self):
        trades = _make_trades()
        tester = RobustnessTester(trades=trades, random_seed=42)
        # num_samples must be >= 100 per model validation
        result = tester.bootstrap(BootstrapConfig(num_samples=100, random_seed=42))
        assert result.method == RobustnessMethod.BOOTSTRAP
        assert result.num_simulations == 100

    def test_empty_trades(self):
        tester = RobustnessTester(trades=[])
        result = tester.monte_carlo()
        assert result.num_simulations == 0
        assert len(result.warnings) > 0


# ===========================================================================
# Walk-Forward Tests
# ===========================================================================

from app.modules.backtesting.walk_forward import WalkForwardEvaluator


class TestWalkForwardEvaluator:
    def test_rolling_folds(self):
        candles = _make_candles(200)
        evaluator = WalkForwardEvaluator()
        config = WalkForwardConfig(
            method=WalkForwardMethod.ROLLING,
            train_window_candles=100,
            test_window_candles=20,
            step_size_candles=20,
            min_folds=2,
        )
        folds = evaluator.generate_folds(candles, config)
        assert len(folds) > 0
        assert folds[0].train_candle_count == 100
        assert folds[0].test_candle_count == 20

    def test_anchored_folds(self):
        candles = _make_candles(200)
        evaluator = WalkForwardEvaluator()
        config = WalkForwardConfig(
            method=WalkForwardMethod.ANCHORED,
            train_window_candles=100,
            test_window_candles=20,
            step_size_candles=20,
            min_folds=2,
        )
        folds = evaluator.generate_folds(candles, config)
        assert len(folds) > 0
        # Anchored: train_start is always candle 0
        assert folds[0].train_start == candles[0].timestamp

    def test_expanding_folds(self):
        candles = _make_candles(200)
        evaluator = WalkForwardEvaluator()
        config = WalkForwardConfig(
            method=WalkForwardMethod.EXPANDING,
            train_window_candles=100,
            test_window_candles=20,
            step_size_candles=20,
            min_folds=2,
        )
        folds = evaluator.generate_folds(candles, config)
        assert len(folds) > 0

    def test_empty_candles(self):
        evaluator = WalkForwardEvaluator()
        config = WalkForwardConfig()
        folds = evaluator.generate_folds([], config)
        assert folds == []


# ===========================================================================
# Paper Trading Tests
# ===========================================================================

from app.modules.backtesting.paper_trading import PaperTradingService


class TestPaperTradingService:
    def test_start_session(self):
        service = PaperTradingService()
        session = service.start_session()
        assert session.status == "active"
        assert session.balance == 10000.0

    def test_list_sessions(self):
        service = PaperTradingService()
        service.start_session()
        service.start_session()
        assert len(service.list_sessions()) == 2

    def test_stop_session(self):
        service = PaperTradingService()
        session = service.start_session()
        result = service.stop_session(session.session_id)
        assert result is not None
        assert result.status == "stopped"

    def test_record_trade(self):
        service = PaperTradingService()
        session = service.start_session()
        trade = ClosedTrade(
            instrument="XAU/USD", side=OrderSide.BUY,
            entry_price=2650.0, exit_price=2660.0, lots=0.1,
            entry_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            exit_time=datetime(2024, 1, 1, 2, tzinfo=timezone.utc),
            close_reason=CloseReason.TAKE_PROFIT,
            gross_pnl=100.0, net_pnl=95.0, total_costs=5.0,
        )
        updated = service.record_trade(session.session_id, trade)
        assert updated is not None
        assert len(updated.trades) == 1
        assert updated.balance == 10095.0

    def test_summary(self):
        service = PaperTradingService()
        service.start_session()
        s = service.summary()
        assert s["total_sessions"] == 1


# ===========================================================================
# Versioning Tests
# ===========================================================================

from app.modules.backtesting.versioning import ResultVersionManager


class TestResultVersionManager:
    def test_create_metadata(self):
        mgr = ResultVersionManager()
        meta = mgr.create_metadata(
            config={"instrument": "XAU/USD", "timeframe": "1h"},
            description="Test run",
        )
        assert meta.config_hash != ""
        assert meta.description == "Test run"

    def test_store_and_retrieve(self):
        mgr = ResultVersionManager()
        result = BacktestResult(
            config=BacktestConfig(),
            status=BacktestStatus.COMPLETED,
        )
        run_id = mgr.store_result(result)
        assert run_id == result.run_id
        retrieved = mgr.get_result(run_id)
        assert retrieved is not None

    def test_list_runs(self):
        mgr = ResultVersionManager()
        for _ in range(3):
            result = BacktestResult(config=BacktestConfig(), status=BacktestStatus.COMPLETED)
            mgr.store_result(result)
        runs = mgr.list_runs()
        assert len(runs) == 3

    def test_delete_result(self):
        mgr = ResultVersionManager()
        result = BacktestResult(config=BacktestConfig(), status=BacktestStatus.COMPLETED)
        mgr.store_result(result)
        deleted = mgr.delete_result(result.run_id)
        assert deleted is True
        assert mgr.get_result(result.run_id) is None

    def test_compare_runs(self):
        mgr = ResultVersionManager()
        from app.modules.backtesting.models import TradeStatistics, RiskMetrics, CostAnalysis

        result_a = BacktestResult(
            config=BacktestConfig(),
            status=BacktestStatus.COMPLETED,
            metrics=PerformanceMetrics(
                total_return=0.05, total_return_pct=5.0, annualized_return=0.05,
                net_profit=500.0, gross_profit=800.0, gross_loss=300.0,
                initial_balance=10000.0, final_balance=10500.0,
                peak_equity=10500.0, test_duration_seconds=86400.0,
                candles_processed=100,
                trade_stats=TradeStatistics(
                    total_trades=10, winning_trades=6, losing_trades=4,
                    win_rate=0.6, loss_rate=0.4, profit_factor=2.67, expectancy=50.0,
                    payoff_ratio=2.0, kelly_criterion=0.2,
                    consecutive_wins=0, consecutive_losses=0,
                    max_consecutive_wins=3, max_consecutive_losses=2,
                    recovery_factor=1.0,
                ),
                risk_metrics=RiskMetrics(
                    sharpe_ratio=1.5, sortino_ratio=2.0, calmar_ratio=1.0,
                    max_drawdown_pct=5.0, max_drawdown_amount=500.0,
                    max_drawdown_duration_seconds=3600.0, max_drawdown_recovery_seconds=7200.0,
                    volatility_annual=0.15, downside_deviation=0.1,
                    tail_ratio=1.5, value_at_risk_95=0.02, conditional_var_95=0.03,
                ),
                cost_analysis=CostAnalysis(
                    total_slippage_cost=50.0, total_spread_cost=80.0,
                    total_commission=0.0, total_costs=130.0,
                    avg_cost_per_trade=13.0, cost_as_pct_of_pnl=16.25,
                    slippage_bps=0.5,
                ),
            ),
        )
        result_b = BacktestResult(
            config=BacktestConfig(),
            status=BacktestStatus.COMPLETED,
            metrics=PerformanceMetrics(
                total_return=0.03, total_return_pct=3.0, annualized_return=0.03,
                net_profit=300.0, gross_profit=600.0, gross_loss=300.0,
                initial_balance=10000.0, final_balance=10300.0,
                peak_equity=10300.0, test_duration_seconds=86400.0,
                candles_processed=100,
                trade_stats=TradeStatistics(
                    total_trades=10, winning_trades=5, losing_trades=5,
                    win_rate=0.5, loss_rate=0.5, profit_factor=2.0, expectancy=30.0,
                    payoff_ratio=2.0, kelly_criterion=0.1,
                    consecutive_wins=0, consecutive_losses=0,
                    max_consecutive_wins=2, max_consecutive_losses=2,
                    recovery_factor=0.6,
                ),
                risk_metrics=RiskMetrics(
                    sharpe_ratio=1.0, sortino_ratio=1.5, calmar_ratio=0.6,
                    max_drawdown_pct=5.0, max_drawdown_amount=500.0,
                    max_drawdown_duration_seconds=3600.0, max_drawdown_recovery_seconds=7200.0,
                    volatility_annual=0.12, downside_deviation=0.08,
                    tail_ratio=1.2, value_at_risk_95=0.015, conditional_var_95=0.025,
                ),
                cost_analysis=CostAnalysis(
                    total_slippage_cost=40.0, total_spread_cost=70.0,
                    total_commission=0.0, total_costs=110.0,
                    avg_cost_per_trade=11.0, cost_as_pct_of_pnl=22.0,
                    slippage_bps=0.4,
                ),
            ),
        )

        mgr.store_result(result_a)
        mgr.store_result(result_b)

        comparison = mgr.compare_runs(result_a.run_id, result_b.run_id)
        assert comparison is not None
        assert "trades" in comparison["comparison"]
        assert "win_rate" in comparison["comparison"]


# ===========================================================================
# Service Tests
# ===========================================================================

from app.modules.backtesting.service import BacktestingService


class TestBacktestingService:
    def test_health_check(self):
        service = BacktestingService()
        health = asyncio.run(service.health_check())
        assert health["status"] == "healthy"
        assert health["module"] == "backtesting"

    def test_capabilities(self):
        service = BacktestingService()
        caps = asyncio.run(service.get_capabilities())
        assert caps["module"] == "backtesting"
        assert "historical_backtest" in caps["features"]
        assert "walk_forward" in caps["features"]
        assert "paper_trading" in caps["features"]

    def test_list_runs_empty(self):
        service = BacktestingService()
        runs = service.list_runs()
        assert runs == []

    def test_paper_trading_start(self):
        service = BacktestingService()
        result = service.start_paper_trading()
        assert "session_id" in result
        assert result["status"] == "active"


# ===========================================================================
# API Tests
# ===========================================================================

from fastapi.testclient import TestClient
from app.main import application


@pytest.fixture
def client():
    return TestClient(application)


class TestBacktestingAPI:
    def test_health_endpoint(self, client):
        response = client.get("/api/v1/backtesting/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["module"] == "backtesting"

    def test_capabilities_endpoint(self, client):
        response = client.get("/api/v1/backtesting/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert data["module"] == "backtesting"
        assert "features" in data

    def test_list_runs_endpoint(self, client):
        response = client.get("/api/v1/backtesting/runs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_paper_trading_start_endpoint(self, client):
        response = client.post("/api/v1/backtesting/paper-trading/start")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "active"

    def test_list_paper_sessions_endpoint(self, client):
        response = client.get("/api/v1/backtesting/paper-trading/sessions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
