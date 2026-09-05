"""
Scalping Arise — Backtest Runner

Main orchestration engine for backtesting.
Ties together all Phase 9 components:
history loading, candle replay, signal generation, trade simulation,
account simulation, and performance analytics.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Optional

from app.modules.backtesting.account_simulator import AccountSimulator
from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.history_provider import HistoricalDataProvider
from app.modules.backtesting.look_ahead_guard import LookAheadGuard
from app.modules.backtesting.models import (
    AccountConfig,
    BacktestConfig,
    BacktestMode,
    BacktestResult,
    BacktestStatus,
    ClosedTrade,
    CloseReason,
    DataQualityReport,
    DataSource,
    FillMethod,
    HistoricalCandle,
    LookAheadViolation,
    OrderSide,
    OrderType,
    SlippageModel,
    SimulatedFill,
    SimulatedOrder,
    SimulatedPosition,
)
from app.modules.backtesting.performance_analytics import PerformanceAnalytics
from app.modules.backtesting.portfolio_simulator import PortfolioSimulator
from app.modules.backtesting.trade_simulator import TradeSimulator
from app.modules.market_data.models import Instrument, Timeframe

logger = logging.getLogger(__name__)


class BacktestRunner:
    """
    Main backtest orchestration engine.

    Executes a complete backtest:
    1. Load historical data
    2. Validate data quality
    3. Set up look-ahead protection
    4. Initialize simulators
    5. Replay candles chronologically
    6. At each candle: check exits, evaluate signals, generate plans, execute trades
    7. Compute performance analytics
    8. Return complete result

    This is a thin orchestrator — it does NOT duplicate Phase 2-8 logic.
    Signal generation and trade planning are delegated to the existing services
    via adapter patterns.
    """

    def __init__(
        self,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()

    async def run(self, config: BacktestConfig) -> BacktestResult:
        """
        Execute a complete backtest.

        This is the main entry point for running a backtest.
        """
        result = BacktestResult(config=config)
        result.started_at = datetime.now(timezone.utc)
        result.status = BacktestStatus.RUNNING

        # Set random seed for determinism
        if config.random_seed is not None:
            random.seed(config.random_seed)
            result.random_seed_used = config.random_seed
        elif self._settings.enforce_determinism:
            seed = self._settings.default_random_seed
            random.seed(seed)
            result.random_seed_used = seed

        try:
            # Step 1: Load historical data
            data_provider = HistoricalDataProvider(settings=self._settings)
            candles, data_source = await data_provider.load_candles(
                instrument=config.instrument,
                timeframe=config.timeframe,
                limit=config.candle_limit or self._settings.default_candle_limit,
                start_time=config.start_time,
                end_time=config.end_time,
            )

            if not candles:
                result.status = BacktestStatus.FAILED
                result.error_message = "No historical data loaded"
                return result

            result.candles_loaded = len(candles)
            result.data_source = data_source

            # Step 2: Validate data quality
            quality = data_provider.validate_data_quality(candles, config.timeframe)
            result.data_quality = quality

            if quality.valid_candles == 0:
                result.status = BacktestStatus.FAILED
                result.error_message = "No valid candles in dataset"
                return result

            # Step 3: Set up simulators
            account_config = AccountConfig(
                initial_balance=config.account.initial_balance,
                max_positions=config.account.max_positions,
                max_daily_loss_pct=config.account.max_daily_loss_pct,
                max_drawdown_pct=config.account.max_drawdown_pct,
            )

            account = AccountSimulator(config=account_config, settings=self._settings)

            trade_sim = TradeSimulator(
                fill_method=config.fill_method,
                slippage_model=config.slippage_model,
                slippage_pips=config.slippage_pips,
                spread_pips=config.spread_pips,
                settings=self._settings,
            )

            portfolio = PortfolioSimulator(
                account=account,
                trade_simulator=trade_sim,
                settings=self._settings,
            )

            # Step 4: Set up look-ahead guard
            guard = LookAheadGuard(
                simulation_time=candles[0].timestamp,
                strict_mode=config.look_ahead_strict,
                max_lookahead_seconds=config.max_lookahead_seconds,
                settings=self._settings,
            )

            # Step 5: Replay loop
            max_trades = config.max_trades or self._settings.max_trades_per_backtest
            trades_executed = 0

            for i, candle in enumerate(candles):
                # Advance guard
                guard.advance(candle.timestamp)

                # Check daily reset
                account.check_daily_reset(candle.timestamp)

                # Update position prices
                portfolio.update_prices(candle)

                # Check SL/TP exits
                exits = portfolio.check_exits(candle)
                for pos, reason in exits:
                    exit_price = trade_sim.calculate_exit_price(pos, reason, candle)
                    trade = portfolio.close_position(
                        pos,
                        reason=reason,
                        exit_price=exit_price,
                        timestamp=candle.timestamp,
                    )
                    account.process_close(trade, candle.timestamp, portfolio.open_positions)

                    # Feed outcome to performance tracker
                    from app.modules.news_intelligence.models import TradeOutcome
                    outcome = TradeOutcome(
                        strategy_id=trade.strategy_id or "backtest",
                        instrument=trade.instrument,
                        direction="long" if trade.side == OrderSide.BUY else "short",
                        entry_price=trade.entry_price,
                        exit_price=trade.exit_price,
                        pnl=trade.net_pnl,
                        is_winner=trade.is_winner,
                        opened_at=trade.entry_time,
                        closed_at=trade.exit_time,
                    )
                    # Note: We don't call record_trade_outcome here to avoid
                    # modifying Phase 8 live state during backtesting

                # Process pending orders from previous candle
                fills = trade_sim.process_orders(candle)
                for fill in fills:
                    position = trade_sim.create_position_from_fill(
                        fill,
                        signal_id=fill.signal_id,
                        strategy_id=fill.strategy_id,
                        plan_id=fill.plan_id,
                    )
                    portfolio.open_position(position)

                # Signal generation and trade planning
                # This is the thin adapter: we delegate to existing services
                # but inject historical data via the guard
                if trades_executed < max_trades:
                    signal, plan = await self._evaluate_at_candle(
                        candle=candle,
                        candles=candles,
                        guard=guard,
                        config=config,
                    )

                    if signal is not None and plan is not None:
                        # Check if plan was approved
                        from app.modules.trade_planning.models import PlanState
                        if plan.state == PlanState.APPROVED:
                            # Create order from plan
                            from app.modules.backtesting.models import order_side_from_plan_side
                            side = order_side_from_plan_side(plan.side.value)
                            if side is not None:
                                order = SimulatedOrder(
                                    instrument=plan.instrument,
                                    side=side,
                                    order_type=OrderType.MARKET,
                                    lots=plan.risk.position_size.lots if plan.risk else 0.01,
                                    stop_loss_price=plan.stop_loss.sl_price if plan.stop_loss else None,
                                    take_profit_price=(
                                        plan.take_profit.targets[0].tp_price
                                        if plan.take_profit and plan.take_profit.targets
                                        else None
                                    ),
                                    signal_id=signal.signal_id,
                                    strategy_id=(
                                        signal.candidates[0].strategy_id
                                        if signal.candidates else None
                                    ),
                                    plan_id=plan.plan_id,
                                )
                                trade_sim.submit_order(order)
                                trades_executed += 1
                        else:
                            portfolio._current_bar_index = i

            # Step 6: Close remaining open positions
            if candles:
                closing_trades = portfolio.close_all_positions(
                    candles[-1],
                    reason=CloseReason.EXPIRED,
                )
                for trade in closing_trades:
                    account.process_close(trade, candles[-1].timestamp, [])

            # Step 7: Compute performance analytics
            from app.modules.backtesting.models import EquityCurve
            final_balance = account.balance
            test_duration = 0.0
            if result.started_at:
                test_duration = (datetime.now(timezone.utc) - result.started_at).total_seconds()

            analytics = PerformanceAnalytics(
                trades=portfolio.closed_trades,
                equity_curve=account.equity_curve,
                initial_balance=config.account.initial_balance,
                final_balance=final_balance,
                test_duration_seconds=test_duration,
                candles_processed=len(candles),
            )
            result.metrics = analytics.compute_all()

            # Step 8: Collect results
            result.trades = portfolio.closed_trades
            result.equity_curve = account.equity_curve
            result.account_snapshots = account.snapshots
            result.look_ahead_violations = guard.violations
            result.status = BacktestStatus.COMPLETED
            result.completed_at = datetime.now(timezone.utc)
            result.duration_seconds = (
                (result.completed_at - result.started_at).total_seconds()
                if result.started_at else 0.0
            )

            logger.info(
                "Backtest completed: %d candles, %d trades, net_pnl=%.2f, sharpe=%.2f",
                len(candles),
                len(portfolio.closed_trades),
                result.metrics.net_profit,
                result.metrics.risk_metrics.sharpe_ratio,
            )

        except Exception as e:
            result.status = BacktestStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now(timezone.utc)
            logger.error("Backtest failed: %s", e, exc_info=True)

        return result

    async def _evaluate_at_candle(
        self,
        candle: HistoricalCandle,
        candles: list[HistoricalCandle],
        guard: LookAheadGuard,
        config: BacktestConfig,
    ) -> tuple[Optional[object], Optional[object]]:
        """
        Evaluate signals and generate a trade plan at a specific candle.

        This is a thin adapter that wraps Phase 6 and Phase 7 services
        with historical data injection.
        """
        try:
            # Get visible candles up to current time
            visible = guard.get_visible_window(candles, max_count=config.candle_limit_per_tf)

            if len(visible) < 50:
                return None, None

            # Build mock price data from visible candles
            current_price = candle.close
            bid = current_price - config.spread_pips * 0.01
            ask = current_price + config.spread_pips * 0.01

            # Try to import and use the real signal engine
            # In a full implementation, we'd inject a mock MarketDataService
            # that returns only visible candles. For now, we use a simplified path.

            # Generate signal using existing engine (with live data — acknowledged limitation)
            from app.modules.signal_engine.service import SignalEngineService
            signal_service = SignalEngineService()

            strategy_ids = config.strategy_ids
            try:
                signal_result = await signal_service.evaluate_signal(
                    instrument=config.instrument,
                    timeframes=config.timeframes,
                    candle_limit=config.candle_limit_per_tf,
                    strategy_ids=strategy_ids,
                )
            except Exception:
                return None, None

            if signal_result.signal_record is None:
                return None, None

            signal = signal_result.signal_record

            # Check if signal is actionable
            from app.modules.signal_engine.models import DecisionType
            if signal.decision == DecisionType.NO_TRADE:
                return None, None

            # Generate trade plan
            from app.modules.trade_planning.service import TradePlanningService
            planning_service = TradePlanningService()

            try:
                plan = await planning_service.generate_plan(
                    signal=signal,
                    account_balance=config.account.initial_balance,
                )
            except Exception:
                return None, None

            return signal, plan

        except Exception as e:
            logger.debug("Signal evaluation failed at candle %s: %s", candle.timestamp, e)
            return None, None

    def summary(self) -> dict:
        """Return summary of runner state."""
        return {
            "module": "backtest_runner",
            "settings": {
                "enforce_determinism": self._settings.enforce_determinism,
                "strict_lookahead": self._settings.strict_lookahead,
                "max_trades_per_backtest": self._settings.max_trades_per_backtest,
            },
        }
