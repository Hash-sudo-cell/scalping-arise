"""
Scalping Arise — Stop-Loss Engine

Places stop-loss levels using invalidation-based, ATR-based,
and structure-based methods. Invalidation is primary; ATR and
structure are fallbacks.
"""

from __future__ import annotations

from typing import Optional

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.instrument_specs import get_spec_or_raise
from app.modules.trade_planning.models import (
    PlanSide,
    SLType,
    StopLossPlan,
    VolatilityAdjustment,
)


def plan_stop_loss(
    *,
    side: PlanSide,
    entry_price: float,
    atr_value: Optional[float] = None,
    invalidation_level: Optional[float] = None,
    structure_level: Optional[float] = None,
    volatility_adjustment: VolatilityAdjustment = VolatilityAdjustment.NORMAL,
    instrument: str,
    settings: Optional[TradePlanningSettings] = None,
) -> StopLossPlan:
    """
    Determine stop-loss placement.

    Priority:
    1. Invalidation-based (primary — from market structure)
    2. ATR-based (fallback — volatility-adjusted)
    3. Structure-based (last resort — S/R levels)

    All placements enforce min/max distance and tick alignment.
    """
    settings = settings or get_trade_planning_settings()
    spec = get_spec_or_raise(instrument)

    # Select ATR multiplier based on volatility
    atr_multiplier = settings.sl_atr_multiplier
    if volatility_adjustment == VolatilityAdjustment.EXPAND:
        atr_multiplier = settings.volatility_expand_sl_multiplier
    elif volatility_adjustment == VolatilityAdjustment.CONTRACT:
        atr_multiplier = settings.volatility_contract_sl_multiplier

    # Try invalidation-based SL first
    if invalidation_level is not None and invalidation_level > 0:
        sl_price = _place_invalidation_sl(
            side=side,
            entry_price=entry_price,
            invalidation_level=invalidation_level,
            buffer_ticks=settings.sl_invalidation_buffer_ticks,
            spec_tick=spec.tick_size,
        )
        distance = abs(entry_price - sl_price)
        distance_pips = spec.pip_distance(entry_price, sl_price)
        risk_per_lot = distance * spec.contract_size

        # Validate against min/max
        if distance_pips < settings.sl_min_distance_pips:
            # Widen to minimum
            sl_price = _enforce_min_distance(side, entry_price, settings.sl_min_distance_pips, spec)
            distance = abs(entry_price - sl_price)
            distance_pips = settings.sl_min_distance_pips
            risk_per_lot = distance * spec.contract_size

        if distance_pips > settings.sl_max_distance_pips:
            # Tighten to maximum
            sl_price = _enforce_max_distance(side, entry_price, settings.sl_max_distance_pips, spec)
            distance = abs(entry_price - sl_price)
            distance_pips = settings.sl_max_distance_pips
            risk_per_lot = distance * spec.contract_size

        sl_price = spec.round_price(sl_price)

        return StopLossPlan(
            sl_type=SLType.INVALIDATION,
            sl_price=sl_price,
            sl_distance_pips=round(distance_pips, 2),
            sl_distance_price=round(distance, spec.price_precision),
            risk_per_lot=round(risk_per_lot, 2),
            invalidation_level=invalidation_level,
            reason=f"Invalidation-based SL at {sl_price} (buffer: {settings.sl_invalidation_buffer_ticks} ticks)",
            evidence=[
                f"Invalidation level: {invalidation_level}",
                f"Buffer: {settings.sl_invalidation_buffer_ticks} ticks",
                f"SL distance: {distance_pips:.1f} pips",
            ],
        )

    # Try ATR-based SL
    if atr_value is not None and atr_value > 0:
        atr_distance = atr_value * atr_multiplier
        if side == PlanSide.LONG:
            sl_price = entry_price - atr_distance
        else:
            sl_price = entry_price + atr_distance

        distance_pips = spec.pip_distance(entry_price, sl_price)
        risk_per_lot = abs(entry_price - sl_price) * spec.contract_size

        # Enforce min/max
        if distance_pips < settings.sl_min_distance_pips:
            sl_price = _enforce_min_distance(side, entry_price, settings.sl_min_distance_pips, spec)
            distance_pips = settings.sl_min_distance_pips
            risk_per_lot = abs(entry_price - sl_price) * spec.contract_size
        elif distance_pips > settings.sl_max_distance_pips:
            sl_price = _enforce_max_distance(side, entry_price, settings.sl_max_distance_pips, spec)
            distance_pips = settings.sl_max_distance_pips
            risk_per_lot = abs(entry_price - sl_price) * spec.contract_size

        sl_price = spec.round_price(sl_price)

        return StopLossPlan(
            sl_type=SLType.ATR,
            sl_price=sl_price,
            sl_distance_pips=round(distance_pips, 2),
            sl_distance_price=round(abs(entry_price - sl_price), spec.price_precision),
            risk_per_lot=round(risk_per_lot, 2),
            atr_multiple=atr_multiplier,
            reason=f"ATR-based SL: {atr_value:.4f} x {atr_multiplier} = {atr_distance:.4f}",
            evidence=[
                f"ATR value: {atr_value}",
                f"ATR multiplier: {atr_multiplier}",
                f"ATR distance: {atr_distance}",
                f"SL distance: {distance_pips:.1f} pips",
            ],
        )

    # Try structure-based SL
    if structure_level is not None and structure_level > 0:
        sl_price = spec.round_price(structure_level)
        distance_pips = spec.pip_distance(entry_price, sl_price)
        risk_per_lot = abs(entry_price - sl_price) * spec.contract_size

        # Validate
        if distance_pips < settings.sl_min_distance_pips:
            sl_price = _enforce_min_distance(side, entry_price, settings.sl_min_distance_pips, spec)
            distance_pips = settings.sl_min_distance_pips
            risk_per_lot = abs(entry_price - sl_price) * spec.contract_size
        elif distance_pips > settings.sl_max_distance_pips:
            sl_price = _enforce_max_distance(side, entry_price, settings.sl_max_distance_pips, spec)
            distance_pips = settings.sl_max_distance_pips
            risk_per_lot = abs(entry_price - sl_price) * spec.contract_size

        return StopLossPlan(
            sl_type=SLType.STRUCTURE,
            sl_price=sl_price,
            sl_distance_pips=round(distance_pips, 2),
            sl_distance_price=round(abs(entry_price - sl_price), spec.price_precision),
            risk_per_lot=round(risk_per_lot, 2),
            reason=f"Structure-based SL at {sl_price}",
            evidence=[f"Structure level: {structure_level}", f"SL distance: {distance_pips:.1f} pips"],
        )

    # Fallback: minimum distance SL
    sl_price = _enforce_min_distance(side, entry_price, settings.sl_min_distance_pips, spec)
    distance_pips = settings.sl_min_distance_pips
    risk_per_lot = abs(entry_price - sl_price) * spec.contract_size

    return StopLossPlan(
        sl_type=SLType.FIXED,
        sl_price=sl_price,
        sl_distance_pips=round(distance_pips, 2),
        sl_distance_price=round(abs(entry_price - sl_price), spec.price_precision),
        risk_per_lot=round(risk_per_lot, 2),
        reason=f"Fallback SL: minimum distance {settings.sl_min_distance_pips} pips",
        evidence=[f"Min distance: {settings.sl_min_distance_pips} pips"],
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _place_invalidation_sl(
    *,
    side: PlanSide,
    entry_price: float,
    invalidation_level: float,
    buffer_ticks: int,
    spec_tick: float,
) -> float:
    """Place SL beyond invalidation level with buffer ticks."""
    buffer = buffer_ticks * spec_tick
    if side == PlanSide.LONG:
        # SL below invalidation
        return invalidation_level - buffer
    else:
        # SL above invalidation
        return invalidation_level + buffer


def _enforce_min_distance(
    side: PlanSide,
    entry_price: float,
    min_pips: float,
    spec: "InstrumentSpecification",
) -> float:
    """Ensure SL is at least min_pips from entry."""
    # Convert pips to price distance
    # For most instruments: 1 pip = tick_size * 10
    pip_value = spec.tick_size * 10
    min_distance = min_pips * pip_value

    if side == PlanSide.LONG:
        return spec.round_price(entry_price - min_distance)
    else:
        return spec.round_price(entry_price + min_distance)


def _enforce_max_distance(
    side: PlanSide,
    entry_price: float,
    max_pips: float,
    spec: "InstrumentSpecification",
) -> float:
    """Ensure SL is at most max_pips from entry."""
    pip_value = spec.tick_size * 10
    max_distance = max_pips * pip_value

    if side == PlanSide.LONG:
        return spec.round_price(entry_price - max_distance)
    else:
        return spec.round_price(entry_price + max_distance)
