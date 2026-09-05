"""
Scalping Arise — Risk-Reward Validation

Validates that a trade plan meets minimum reward-to-risk ratio requirements.
"""

from __future__ import annotations

from typing import Optional

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.models import TakeProfitPlan, rr_ratio


def validate_risk_reward(
    take_profit: TakeProfitPlan,
    sl_distance_price: float,
    settings: Optional[TradePlanningSettings] = None,
) -> tuple[bool, str]:
    """
    Validate that take-profit targets meet minimum R:R ratio.

    Returns:
        (valid, reason)
    """
    settings = settings or get_trade_planning_settings()

    if not take_profit.targets:
        return False, "No take-profit targets defined"

    if sl_distance_price <= 0:
        return False, "Stop-loss distance is zero or negative"

    # Check TP1 meets minimum R:R
    tp1 = next((t for t in take_profit.targets if t.target.value == "tp1"), None)
    if tp1 is None:
        return False, "TP1 target missing"

    actual_rr = rr_ratio(tp1.tp_distance_price, sl_distance_price)
    if actual_rr < settings.min_risk_reward_ratio:
        return False, (
            f"TP1 R:R {actual_rr:.2f} below minimum {settings.min_risk_reward_ratio}"
        )

    return True, f"R:R validated: TP1={actual_rr:.2f}"
