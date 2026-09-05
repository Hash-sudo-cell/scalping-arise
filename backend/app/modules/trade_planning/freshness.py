"""
Scalping Arise — Market Data Freshness Gate

Validates that market data is fresh enough for trade planning.
Stale data leads to invalid plans.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.models import FreshnessCheck


def check_data_freshness(
    *,
    latest_timestamp: Optional[datetime],
    source: str = "",
    settings: Optional[TradePlanningSettings] = None,
) -> FreshnessCheck:
    """
    Check if market data is fresh enough for trade planning.

    Uses the latest data timestamp to calculate age.
    """
    settings = settings or get_trade_planning_settings()

    if latest_timestamp is None:
        return FreshnessCheck(
            is_fresh=False,
            age_seconds=999999,
            max_age_seconds=settings.freshness_max_age_seconds,
            source=source,
            reason="No timestamp available",
        )

    # Ensure UTC
    if latest_timestamp.tzinfo is None:
        latest_timestamp = latest_timestamp.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age = int((now - latest_timestamp).total_seconds())
    max_age = settings.freshness_max_age_seconds

    is_fresh = age <= max_age

    return FreshnessCheck(
        is_fresh=is_fresh,
        age_seconds=age,
        max_age_seconds=max_age,
        source=source,
        reason="" if is_fresh else f"Data age {age}s exceeds maximum {max_age}s",
    )
