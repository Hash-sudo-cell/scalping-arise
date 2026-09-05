"""
Scalping Arise — Strategy Performance Tracker

Tracks and computes performance metrics for strategies from
realized trade outcomes. Does NOT implement backtesting or
forward-testing — only consumes actual recorded outcomes.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from app.modules.news_intelligence.config import NewsIntelligenceSettings, get_news_intelligence_settings
from app.modules.news_intelligence.models import StrategyPerformanceMetrics, TradeOutcome


class PerformanceTracker:
    """
    In-memory strategy performance tracker.

    Stores trade outcomes per strategy and computes metrics on demand.
    No persistence — matches the project's in-memory architecture.
    """

    def __init__(
        self,
        settings: NewsIntelligenceSettings | None = None,
    ) -> None:
        self._settings = settings or get_news_intelligence_settings()
        self._outcomes: dict[str, deque[TradeOutcome]] = {}

    def record_outcome(self, outcome: TradeOutcome) -> None:
        """Record a realized trade outcome for a strategy."""
        key = outcome.strategy_id
        if key not in self._outcomes:
            self._outcomes[key] = deque(maxlen=10000)
        self._outcomes[key].append(outcome)

    def get_outcomes(self, strategy_id: str) -> list[TradeOutcome]:
        """Get all recorded outcomes for a strategy."""
        return list(self._outcomes.get(strategy_id, []))

    def compute_metrics(self, strategy_id: str) -> StrategyPerformanceMetrics:
        """
        Compute performance metrics for a strategy from recorded outcomes.

        Returns zero-valued metrics if no outcomes exist.
        """
        outcomes = self.get_outcomes(strategy_id)
        if not outcomes:
            return _empty_metrics(strategy_id)

        total = len(outcomes)
        winners = [o for o in outcomes if o.is_winner]
        losers = [o for o in outcomes if not o.is_winner]

        win_count = len(winners)
        loss_count = len(losers)
        win_rate = win_count / total if total > 0 else 0.0

        net_pnl = sum(o.pnl for o in outcomes)
        gross_wins = sum(o.pnl for o in winners) if winners else 0.0
        gross_losses = abs(sum(o.pnl for o in losers)) if losers else 0.0
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else (
            float("inf") if gross_wins > 0 else 0.0
        )

        avg_win = gross_wins / win_count if win_count > 0 else 0.0
        avg_loss = -(gross_losses / loss_count) if loss_count > 0 else 0.0

        # Drawdown calculation
        max_dd = _compute_max_drawdown(outcomes)

        # Consecutive losses
        consec_losses = _compute_consecutive_losses(outcomes)

        # Recent window
        recent_n = self._settings.recent_trades_window
        recent = outcomes[-recent_n:] if len(outcomes) >= recent_n else outcomes
        recent_wins = sum(1 for o in recent if o.is_winner)
        recent_win_rate = recent_wins / len(recent) if recent else 0.0

        return StrategyPerformanceMetrics(
            strategy_id=strategy_id,
            total_trades=total,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate=round(win_rate, 4),
            net_pnl=round(net_pnl, 2),
            average_win=round(avg_win, 2),
            average_loss=round(avg_loss, 2),
            profit_factor=round(min(profit_factor, 999.99), 2),
            max_drawdown=round(max_dd, 2),
            consecutive_losses=consec_losses,
            recent_win_rate=round(recent_win_rate, 4),
            recent_trades=len(recent),
        )

    def clear(self, strategy_id: str | None = None) -> None:
        """Clear outcomes for a specific strategy or all strategies."""
        if strategy_id:
            self._outcomes.pop(strategy_id, None)
        else:
            self._outcomes.clear()


def _empty_metrics(strategy_id: str) -> StrategyPerformanceMetrics:
    """Return zero-valued metrics."""
    return StrategyPerformanceMetrics(
        strategy_id=strategy_id,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate=0.0,
        net_pnl=0.0,
        average_win=0.0,
        average_loss=0.0,
        profit_factor=0.0,
        max_drawdown=0.0,
        consecutive_losses=0,
        recent_win_rate=0.0,
        recent_trades=0,
    )


def _compute_max_drawdown(outcomes: list[TradeOutcome]) -> float:
    """Compute maximum drawdown from a sequence of trade outcomes."""
    if not outcomes:
        return 0.0

    peak = 0.0
    equity = 0.0
    max_dd = 0.0

    for o in outcomes:
        equity += o.pnl
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    return max_dd


def _compute_consecutive_losses(outcomes: list[TradeOutcome]) -> int:
    """Count consecutive losses from the most recent trade backward."""
    count = 0
    for o in reversed(outcomes):
        if not o.is_winner:
            count += 1
        else:
            break
    return count
