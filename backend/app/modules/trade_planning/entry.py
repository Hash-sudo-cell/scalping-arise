"""
Scalping Arise — Entry Planning Engine

Determines entry state (ENTRY_READY, WAIT_FOR_ENTRY, ENTRY_UNAVAILABLE)
based on current spread, price position, and signal direction.
"""

from __future__ import annotations

from typing import Optional

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.instrument_specs import get_spec_or_raise
from app.modules.trade_planning.models import (
    EntryPlan,
    EntryState,
    EntryType,
    PlanSide,
    PriceTickCheck,
)


def plan_entry(
    *,
    side: PlanSide,
    current_price: float,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    spread_pips: Optional[float] = None,
    price_check: Optional[PriceTickCheck],
    instrument: str,
    settings: Optional[TradePlanningSettings] = None,
) -> EntryPlan:
    """
    Determine the entry plan for a trade.

    ENTRY_READY: spread is tight enough, price is valid, can enter immediately
    WAIT_FOR_ENTRY: conditions are almost met, wait for spread to tighten
    ENTRY_UNAVAILABLE: cannot enter (price invalid, spread too wide, etc.)
    """
    settings = settings or get_trade_planning_settings()
    spec = get_spec_or_raise(instrument)
    evidence: list[str] = []

    # Price validation
    if price_check and not price_check.is_valid:
        return EntryPlan(
            state=EntryState.ENTRY_UNAVAILABLE,
            reason=f"Price validation failed: {price_check.reason}",
            evidence=[price_check.reason],
        )

    if current_price <= 0:
        return EntryPlan(
            state=EntryState.ENTRY_UNAVAILABLE,
            reason="Current price is zero or negative",
            evidence=["Invalid price"],
        )

    # Tick alignment check
    tick_aligned = spec.is_tick_aligned(current_price)
    if not tick_aligned:
        evidence.append(f"Price {current_price} not aligned to tick grid (tick_size={spec.tick_size})")

    # Spread check
    effective_spread_pips = spread_pips
    if effective_spread_pips is None and bid is not None and ask is not None and bid > 0:
        effective_spread_pips = spec.pip_distance(bid, ask)

    if effective_spread_pips is not None:
        if effective_spread_pips > settings.entry_ready_max_spread_pips * 2:
            return EntryPlan(
                state=EntryState.ENTRY_UNAVAILABLE,
                entry_price=current_price,
                reason=f"Spread {effective_spread_pips:.1f} pips exceeds maximum",
                evidence=[f"Spread {effective_spread_pips:.1f} pips > 2x max {settings.entry_ready_max_spread_pips}"],
            )
        elif effective_spread_pips > settings.entry_ready_max_spread_pips:
            return EntryPlan(
                state=EntryState.WAIT_FOR_ENTRY,
                entry_price=current_price,
                entry_type=EntryType.MARKET,
                reason=f"Spread {effective_spread_pips:.1f} pips too wide, waiting for tightening",
                evidence=[f"Spread {effective_spread_pips:.1f} > max {settings.entry_ready_max_spread_pips}"],
            )
        else:
            evidence.append(f"Spread {effective_spread_pips:.1f} pips within tolerance")

    # Determine entry price based on side
    if side == PlanSide.LONG:
        entry_price = ask if ask and ask > 0 else current_price
    else:
        entry_price = bid if bid and bid > 0 else current_price

    entry_price = spec.round_price(entry_price)

    evidence.append(f"Entry price {entry_price} ({side.value})")

    return EntryPlan(
        state=EntryState.ENTRY_READY,
        entry_type=EntryType.MARKET,
        entry_price=entry_price,
        reason="Entry conditions satisfied",
        evidence=evidence,
    )
