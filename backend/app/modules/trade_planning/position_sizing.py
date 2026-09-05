"""
Scalping Arise — Position Sizing & Risk Calculation

Calculates lot size based on account balance, risk percentage,
SL distance, and instrument specification. Enforces lot rounding
and margin constraints.
"""

from __future__ import annotations

from typing import Optional

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.instrument_specs import get_spec_or_raise
from app.modules.trade_planning.models import (
    InstrumentSpecification,
    PositionSizeResult,
    RiskCalculation,
    RiskParameters,
)


def calculate_position_size(
    *,
    account_balance: float,
    risk_per_trade_pct: float,
    sl_distance_price: float,
    instrument: str,
    settings: Optional[TradePlanningSettings] = None,
) -> PositionSizeResult:
    """
    Calculate optimal lot size based on risk parameters.

    Formula:
        risk_amount = account_balance * (risk_per_trade_pct / 100)
        lots = risk_amount / (sl_distance_price * contract_size)
        lots = round to lot_step, clamp to min/max

    Then calculates margin and exposure from the rounded lot size.
    """
    settings = settings or get_trade_planning_settings()
    spec = get_spec_or_raise(instrument)

    # Risk amount in account currency
    risk_amount = account_balance * (risk_per_trade_pct / 100)

    # Raw lot size
    if sl_distance_price <= 0 or spec.contract_size <= 0:
        raw_lots = 0.0
    else:
        raw_lots = risk_amount / (sl_distance_price * spec.contract_size)

    # Round to lot step and clamp
    lots = spec.round_lots(raw_lots)

    # Recalculate actual risk from rounded lots
    actual_risk = lots * sl_distance_price * spec.contract_size
    risk_pct_actual = (actual_risk / account_balance * 100) if account_balance > 0 else 0.0

    # Margin calculation
    notional = lots * spec.contract_size * (sl_distance_price + spec.round_price(sl_distance_price))
    # Simplified: use entry-level notional for margin (SL price is approximate)
    margin_required = lots * spec.contract_size * spec.margin_rate
    margin_pct = (margin_required / account_balance * 100) if account_balance > 0 else 0.0

    # Exposure
    exposure = lots * spec.contract_size
    exposure_pct = (exposure / account_balance * 100) if account_balance > 0 else 0.0

    return PositionSizeResult(
        lots=round(lots, 10),
        risk_amount=round(actual_risk, 2),
        risk_pct_actual=round(risk_pct_actual, 4),
        margin_required=round(margin_required, 2),
        margin_pct=round(margin_pct, 4),
        exposure=round(exposure, 2),
        exposure_pct=round(exposure_pct, 4),
    )


def calculate_risk(
    *,
    account_balance: float,
    risk_per_trade_pct: float,
    sl_distance_price: float,
    instrument: str,
    current_open_positions: int = 0,
    current_daily_loss: float = 0.0,
    peak_balance: Optional[float] = None,
    settings: Optional[TradePlanningSettings] = None,
) -> RiskCalculation:
    """
    Complete risk calculation with guardrail checks.

    Combines position sizing with risk limit validation.
    """
    settings = settings or get_trade_planning_settings()

    # Position sizing
    position_size = calculate_position_size(
        account_balance=account_balance,
        risk_per_trade_pct=risk_per_trade_pct,
        sl_distance_price=sl_distance_price,
        instrument=instrument,
        settings=settings,
    )

    # Guardrail checks
    risk_params = RiskParameters(
        account_balance=account_balance,
        risk_per_trade_pct=risk_per_trade_pct,
        max_positions=settings.max_open_positions,
        current_open_positions=current_open_positions,
    )

    # Daily loss check
    daily_loss_limit = account_balance * (settings.max_daily_loss_pct / 100)
    daily_loss_remaining = max(0.0, daily_loss_limit - current_daily_loss)
    within_daily_loss = position_size.risk_amount <= daily_loss_remaining

    # Drawdown check
    effective_peak = peak_balance if peak_balance and peak_balance > 0 else account_balance
    drawdown_limit = effective_peak * (settings.max_drawdown_pct / 100)
    current_drawdown = max(0.0, effective_peak - account_balance)
    drawdown_remaining = max(0.0, drawdown_limit - current_drawdown)
    within_drawdown = (current_drawdown + position_size.risk_amount) <= drawdown_limit

    # Portfolio risk check
    total_risk_pct = position_size.risk_pct_actual
    within_risk = total_risk_pct <= settings.risk_per_trade_pct

    # Position count check
    within_positions = current_open_positions < settings.max_open_positions

    warnings: list[str] = []
    rejections: list[str] = []

    if not within_daily_loss:
        rejections.append(
            f"Daily loss limit: risk {position_size.risk_amount:.2f} exceeds remaining {daily_loss_remaining:.2f}"
        )
    if not within_drawdown:
        rejections.append(
            f"Drawdown limit: risk {position_size.risk_amount:.2f} exceeds remaining {drawdown_remaining:.2f}"
        )
    if not within_positions:
        rejections.append(
            f"Max positions reached: {current_open_positions}/{settings.max_open_positions}"
        )
    if total_risk_pct > settings.risk_per_trade_pct * 0.8:
        warnings.append(f"Risk at {total_risk_pct:.1f}% — approaching limit {settings.risk_per_trade_pct}%")

    return RiskCalculation(
        position_size=position_size,
        risk_parameters=risk_params,
        within_risk_limits=within_risk and within_positions,
        within_drawdown_limit=within_drawdown,
        within_daily_loss_limit=within_daily_loss,
        daily_loss_remaining=round(daily_loss_remaining, 2),
        max_drawdown_remaining=round(drawdown_remaining, 2),
        warnings=warnings,
        rejections=rejections,
    )
