"""
Scalping Arise — Risk Guardrails

Enforces maximum risk limits, drawdown limits, and daily loss limits.
Runs before plan validation to prevent over-risking.
"""

from __future__ import annotations

from typing import Optional

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.models import RiskCalculation


def validate_risk_guardrails(
    risk: RiskCalculation,
    settings: Optional[TradePlanningSettings] = None,
) -> tuple[bool, list[str]]:
    """
    Validate that a risk calculation passes all guardrails.

    Returns:
        (passed, list_of_rejection_reasons)
    """
    settings = settings or get_trade_planning_settings()
    rejections: list[str] = []

    # Daily loss limit
    if not risk.within_daily_loss_limit:
        rejections.append(
            f"Daily loss limit exceeded: remaining {risk.daily_loss_remaining:.2f}"
        )

    # Drawdown limit
    if not risk.within_drawdown_limit:
        rejections.append(
            f"Drawdown limit exceeded: remaining {risk.max_drawdown_remaining:.2f}"
        )

    # Risk per trade
    if not risk.within_risk_limits:
        rejections.append(
            f"Risk per trade exceeded: {risk.position_size.risk_pct_actual:.2f}% > allowed"
        )

    # Any rejections from the risk calculation itself
    rejections.extend(risk.rejections)

    return len(rejections) == 0, rejections
