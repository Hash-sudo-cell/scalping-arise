"""
Scalping Arise — Walk-Forward Evaluation

Implements walk-forward optimization and testing for strategy validation.
Supports anchored, rolling, and expanding window methods.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.models import (
    BacktestConfig,
    BacktestResult,
    HistoricalCandle,
    WalkForwardConfig,
    WalkForwardFold,
    WalkForwardMethod,
    WalkForwardResult,
)

logger = logging.getLogger(__name__)


class WalkForwardEvaluator:
    """
    Walk-forward evaluation engine.

    Splits historical data into train/test folds, runs backtests
    on each fold, and aggregates out-of-sample results.
    """

    def __init__(
        self,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()

    def generate_folds(
        self,
        candles: list[HistoricalCandle],
        config: WalkForwardConfig,
    ) -> list[WalkForwardFold]:
        """
        Generate walk-forward folds from candle data.

        Returns a list of folds with train/test time boundaries.
        """
        if not candles:
            return []

        sorted_candles = sorted(candles, key=lambda c: c.timestamp)
        total = len(sorted_candles)

        if config.method == WalkForwardMethod.ANCHORED:
            return self._generate_anchored_folds(sorted_candles, config)
        elif config.method == WalkForwardMethod.ROLLING:
            return self._generate_rolling_folds(sorted_candles, config)
        elif config.method == WalkForwardMethod.EXPANDING:
            return self._generate_expanding_folds(sorted_candles, config)
        else:
            return self._generate_rolling_folds(sorted_candles, config)

    def _generate_anchored_folds(
        self,
        candles: list[HistoricalCandle],
        config: WalkForwardConfig,
    ) -> list[WalkForwardFold]:
        """Anchored walk-forward: train window always starts from the beginning."""
        folds: list[WalkForwardFold] = []
        total = len(candles)
        train_size = config.train_window_candles
        test_size = config.test_window_candles
        step = config.step_size_candles

        fold_id = 0
        test_start_idx = train_size

        while test_start_idx + test_size <= total and fold_id < config.max_folds:
            test_end_idx = min(test_start_idx + test_size, total)

            fold = WalkForwardFold(
                fold_id=fold_id,
                train_start=candles[0].timestamp,
                train_end=candles[test_start_idx - 1].timestamp,
                test_start=candles[test_start_idx].timestamp,
                test_end=candles[test_end_idx - 1].timestamp,
                train_candle_count=test_start_idx,
                test_candle_count=test_end_idx - test_start_idx,
            )
            folds.append(fold)

            test_start_idx += step
            fold_id += 1

        if len(folds) < config.min_folds:
            logger.warning(
                "Only %d folds generated (minimum: %d). "
                "Try reducing train_window or test_window.",
                len(folds),
                config.min_folds,
            )

        return folds

    def _generate_rolling_folds(
        self,
        candles: list[HistoricalCandle],
        config: WalkForwardConfig,
    ) -> list[WalkForwardFold]:
        """Rolling walk-forward: fixed-size train window slides forward."""
        folds: list[WalkForwardFold] = []
        total = len(candles)
        train_size = config.train_window_candles
        test_size = config.test_window_candles
        step = config.step_size_candles

        fold_id = 0
        train_start_idx = 0

        while train_start_idx + train_size + test_size <= total and fold_id < config.max_folds:
            train_end_idx = train_start_idx + train_size
            test_end_idx = min(train_end_idx + test_size, total)

            fold = WalkForwardFold(
                fold_id=fold_id,
                train_start=candles[train_start_idx].timestamp,
                train_end=candles[train_end_idx - 1].timestamp,
                test_start=candles[train_end_idx].timestamp,
                test_end=candles[test_end_idx - 1].timestamp,
                train_candle_count=train_size,
                test_candle_count=test_end_idx - train_end_idx,
            )
            folds.append(fold)

            train_start_idx += step
            fold_id += 1

        return folds

    def _generate_expanding_folds(
        self,
        candles: list[HistoricalCandle],
        config: WalkForwardConfig,
    ) -> list[WalkForwardFold]:
        """Expanding walk-forward: train window grows with each fold."""
        folds: list[WalkForwardFold] = []
        total = len(candles)
        initial_train = config.train_window_candles
        test_size = config.test_window_candles
        step = config.step_size_candles

        fold_id = 0
        train_end_idx = initial_train

        while train_end_idx + test_size <= total and fold_id < config.max_folds:
            test_end_idx = min(train_end_idx + test_size, total)

            fold = WalkForwardFold(
                fold_id=fold_id,
                train_start=candles[0].timestamp,
                train_end=candles[train_end_idx - 1].timestamp,
                test_start=candles[train_end_idx].timestamp,
                test_end=candles[test_end_idx - 1].timestamp,
                train_candle_count=train_end_idx,
                test_candle_count=test_end_idx - train_end_idx,
            )
            folds.append(fold)

            train_end_idx += step
            fold_id += 1

        return folds

    def aggregate_oos_results(
        self,
        folds: list[WalkForwardFold],
    ) -> WalkForwardResult:
        """
        Aggregate out-of-sample results across all completed folds.

        Computes consistency ratio and overfit score.
        """
        completed = [f for f in folds if f.status == "completed" and f.out_of_sample_metrics is not None]

        if not completed:
            return WalkForwardResult(
                config=WalkForwardConfig(),
                folds=folds,
                total_folds=len(folds),
                completed_folds=0,
                consistency_ratio=0.0,
                overfit_score=0.0,
                status="no_completed_folds",
            )

        # Consistency: fraction of OOS folds with positive return
        profitable = sum(
            1 for f in completed
            if f.out_of_sample_metrics is not None and f.out_of_sample_metrics.net_profit > 0
        )
        consistency = profitable / len(completed)

        # Overfit score: compare IS vs OOS performance
        is_sharpes = []
        oos_sharpes = []
        for f in completed:
            if f.in_sample_metrics and f.out_of_sample_metrics:
                is_sharpes.append(f.in_sample_metrics.risk_metrics.sharpe_ratio)
                oos_sharpes.append(f.out_of_sample_metrics.risk_metrics.sharpe_ratio)

        if is_sharpes and oos_sharpes:
            avg_is = sum(is_sharpes) / len(is_sharpes)
            avg_oos = sum(oos_sharpes) / len(oos_sharpes)
            # Overfit score: 1.0 = OOS matches IS, 0.0 = OOS is much worse
            if avg_is > 0:
                overfit = min(1.0, max(0.0, avg_oos / avg_is))
            else:
                overfit = 1.0 if avg_oos >= 0 else 0.0
        else:
            overfit = 0.5

        # Aggregate OOS metrics (average across folds)
        agg = self._average_metrics(completed)

        return WalkForwardResult(
            config=WalkForwardConfig(),
            folds=folds,
            aggregate_oos_metrics=agg,
            consistency_ratio=consistency,
            overfit_score=overfit,
            total_folds=len(folds),
            completed_folds=len(completed),
            status="completed",
        )

    def _average_metrics(
        self,
        folds: list[WalkForwardFold],
    ) -> Optional["PerformanceMetrics"]:
        """Average performance metrics across folds."""
        from app.modules.backtesting.performance_analytics import PerformanceMetrics
        from app.modules.backtesting.models import TradeStatistics, RiskMetrics, CostAnalysis

        metrics_list = [
            f.out_of_sample_metrics for f in folds
            if f.out_of_sample_metrics is not None
        ]
        if not metrics_list:
            return None

        n = len(metrics_list)

        return PerformanceMetrics(
            total_return=sum(m.total_return for m in metrics_list) / n,
            total_return_pct=sum(m.total_return_pct for m in metrics_list) / n,
            annualized_return=sum(m.annualized_return for m in metrics_list) / n,
            net_profit=sum(m.net_profit for m in metrics_list) / n,
            gross_profit=sum(m.gross_profit for m in metrics_list) / n,
            gross_loss=sum(m.gross_loss for m in metrics_list) / n,
            initial_balance=metrics_list[0].initial_balance,
            final_balance=metrics_list[-1].final_balance,
            peak_equity=max(m.peak_equity for m in metrics_list),
            test_duration_seconds=sum(m.test_duration_seconds for m in metrics_list),
            candles_processed=sum(m.candles_processed for m in metrics_list),
            trade_stats=TradeStatistics(
                total_trades=sum(m.trade_stats.total_trades for m in metrics_list) // n,
                winning_trades=sum(m.trade_stats.winning_trades for m in metrics_list) // n,
                losing_trades=sum(m.trade_stats.losing_trades for m in metrics_list) // n,
                win_rate=sum(m.trade_stats.win_rate for m in metrics_list) / n,
                loss_rate=sum(m.trade_stats.loss_rate for m in metrics_list) / n,
                profit_factor=sum(m.trade_stats.profit_factor for m in metrics_list) / n,
                expectancy=sum(m.trade_stats.expectancy for m in metrics_list) / n,
                payoff_ratio=sum(m.trade_stats.payoff_ratio for m in metrics_list) / n,
                kelly_criterion=0.0,
                consecutive_wins=0, consecutive_losses=0,
                max_consecutive_wins=0, max_consecutive_losses=0,
                recovery_factor=sum(m.trade_stats.recovery_factor for m in metrics_list) / n,
            ),
            risk_metrics=RiskMetrics(
                sharpe_ratio=sum(m.risk_metrics.sharpe_ratio for m in metrics_list) / n,
                sortino_ratio=sum(m.risk_metrics.sortino_ratio for m in metrics_list) / n,
                calmar_ratio=sum(m.risk_metrics.calmar_ratio for m in metrics_list) / n,
                max_drawdown_pct=max(m.risk_metrics.max_drawdown_pct for m in metrics_list),
                max_drawdown_amount=max(m.risk_metrics.max_drawdown_amount for m in metrics_list),
                max_drawdown_duration_seconds=max(m.risk_metrics.max_drawdown_duration_seconds for m in metrics_list),
                max_drawdown_recovery_seconds=max(m.risk_metrics.max_drawdown_recovery_seconds for m in metrics_list),
                volatility_annual=sum(m.risk_metrics.volatility_annual for m in metrics_list) / n,
                downside_deviation=sum(m.risk_metrics.downside_deviation for m in metrics_list) / n,
                tail_ratio=sum(m.risk_metrics.tail_ratio for m in metrics_list) / n,
                value_at_risk_95=sum(m.risk_metrics.value_at_risk_95 for m in metrics_list) / n,
                conditional_var_95=sum(m.risk_metrics.conditional_var_95 for m in metrics_list) / n,
            ),
            cost_analysis=CostAnalysis(
                total_slippage_cost=sum(m.cost_analysis.total_slippage_cost for m in metrics_list) / n,
                total_spread_cost=sum(m.cost_analysis.total_spread_cost for m in metrics_list) / n,
                total_commission=sum(m.cost_analysis.total_commission for m in metrics_list) / n,
                total_costs=sum(m.cost_analysis.total_costs for m in metrics_list) / n,
                avg_cost_per_trade=sum(m.cost_analysis.avg_cost_per_trade for m in metrics_list) / n,
                cost_as_pct_of_pnl=sum(m.cost_analysis.cost_as_pct_of_pnl for m in metrics_list) / n,
                slippage_bps=sum(m.cost_analysis.slippage_bps for m in metrics_list) / n,
            ),
        )
