"""
Scalping Arise — Cost Validation

Estimates trading costs (spread, commission) and validates they
are within acceptable limits relative to the trade's risk.
"""

from __future__ import annotations

from typing import Optional

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.instrument_specs import get_spec_or_raise
from app.modules.trade_planning.models import CostEstimate


def estimate_cost(
    *,
    lots: float,
    spread_pips: Optional[float],
    instrument: str,
    risk_amount: float = 0.0,
    settings: Optional[TradePlanningSettings] = None,
) -> CostEstimate:
    """
    Estimate trading costs and validate against risk.

    Cost = spread cost + commission
    Validated as percentage of risk amount.
    """
    settings = settings or get_trade_planning_settings()
    spec = get_spec_or_raise(instrument)

    # Spread cost
    effective_spread = spread_pips if spread_pips is not None else spec.typical_spread_pips
    spread_cost = effective_spread * spec.pip_value_per_lot * lots

    # Commission
    commission = settings.typical_commission_per_lot * lots

    # Total cost
    total_cost = spread_cost + commission

    # Cost as % of risk
    cost_pct = (total_cost / risk_amount * 100) if risk_amount > 0 else 0.0

    # Tolerance check
    within_tolerance = cost_pct <= settings.max_spread_cost_pct_of_risk

    reason = ""
    if not within_tolerance:
        reason = f"Cost {cost_pct:.1f}% of risk exceeds limit {settings.max_spread_cost_pct_of_risk}%"

    return CostEstimate(
        spread_cost=round(spread_cost, 2),
        spread_pips=round(effective_spread, 2),
        commission=round(commission, 2),
        total_cost=round(total_cost, 2),
        cost_pct_of_risk=round(cost_pct, 2),
        within_tolerance=within_tolerance,
        reason=reason,
    )
