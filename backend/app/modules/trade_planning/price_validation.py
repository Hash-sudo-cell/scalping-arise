"""
Scalping Arise — Price & Tick Validation

Validates current price data for correctness, tick alignment,
spread reasonableness, and staleness.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.instrument_specs import get_spec_or_raise
from app.modules.trade_planning.models import PriceTickCheck


def validate_price(
    *,
    current_price: float,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    timestamp: Optional[datetime] = None,
    instrument: str,
    settings: Optional[TradePlanningSettings] = None,
) -> PriceTickCheck:
    """
    Validate current price data.

    Checks:
    1. Price is positive
    2. Price is tick-aligned
    3. Bid/ask spread is reasonable
    4. Price data is not stale
    """
    settings = settings or get_trade_planning_settings()
    spec = get_spec_or_raise(instrument)

    # Basic validity
    if current_price <= 0:
        return PriceTickCheck(
            is_valid=False,
            current_price=0.0,
            reason=f"Price {current_price} is not positive",
        )

    if not (current_price == current_price):  # NaN check
        return PriceTickCheck(
            is_valid=False,
            current_price=0.0,
            reason="Price is NaN",
        )

    # Tick alignment
    tick_aligned = spec.is_tick_aligned(current_price)

    # Spread check
    spread_pips: Optional[float] = None
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        if ask < bid:
            return PriceTickCheck(
                is_valid=False,
                current_price=current_price,
                bid=bid,
                ask=ask,
                reason=f"Ask ({ask}) is less than bid ({bid})",
            )
        spread_pips = spec.pip_distance(bid, ask)

        # Reasonable spread check (max 10x typical)
        if spread_pips > spec.typical_spread_pips * 10 and spec.typical_spread_pips > 0:
            return PriceTickCheck(
                is_valid=False,
                current_price=current_price,
                bid=bid,
                ask=ask,
                spread_pips=spread_pips,
                tick_aligned=tick_aligned,
                reason=f"Spread {spread_pips:.1f} pips exceeds 10x typical ({spec.typical_spread_pips})",
            )

    # Age check
    price_age: Optional[int] = None
    if timestamp is not None:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        price_age = int((now - timestamp).total_seconds())
        if price_age > settings.price_max_age_seconds:
            return PriceTickCheck(
                is_valid=False,
                current_price=current_price,
                bid=bid,
                ask=ask,
                spread_pips=spread_pips,
                tick_aligned=tick_aligned,
                price_age_seconds=price_age,
                reason=f"Price age {price_age}s exceeds maximum {settings.price_max_age_seconds}s",
            )

    return PriceTickCheck(
        is_valid=True,
        current_price=current_price,
        bid=bid,
        ask=ask,
        spread_pips=spread_pips,
        tick_aligned=tick_aligned,
        price_age_seconds=price_age,
    )
