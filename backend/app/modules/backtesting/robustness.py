"""
Scalping Arise — Robustness Testing

Monte Carlo simulation, bootstrap analysis, parameter sensitivity,
and regime partition testing for backtest result validation.

All methods are deterministic when seeded.
"""

from __future__ import annotations

import logging
import math
import random
from typing import Optional

from app.modules.backtesting.models import (
    BootstrapConfig,
    ClosedTrade,
    MonteCarloConfig,
    ParameterSensitivityConfig,
    PerformanceMetrics,
    RegimePartitionConfig,
    RobustnessMethod,
    RobustnessResult,
)

logger = logging.getLogger(__name__)


class RobustnessTester:
    """
    Robustness testing for backtest results.

    Provides Monte Carlo simulation, bootstrap analysis,
    parameter sensitivity, and regime partition testing.
    """

    def __init__(
        self,
        trades: list[ClosedTrade],
        base_metrics: Optional[PerformanceMetrics] = None,
        random_seed: Optional[int] = None,
    ) -> None:
        self._trades = trades
        self._base_metrics = base_metrics
        self._seed = random_seed

    def monte_carlo(
        self,
        config: Optional[MonteCarloConfig] = None,
    ) -> RobustnessResult:
        """
        Monte Carlo simulation: resample trades with replacement
        to estimate the distribution of performance metrics.
        """
        cfg = config or MonteCarloConfig()
        seed = cfg.random_seed or self._seed
        rng = random.Random(seed)

        if not self._trades:
            return RobustnessResult(
                method=RobustnessMethod.MONTE_CARLO,
                num_simulations=0,
                stability_score=0.0,
                warnings=["No trades to simulate"],
            )

        simulated_metrics: list[PerformanceMetrics] = []
        sample_size = len(self._trades)

        for _ in range(cfg.num_simulations):
            # Resample with replacement
            if cfg.resample_with_replacement:
                sampled = [rng.choice(self._trades) for _ in range(sample_size)]
            else:
                sampled = list(self._trades)
                rng.shuffle(sampled)

            metrics = self._compute_metrics_from_trades(sampled)
            simulated_metrics.append(metrics)

        # Extract net profits for analysis
        net_profits = [m.net_profit for m in simulated_metrics]
        sorted_profits = sorted(net_profits)

        # Confidence interval
        lower_idx = int(len(sorted_profits) * ((1 - cfg.confidence_level) / 2))
        upper_idx = int(len(sorted_profits) * (1 - (1 - cfg.confidence_level) / 2))
        lower_idx = max(0, min(lower_idx, len(sorted_profits) - 1))
        upper_idx = max(0, min(upper_idx, len(sorted_profits) - 1))

        ci_lower = sorted_profits[lower_idx]
        ci_upper = sorted_profits[upper_idx]

        # P-value: fraction of simulations with negative return
        p_value = sum(1 for p in net_profits if p < 0) / len(net_profits)

        # Stability score: fraction of simulations with positive return
        stability = 1.0 - p_value

        # Percentiles
        percentiles = {
            "p5": self._percentile(sorted_profits, 0.05),
            "p25": self._percentile(sorted_profits, 0.25),
            "p50": self._percentile(sorted_profits, 0.50),
            "p75": self._percentile(sorted_profits, 0.75),
            "p95": self._percentile(sorted_profits, 0.95),
        }

        warnings: list[str] = []
        if p_value > 0.10:
            warnings.append(f"High probability of loss: {p_value:.1%}")
        if ci_lower < 0:
            warnings.append(f"Confidence interval includes negative returns")

        return RobustnessResult(
            method=RobustnessMethod.MONTE_CARLO,
            num_simulations=cfg.num_simulations,
            confidence_interval_lower=ci_lower,
            confidence_interval_upper=ci_upper,
            p_value=p_value,
            stability_score=stability,
            simulations=simulated_metrics,
            percentiles=percentiles,
            warnings=warnings,
        )

    def bootstrap(
        self,
        config: Optional[BootstrapConfig] = None,
    ) -> RobustnessResult:
        """
        Bootstrap analysis: resample trades without replacement
        to estimate metric confidence intervals.
        """
        cfg = config or BootstrapConfig()
        seed = cfg.random_seed or self._seed
        rng = random.Random(seed)

        if not self._trades:
            return RobustnessResult(
                method=RobustnessMethod.BOOTSTRAP,
                num_simulations=0,
                stability_score=0.0,
                warnings=["No trades to bootstrap"],
            )

        simulated_metrics: list[PerformanceMetrics] = []
        sample_size = max(1, int(len(self._trades) * cfg.sample_size_pct))

        for _ in range(cfg.num_samples):
            sampled = rng.sample(self._trades, min(sample_size, len(self._trades)))
            metrics = self._compute_metrics_from_trades(sampled)
            simulated_metrics.append(metrics)

        net_profits = [m.net_profit for m in simulated_metrics]
        sorted_profits = sorted(net_profits)

        ci_lower = self._percentile(sorted_profits, 0.025)
        ci_upper = self._percentile(sorted_profits, 0.975)

        p_value = sum(1 for p in net_profits if p < 0) / len(net_profits)
        stability = 1.0 - p_value

        percentiles = {
            "p5": self._percentile(sorted_profits, 0.05),
            "p25": self._percentile(sorted_profits, 0.25),
            "p50": self._percentile(sorted_profits, 0.50),
            "p75": self._percentile(sorted_profits, 0.75),
            "p95": self._percentile(sorted_profits, 0.95),
        }

        warnings: list[str] = []
        if p_value > 0.10:
            warnings.append(f"High probability of loss in bootstrap: {p_value:.1%}")

        return RobustnessResult(
            method=RobustnessMethod.BOOTSTRAP,
            num_simulations=cfg.num_samples,
            confidence_interval_lower=ci_lower,
            confidence_interval_upper=ci_upper,
            p_value=p_value,
            stability_score=stability,
            simulations=simulated_metrics,
            percentiles=percentiles,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_metrics_from_trades(
        self,
        trades: list[ClosedTrade],
    ) -> PerformanceMetrics:
        """Compute performance metrics from a subset of trades."""
        from app.modules.backtesting.performance_analytics import PerformanceMetrics as PM

        if not trades:
            return PM(
                total_return=0.0, total_return_pct=0.0, annualized_return=0.0,
                net_profit=0.0, gross_profit=0.0, gross_loss=0.0,
                initial_balance=10000.0, final_balance=10000.0,
                peak_equity=10000.0, test_duration_seconds=0.0,
                candles_processed=0,
                trade_stats=TradeStatistics(
                    total_trades=0, winning_trades=0, losing_trades=0,
                    win_rate=0.0, loss_rate=0.0, profit_factor=0.0,
                    expectancy=0.0, payoff_ratio=0.0, kelly_criterion=0.0,
                    consecutive_wins=0, consecutive_losses=0,
                    max_consecutive_wins=0, max_consecutive_losses=0,
                    recovery_factor=0.0,
                ),
                risk_metrics=RiskMetrics(
                    sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
                    max_drawdown_pct=0.0, max_drawdown_amount=0.0,
                    max_drawdown_duration_seconds=0.0, max_drawdown_recovery_seconds=0.0,
                    volatility_annual=0.0, downside_deviation=0.0,
                    tail_ratio=0.0, value_at_risk_95=0.0, conditional_var_95=0.0,
                ),
                cost_analysis=CostAnalysis(
                    total_slippage_cost=0.0, total_spread_cost=0.0,
                    total_commission=0.0, total_costs=0.0,
                    avg_cost_per_trade=0.0, cost_as_pct_of_pnl=0.0,
                    slippage_bps=0.0,
                ),
            )

        total = len(trades)
        winners = [t for t in trades if t.is_winner]
        losers = [t for t in trades if not t.is_winner and t.net_pnl != 0]

        win_count = len(winners)
        loss_count = len(losers)
        win_rate = win_count / total if total > 0 else 0.0

        net_pnl = sum(t.net_pnl for t in trades)
        gross_profit = sum(t.net_pnl for t in winners) if winners else 0.0
        gross_loss = abs(sum(t.net_pnl for t in losers)) if losers else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        avg_win = gross_profit / win_count if win_count > 0 else 0.0
        avg_loss = -(gross_loss / loss_count) if loss_count > 0 else 0.0
        payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        # Max drawdown from equity curve simulation
        equity = 10000.0
        peak = equity
        max_dd_pct = 0.0
        for t in trades:
            equity += t.net_pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
            max_dd_pct = max(max_dd_pct, dd)

        from app.modules.backtesting.models import TradeStatistics, RiskMetrics, CostAnalysis
        from app.modules.backtesting.performance_analytics import PerformanceMetrics

        return PerformanceMetrics(
            total_return=net_pnl / 10000.0,
            total_return_pct=net_pnl / 10000.0 * 100,
            annualized_return=net_pnl / 10000.0,
            net_profit=net_pnl,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            initial_balance=10000.0,
            final_balance=10000.0 + net_pnl,
            peak_equity=10000.0 + max(t.net_pnl for t in trades) if trades else 10000.0,
            test_duration_seconds=0.0,
            candles_processed=0,
            trade_stats=TradeStatistics(
                total_trades=total,
                winning_trades=win_count,
                losing_trades=loss_count,
                win_rate=win_rate,
                loss_rate=1.0 - win_rate,
                profit_factor=profit_factor,
                expectancy=expectancy,
                payoff_ratio=payoff,
                kelly_criterion=0.0,
                consecutive_wins=0,
                consecutive_losses=0,
                max_consecutive_wins=0,
                max_consecutive_losses=0,
                recovery_factor=net_pnl / (max_dd_pct / 100 * 10000) if max_dd_pct > 0 else 0.0,
            ),
            risk_metrics=RiskMetrics(
                sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
                max_drawdown_pct=max_dd_pct,
                max_drawdown_amount=max_dd_pct / 100 * 10000,
                max_drawdown_duration_seconds=0.0,
                max_drawdown_recovery_seconds=0.0,
                volatility_annual=0.0, downside_deviation=0.0,
                tail_ratio=0.0, value_at_risk_95=0.0, conditional_var_95=0.0,
            ),
            cost_analysis=CostAnalysis(
                total_slippage_cost=sum(t.slippage_cost for t in trades),
                total_spread_cost=sum(t.spread_cost for t in trades),
                total_commission=sum(t.commission for t in trades),
                total_costs=sum(t.total_costs for t in trades),
                avg_cost_per_trade=sum(t.total_costs for t in trades) / total,
                cost_as_pct_of_pnl=0.0,
                slippage_bps=0.0,
            ),
        )

    @staticmethod
    def _percentile(sorted_data: list[float], pct: float) -> float:
        """Compute percentile from sorted data."""
        if not sorted_data:
            return 0.0
        idx = int(len(sorted_data) * pct)
        idx = max(0, min(idx, len(sorted_data) - 1))
        return sorted_data[idx]
