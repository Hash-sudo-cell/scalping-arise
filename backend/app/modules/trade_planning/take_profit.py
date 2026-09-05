"""
Scalping Arise — Take-Profit Engine

Places TP1 (conservative) and TP2 (extended) targets based on
risk-reward ratios, structure levels, and ATR projections.
"""

from __future__ import annotations

from typing import Optional

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.instrument_specs import get_spec_or_raise
from app.modules.trade_planning.models import (
    PlanSide,
    TakeProfitPlan,
    TakeProfitTarget,
    TPTarget,
    rr_ratio,
)


def plan_take_profit(
    *,
    side: PlanSide,
    entry_price: float,
    sl_price: float,
    sl_distance_price: float,
    atr_value: Optional[float] = None,
    structure_targets: Optional[list[float]] = None,
    instrument: str,
    settings: Optional[TradePlanningSettings] = None,
) -> TakeProfitPlan:
    """
    Determine take-profit targets.

    TP1: Conservative target at configured R:R ratio
    TP2: Extended target at higher R:R ratio

    Structure levels may override calculated targets if they provide
    better R:R ratios.
    """
    settings = settings or get_trade_planning_settings()
    spec = get_spec_or_raise(instrument)
    targets: list[TakeProfitTarget] = []
    evidence: list[str] = []

    # Calculate base TP prices from R:R ratios
    tp1_distance = sl_distance_price * settings.tp1_risk_reward_ratio
    tp2_distance = sl_distance_price * settings.tp2_risk_reward_ratio

    if side == PlanSide.LONG:
        tp1_price = spec.round_price(entry_price + tp1_distance)
        tp2_price = spec.round_price(entry_price + tp2_distance)
    else:
        tp1_price = spec.round_price(entry_price - tp1_distance)
        tp2_price = spec.round_price(entry_price - tp2_distance)

    # Validate against structure targets
    if structure_targets:
        # Pick the best structure target for TP1 (closest that meets min R:R)
        valid_structure = [
            t for t in structure_targets
            if _structure_valid(t, side, entry_price, sl_distance_price, settings.tp_min_distance_pips, spec)
        ]
        if valid_structure:
            best = _pick_best_structure_target(valid_structure, side, entry_price, sl_distance_price)
            if best is not None:
                tp1_price = spec.round_price(best)
                tp1_distance = abs(entry_price - tp1_price)
                evidence.append(f"Structure target used for TP1: {best}")

    # Validate TP1
    tp1_distance_pips = spec.pip_distance(entry_price, tp1_price)
    if tp1_distance_pips < settings.tp_min_distance_pips:
        # Enforce minimum
        tp1_distance_price = settings.tp_min_distance_pips * spec.tick_size * 10
        if side == PlanSide.LONG:
            tp1_price = spec.round_price(entry_price + tp1_distance_price)
        else:
            tp1_price = spec.round_price(entry_price - tp1_distance_price)
        tp1_distance_pips = settings.tp_min_distance_pips

    if tp1_distance_pips > settings.tp_max_distance_pips:
        # Cap at maximum
        tp1_distance_price = settings.tp_max_distance_pips * spec.tick_size * 10
        if side == PlanSide.LONG:
            tp1_price = spec.round_price(entry_price + tp1_distance_price)
        else:
            tp1_price = spec.round_price(entry_price - tp1_distance_price)
        tp1_distance_pips = settings.tp_max_distance_pips

    # Build TP1 target
    tp1_reward = abs(tp1_price - entry_price)
    tp1_rr = rr_ratio(tp1_reward, sl_distance_price)
    tp1_reward_per_lot = tp1_reward * spec.contract_size

    targets.append(TakeProfitTarget(
        target=TPTarget.TP1,
        tp_price=tp1_price,
        tp_distance_pips=round(tp1_distance_pips, 2),
        tp_distance_price=round(tp1_reward, spec.price_precision),
        reward_per_lot=round(tp1_reward_per_lot, 2),
        risk_reward_ratio=round(tp1_rr, 2),
        partial_close_pct=settings.tp1_partial_close_pct,
        reason=f"TP1 at R:R {tp1_rr:.2f}",
    ))

    # Build TP2 target (same distance calculation, no partial close)
    tp2_distance_pips = spec.pip_distance(entry_price, tp2_price)
    if tp2_distance_pips < settings.tp_min_distance_pips:
        tp2_distance_price = settings.tp_min_distance_pips * spec.tick_size * 10
        if side == PlanSide.LONG:
            tp2_price = spec.round_price(entry_price + tp2_distance_price)
        else:
            tp2_price = spec.round_price(entry_price - tp2_distance_price)
        tp2_distance_pips = settings.tp_min_distance_pips

    if tp2_distance_pips > settings.tp_max_distance_pips:
        tp2_distance_price = settings.tp_max_distance_pips * spec.tick_size * 10
        if side == PlanSide.LONG:
            tp2_price = spec.round_price(entry_price + tp2_distance_price)
        else:
            tp2_price = spec.round_price(entry_price - tp2_distance_price)
        tp2_distance_pips = settings.tp_max_distance_pips

    tp2_reward = abs(tp2_price - entry_price)
    tp2_rr = rr_ratio(tp2_reward, sl_distance_price)
    tp2_reward_per_lot = tp2_reward * spec.contract_size

    targets.append(TakeProfitTarget(
        target=TPTarget.TP2,
        tp_price=tp2_price,
        tp_distance_pips=round(tp2_distance_pips, 2),
        tp_distance_price=round(tp2_reward, spec.price_precision),
        reward_per_lot=round(tp2_reward_per_lot, 2),
        risk_reward_ratio=round(tp2_rr, 2),
        reason=f"TP2 at R:R {tp2_rr:.2f}",
    ))

    evidence.append(f"TP1: {tp1_price} (R:R {tp1_rr:.2f})")
    evidence.append(f"TP2: {tp2_price} (R:R {tp2_rr:.2f})")

    return TakeProfitPlan(
        targets=targets,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _structure_valid(
    target: float,
    side: PlanSide,
    entry_price: float,
    sl_distance_price: float,
    min_pips: float,
    spec: "InstrumentSpecification",
) -> bool:
    """Check if a structure target is valid for use as TP."""
    distance = abs(target - entry_price)
    distance_pips = spec.pip_distance(entry_price, target)
    if distance_pips < min_pips:
        return False
    # Must be in the correct direction
    if side == PlanSide.LONG and target <= entry_price:
        return False
    if side == PlanSide.SHORT and target >= entry_price:
        return False
    return True


def _pick_best_structure_target(
    targets: list[float],
    side: PlanSide,
    entry_price: float,
    sl_distance_price: float,
) -> Optional[float]:
    """Pick the structure target closest to the ideal R:R ratio."""
    if not targets:
        return None
    # Sort by distance from entry (closest first for TP1)
    if side == PlanSide.LONG:
        valid = [t for t in targets if t > entry_price]
        valid.sort()
    else:
        valid = [t for t in targets if t < entry_price]
        valid.sort(reverse=True)
    return valid[0] if valid else None
