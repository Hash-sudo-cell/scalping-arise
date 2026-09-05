"""
Scalping Arise — Event Freshness

Separate freshness mechanism for external event/news data.
Distinct from Phase 2 market-data freshness.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.modules.news_intelligence.config import NewsIntelligenceSettings, get_news_intelligence_settings
from app.modules.news_intelligence.models import EventDataStatus, EventFreshness


def check_event_freshness(
    latest_update_time: Optional[datetime],
    settings: NewsIntelligenceSettings | None = None,
) -> EventFreshness:
    """
    Validate event data freshness.

    Returns EventFreshness with status FRESH, STALE, or UNAVAILABLE.
    """
    settings = settings or get_news_intelligence_settings()

    if latest_update_time is None:
        return EventFreshness(
            status=EventDataStatus.UNAVAILABLE,
            data_age_seconds=999999,
            max_age_seconds=settings.event_data_max_age_seconds,
            reason="No event data available from provider",
        )

    now = datetime.now(timezone.utc)
    if latest_update_time.tzinfo is None:
        latest_update_time = latest_update_time.replace(tzinfo=timezone.utc)

    age_seconds = int((now - latest_update_time).total_seconds())

    if age_seconds <= settings.event_data_max_age_seconds:
        return EventFreshness(
            status=EventDataStatus.FRESH,
            data_age_seconds=age_seconds,
            max_age_seconds=settings.event_data_max_age_seconds,
            reason=f"Event data is {age_seconds}s old (max: {settings.event_data_max_age_seconds}s)",
        )

    return EventFreshness(
        status=EventDataStatus.STALE,
        data_age_seconds=age_seconds,
        max_age_seconds=settings.event_data_max_age_seconds,
        reason=f"Event data is stale: {age_seconds}s old (max: {settings.event_data_max_age_seconds}s)",
    )
