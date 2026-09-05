"""
Scalping Arise — Strategy State Machine

Manages strategy performance states (ACTIVE / MONITORED / RESTRICTED / DISABLED)
with minimum sample protection, underperformance detection, and recovery logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.modules.news_intelligence.config import NewsIntelligenceSettings, get_news_intelligence_settings
from app.modules.news_intelligence.models import (
    RecoveryState,
    StrategyPerformanceMetrics,
    StrategyPerformanceState,
    StrategyStateRecord,
)


def evaluate_strategy_state(
    strategy_id: str,
    metrics: StrategyPerformanceMetrics,
    current_state: StrategyPerformanceState | None = None,
    recovery_state: RecoveryState | None = None,
    settings: NewsIntelligenceSettings | None = None,
) -> tuple[StrategyPerformanceState, RecoveryState | None, list[str]]:
    """
    Evaluate the performance state of a strategy.

    Returns:
        (new_state, new_recovery_state, reasons)
    """
    settings = settings or get_news_intelligence_settings()
    current = current_state or StrategyPerformanceState.ACTIVE
    reasons: list[str] = []

    # --- Minimum sample protection ---
    if metrics.total_trades < settings.min_performance_sample:
        if current == StrategyPerformanceState.DISABLED:
            # Don't keep disabled from tiny sample — move to MONITORED
            return (
                StrategyPerformanceState.MONITORED,
                RecoveryState.RECOVERY_EVALUATION,
                ["Insufficient sample for DISABLED — moving to MONITORED for observation"],
            )
        reasons.append(f"Sample size {metrics.total_trades} < minimum {settings.min_performance_sample}")
        return StrategyPerformanceState.MONITORED, recovery_state, reasons

    # --- Recovery logic for DISABLED strategies ---
    if current == StrategyPerformanceState.DISABLED:
        return _evaluate_recovery(metrics, recovery_state, settings)

    # --- Active state checks ---
    underperforming = False

    if metrics.win_rate < settings.min_win_rate:
        underperforming = True
        reasons.append(
            f"Win rate {metrics.win_rate:.1%} below minimum {settings.min_win_rate:.1%}"
        )

    if metrics.max_drawdown > settings.max_drawdown_pct:
        underperforming = True
        reasons.append(
            f"Drawdown {metrics.max_drawdown:.1f}% exceeds maximum {settings.max_drawdown_pct:.1f}%"
        )

    if metrics.consecutive_losses >= settings.max_consecutive_losses:
        underperforming = True
        reasons.append(
            f"Consecutive losses {metrics.consecutive_losses} >= maximum {settings.max_consecutive_losses}"
        )

    if metrics.profit_factor < settings.min_profit_factor:
        underperforming = True
        reasons.append(
            f"Profit factor {metrics.profit_factor:.2f} below minimum {settings.min_profit_factor:.2f}"
        )

    # --- State transitions ---
    if underperforming:
        if current == StrategyPerformanceState.ACTIVE:
            # Check severity — if multiple thresholds breached, go to RESTRICTED
            breach_count = len(reasons)
            if breach_count >= 2:
                return StrategyPerformanceState.RESTRICTED, None, reasons
            return StrategyPerformanceState.MONITORED, None, reasons

        if current == StrategyPerformanceState.MONITORED:
            # If still underperforming after monitoring, restrict
            return StrategyPerformanceState.RESTRICTED, None, reasons

        if current == StrategyPerformanceState.RESTRICTED:
            # If severely underperforming (all thresholds), disable
            if len(reasons) >= 3:
                return StrategyPerformanceState.DISABLED, RecoveryState.DISABLED, reasons
            return StrategyPerformanceState.RESTRICTED, None, reasons

    else:
        # Not underperforming — recover if previously restricted
        if current == StrategyPerformanceState.RESTRICTED:
            return StrategyPerformanceState.MONITORED, None, ["Performance recovered — moving to MONITORED"]
        if current == StrategyPerformanceState.MONITORED:
            return StrategyPerformanceState.ACTIVE, None, ["Performance healthy — returning to ACTIVE"]

    # No change
    return current, recovery_state, reasons


def _evaluate_recovery(
    metrics: StrategyPerformanceMetrics,
    recovery_state: RecoveryState | None,
    settings: NewsIntelligenceSettings,
) -> tuple[StrategyPerformanceState, RecoveryState, list[str]]:
    """Evaluate recovery progress for a DISABLED strategy."""
    reasons: list[str] = []
    current_recovery = recovery_state or RecoveryState.DISABLED

    # Check minimum recovery sample
    if metrics.total_trades < settings.recovery_min_sample:
        return (
            StrategyPerformanceState.DISABLED,
            RecoveryState.RECOVERY_EVALUATION,
            [f"Recovery sample {metrics.total_trades} < minimum {settings.recovery_min_sample}"],
        )

    # Check recovery thresholds
    recovery_ok = True

    if metrics.win_rate < settings.recovery_min_win_rate:
        recovery_ok = False
        reasons.append(
            f"Recovery win rate {metrics.win_rate:.1%} below minimum {settings.recovery_min_win_rate:.1f%}"
        )

    if metrics.max_drawdown > settings.recovery_max_drawdown_pct:
        recovery_ok = False
        reasons.append(
            f"Recovery drawdown {metrics.max_drawdown:.1f}% exceeds maximum {settings.recovery_max_drawdown_pct:.1f}%"
        )

    if metrics.profit_factor < settings.recovery_min_profit_factor:
        recovery_ok = False
        reasons.append(
            f"Recovery profit factor {metrics.profit_factor:.2f} below minimum {settings.recovery_min_profit_factor:.2f}"
        )

    if recovery_ok:
        if current_recovery == RecoveryState.RECOVERY_EVALUATION:
            return (
                StrategyPerformanceState.RESTRICTED,
                RecoveryState.RESTRICTED,
                ["Recovery criteria met — moving to RESTRICTED"],
            )
        if current_recovery == RecoveryState.RESTRICTED:
            return (
                StrategyPerformanceState.ACTIVE,
                RecoveryState.ACTIVE,
                ["Sustained recovery — returning to ACTIVE"],
            )

    return StrategyPerformanceState.DISABLED, RecoveryState.DISABLED, reasons


def create_initial_state(strategy_id: str) -> StrategyStateRecord:
    """Create an initial state record for a strategy."""
    return StrategyStateRecord(
        strategy_id=strategy_id,
        state=StrategyPerformanceState.ACTIVE,
        recovery_state=None,
        sample_size=0,
        state_reasons=["Initial state — no trades recorded"],
        last_state_change=datetime.now(timezone.utc),
    )
