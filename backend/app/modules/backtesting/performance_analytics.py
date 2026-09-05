"""
Scalping Arise — Performance Analytics

Computes comprehensive performance metrics from backtest results.
Includes return metrics, risk-adjusted ratios, trade statistics,
cost analysis, and drawdown analysis.

All calculations use only data available in the inputs — no external state.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Optional

from app.modules.backtesting.models import (
    AccountSnapshot,
    ClosedTrade,
    CostAnalysis,
    EquityCurve,
    OrderSide,
    PerformanceMetrics,
    RiskMetrics,
    TradeStatistics,
)

logger = logging.getLogger(__name__)

# Trading days per year for annualization
_TRADING_DAYS_PER_YEAR = 252
_HOURS_PER_YEAR = 8760


class PerformanceAnalytics:
    """
    Computes comprehensive performance metrics from backtest results.

    Pure function class — no side effects, no external state.
    All methods take data as input and return metrics.
    """

    def __init__(
        self,
        trades: list[ClosedTrade],
        equity_curve: EquityCurve,
        initial_balance: float,
        final_balance: float,
        test_duration_seconds: float = 0.0,
        candles_processed: int = 0,
        risk_free_rate: float = 0.0,
    ) -> None:
        self._trades = trades
        self._equity_curve = equity_curve
        self._initial_balance = initial_balance
        self._final_balance = final_balance
        self._test_duration_seconds = test_duration_seconds
        self._candles_processed = candles_processed
        self._risk_free_rate = risk_free_rate

    def compute_all(self) -> PerformanceMetrics:
        """Compute all performance metrics."""
        trade_stats = self._compute_trade_statistics()
        risk_metrics = self._compute_risk_metrics()
        cost_analysis = self._compute_cost_analysis()

        total_return = (self._final_balance - self._initial_balance) / self._initial_balance

        # Annualize returns
        if self._test_duration_seconds > 0:
            years = self._test_duration_seconds / (365.25 * 24 * 3600)
            annualized_return = ((1 + total_return) ** (1 / max(years, 0.001))) - 1
        else:
            annualized_return = 0.0

        gross_profit = sum(t.net_pnl for t in self._trades if t.net_pnl > 0)
        gross_loss = abs(sum(t.net_pnl for t in self._trades if t.net_pnl < 0))

        return PerformanceMetrics(
            total_return=total_return,
            total_return_pct=total_return * 100,
            annualized_return=annualized_return,
            monthly_avg_return=0.0,
            daily_avg_return=0.0,
            trade_stats=trade_stats,
            risk_metrics=risk_metrics,
            cost_analysis=cost_analysis,
            net_profit=self._final_balance - self._initial_balance,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            initial_balance=self._initial_balance,
            final_balance=self._final_balance,
            peak_equity=max(self._equity_curve.equity_values) if self._equity_curve.equity_values else self._initial_balance,
            test_duration_seconds=self._test_duration_seconds,
            candles_processed=self._candles_processed,
        )

    # ------------------------------------------------------------------
    # Trade Statistics
    # ------------------------------------------------------------------

    def _compute_trade_statistics(self) -> TradeStatistics:
        """Compute aggregate trade statistics."""
        if not self._trades:
            return self._empty_trade_stats()

        winners = [t for t in self._trades if t.is_winner]
        losers = [t for t in self._trades if not t.is_winner and t.net_pnl != 0]
        breakeven = [t for t in self._trades if t.net_pnl == 0]

        total = len(self._trades)
        win_count = len(winners)
        loss_count = len(losers)

        win_rate = win_count / total if total > 0 else 0.0
        loss_rate = loss_count / total if total > 0 else 0.0

        avg_win = sum(t.net_pnl for t in winners) / win_count if win_count > 0 else 0.0
        avg_loss = sum(t.net_pnl for t in losers) / loss_count if loss_count > 0 else 0.0

        largest_win = max((t.net_pnl for t in winners), default=0.0)
        largest_loss = min((t.net_pnl for t in losers), default=0.0)

        # Duration
        durations = [
            (t.exit_time - t.entry_time).total_seconds()
            for t in self._trades
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        # Holding bars
        holding_bars = [t.holding_bars for t in self._trades if t.holding_bars > 0]
        avg_holding_bars = sum(holding_bars) / len(holding_bars) if holding_bars else 0.0

        # Profit factor
        gross_wins = sum(t.net_pnl for t in winners)
        gross_losses = abs(sum(t.net_pnl for t in losers))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

        # Expectancy
        expectancy = (
            (win_rate * avg_win) + (loss_rate * avg_loss)
        ) if total > 0 else 0.0

        # Payoff ratio
        payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

        # Kelly criterion
        if payoff_ratio > 0:
            kelly = win_rate - ((1 - win_rate) / payoff_ratio)
        else:
            kelly = 0.0

        # Consecutive wins/losses
        max_consec_wins, max_consec_losses = self._consecutive_streaks()

        # Recovery factor
        max_dd = self._compute_max_drawdown()
        recovery_factor = (
            (self._final_balance - self._initial_balance) / max_dd
            if max_dd > 0 else 0.0
        )

        return TradeStatistics(
            total_trades=total,
            winning_trades=win_count,
            losing_trades=loss_count,
            breakeven_trades=len(breakeven),
            win_rate=win_rate,
            loss_rate=loss_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_trade_duration_seconds=avg_duration,
            avg_holding_bars=avg_holding_bars,
            profit_factor=profit_factor,
            expectancy=expectancy,
            kelly_criterion=kelly,
            consecutive_wins=0,
            consecutive_losses=0,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            payoff_ratio=payoff_ratio,
            recovery_factor=recovery_factor,
        )

    def _consecutive_streaks(self) -> tuple[int, int]:
        """Compute max consecutive wins and losses."""
        if not self._trades:
            return 0, 0

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for t in self._trades:
            if t.is_winner:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif t.net_pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_wins = 0
                current_losses = 0

        return max_wins, max_losses

    # ------------------------------------------------------------------
    # Risk Metrics
    # ------------------------------------------------------------------

    def _compute_risk_metrics(self) -> RiskMetrics:
        """Compute risk-adjusted performance metrics."""
        equity_values = self._equity_curve.equity_values
        if not equity_values or len(equity_values) < 2:
            return self._empty_risk_metrics()

        # Daily returns
        returns = self._compute_returns(equity_values)

        # Volatility
        volatility = self._compute_volatility(returns)

        # Sharpe ratio
        sharpe = self._compute_sharpe_ratio(returns, volatility)

        # Sortino ratio
        sortino = self._compute_sortino_ratio(returns)

        # Max drawdown
        max_dd_pct, max_dd_amount, max_dd_duration, max_dd_recovery = (
            self._compute_max_drawdown_detailed()
        )

        # Calmar ratio
        total_return = (self._final_balance - self._initial_balance) / self._initial_balance
        calmar = total_return / (max_dd_pct / 100) if max_dd_pct > 0 else 0.0

        # Downside deviation
        downside_dev = self._compute_downside_deviation(returns)

        # VaR and CVaR
        var_95 = self._compute_var(returns, 0.05)
        cvar_95 = self._compute_cvar(returns, 0.05)

        # Tail ratio
        tail_ratio = self._compute_tail_ratio(returns)

        return RiskMetrics(
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown_pct=max_dd_pct,
            max_drawdown_amount=max_dd_amount,
            max_drawdown_duration_seconds=max_dd_duration,
            max_drawdown_recovery_seconds=max_dd_recovery,
            volatility_annual=volatility,
            downside_deviation=downside_dev,
            tail_ratio=tail_ratio,
            value_at_risk_95=var_95,
            conditional_var_95=cvar_95,
        )

    def _compute_returns(self, equity_values: list[float]) -> list[float]:
        """Compute period-over-period returns."""
        returns: list[float] = []
        for i in range(1, len(equity_values)):
            if equity_values[i - 1] > 0:
                returns.append(
                    (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
                )
            else:
                returns.append(0.0)
        return returns

    def _compute_volatility(self, returns: list[float]) -> float:
        """Compute annualized volatility."""
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        daily_vol = math.sqrt(variance)
        return daily_vol * math.sqrt(_TRADING_DAYS_PER_YEAR)

    def _compute_sharpe_ratio(
        self,
        returns: list[float],
        volatility: float,
    ) -> float:
        """Compute annualized Sharpe ratio."""
        if not returns or volatility <= 0:
            return 0.0
        mean_return = sum(returns) / len(returns)
        excess_return = mean_return - (self._risk_free_rate / _TRADING_DAYS_PER_YEAR)
        daily_vol = volatility / math.sqrt(_TRADING_DAYS_PER_YEAR)
        return excess_return / daily_vol if daily_vol > 0 else 0.0

    def _compute_sortino_ratio(self, returns: list[float]) -> float:
        """Compute annualized Sortino ratio."""
        if not returns:
            return 0.0
        mean_return = sum(returns) / len(returns)
        excess_return = mean_return - (self._risk_free_rate / _TRADING_DAYS_PER_YEAR)

        downside_returns = [r for r in returns if r < 0]
        if not downside_returns:
            return float("inf") if excess_return > 0 else 0.0

        downside_var = sum(r ** 2 for r in downside_returns) / len(returns)
        downside_dev = math.sqrt(downside_var)

        annualized_downside = downside_dev * math.sqrt(_TRADING_DAYS_PER_YEAR)
        return excess_return / annualized_downside * math.sqrt(_TRADING_DAYS_PER_YEAR) if annualized_downside > 0 else 0.0

    def _compute_downside_deviation(self, returns: list[float]) -> float:
        """Compute annualized downside deviation."""
        if not returns:
            return 0.0
        downside_returns = [r for r in returns if r < 0]
        if not downside_returns:
            return 0.0
        downside_var = sum(r ** 2 for r in downside_returns) / len(returns)
        daily_downside = math.sqrt(downside_var)
        return daily_downside * math.sqrt(_TRADING_DAYS_PER_YEAR)

    def _compute_max_drawdown(self) -> float:
        """Compute maximum drawdown amount."""
        equity = self._equity_curve.equity_values
        if not equity:
            return 0.0
        peak = equity[0]
        max_dd = 0.0
        for e in equity:
            if e > peak:
                peak = e
            dd = peak - e
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _compute_max_drawdown_detailed(self) -> tuple[float, float, float, float]:
        """
        Compute max drawdown with duration and recovery.

        Returns (max_dd_pct, max_dd_amount, duration_seconds, recovery_seconds).
        """
        equity = self._equity_curve.equity_values
        timestamps = self._equity_curve.timestamps

        if not equity or len(equity) < 2:
            return 0.0, 0.0, 0.0, 0.0

        peak = equity[0]
        peak_idx = 0
        max_dd_pct = 0.0
        max_dd_amount = 0.0
        dd_start_idx = 0
        dd_end_idx = 0

        for i, e in enumerate(equity):
            if e > peak:
                peak = e
                peak_idx = i
            dd_amount = peak - e
            dd_pct = (dd_amount / peak * 100) if peak > 0 else 0.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
                max_dd_amount = dd_amount
                dd_start_idx = peak_idx
                dd_end_idx = i

        # Duration
        if dd_start_idx < len(timestamps) and dd_end_idx < len(timestamps):
            duration = (timestamps[dd_end_idx] - timestamps[dd_start_idx]).total_seconds()
        else:
            duration = 0.0

        # Recovery time (how long until equity exceeds previous peak)
        recovery = 0.0
        for i in range(dd_end_idx, len(equity)):
            if equity[i] >= peak:
                if dd_end_idx < len(timestamps) and i < len(timestamps):
                    recovery = (timestamps[i] - timestamps[dd_end_idx]).total_seconds()
                break

        return max_dd_pct, max_dd_amount, duration, recovery

    def _compute_var(self, returns: list[float], percentile: float) -> float:
        """Compute Value at Risk at given percentile."""
        if not returns:
            return 0.0
        sorted_returns = sorted(returns)
        idx = int(len(sorted_returns) * percentile)
        idx = max(0, min(idx, len(sorted_returns) - 1))
        return abs(sorted_returns[idx])

    def _compute_cvar(self, returns: list[float], percentile: float) -> float:
        """Compute Conditional VaR (Expected Shortfall) at given percentile."""
        if not returns:
            return 0.0
        sorted_returns = sorted(returns)
        cutoff = int(len(sorted_returns) * percentile)
        cutoff = max(1, cutoff)
        tail = sorted_returns[:cutoff]
        return abs(sum(tail) / len(tail)) if tail else 0.0

    def _compute_tail_ratio(self, returns: list[float]) -> float:
        """Compute tail ratio (95th percentile gain / 5th percentile loss)."""
        if len(returns) < 20:
            return 0.0
        sorted_returns = sorted(returns)
        p95_idx = int(len(sorted_returns) * 0.95)
        p05_idx = int(len(sorted_returns) * 0.05)
        p95 = sorted_returns[min(p95_idx, len(sorted_returns) - 1)]
        p05 = sorted_returns[max(p05_idx, 0)]
        if p05 >= 0:
            return 0.0
        return abs(p95 / p05)

    # ------------------------------------------------------------------
    # Cost Analysis
    # ------------------------------------------------------------------

    def _compute_cost_analysis(self) -> CostAnalysis:
        """Compute transaction cost analysis."""
        if not self._trades:
            return CostAnalysis(
                total_slippage_cost=0.0,
                total_spread_cost=0.0,
                total_commission=0.0,
                total_costs=0.0,
                avg_cost_per_trade=0.0,
                cost_as_pct_of_pnl=0.0,
                slippage_bps=0.0,
            )

        total_slippage = sum(t.slippage_cost for t in self._trades)
        total_spread = sum(t.spread_cost for t in self._trades)
        total_commission = sum(t.commission for t in self._trades)
        total_costs = total_slippage + total_spread + total_commission

        avg_cost = total_costs / len(self._trades)
        gross_pnl = sum(t.gross_pnl for t in self._trades)
        cost_pct = (total_costs / abs(gross_pnl) * 100) if gross_pnl != 0 else 0.0

        # Slippage in basis points (average)
        pip_values = []
        for t in self._trades:
            from app.modules.trade_planning.instrument_specs import get_spec
            spec = get_spec(t.instrument)
            pip_value = (spec.tick_size * 10) if spec else 0.01
            if pip_value > 0 and t.lots > 0:
                avg_slippage_pips = t.slippage_cost / (t.lots * (spec.pip_value_per_lot if spec else 1.0))
                pip_values.append(avg_slippage_pips)

        avg_slippage_bps = (sum(pip_values) / len(pip_values) * 10) if pip_values else 0.0

        return CostAnalysis(
            total_slippage_cost=total_slippage,
            total_spread_cost=total_spread,
            total_commission=total_commission,
            total_costs=total_costs,
            avg_cost_per_trade=avg_cost,
            cost_as_pct_of_pnl=cost_pct,
            slippage_bps=avg_slippage_bps,
        )

    # ------------------------------------------------------------------
    # Empty defaults
    # ------------------------------------------------------------------

    def _empty_trade_stats(self) -> TradeStatistics:
        return TradeStatistics(
            total_trades=0, winning_trades=0, losing_trades=0,
            win_rate=0.0, loss_rate=0.0, profit_factor=0.0,
            expectancy=0.0, payoff_ratio=0.0, kelly_criterion=0.0,
            consecutive_wins=0, consecutive_losses=0,
            max_consecutive_wins=0, max_consecutive_losses=0,
            recovery_factor=0.0,
        )

    def _empty_risk_metrics(self) -> RiskMetrics:
        return RiskMetrics(
            sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
            max_drawdown_pct=0.0, max_drawdown_amount=0.0,
            max_drawdown_duration_seconds=0.0, max_drawdown_recovery_seconds=0.0,
            volatility_annual=0.0, downside_deviation=0.0,
            tail_ratio=0.0, value_at_risk_95=0.0, conditional_var_95=0.0,
        )
