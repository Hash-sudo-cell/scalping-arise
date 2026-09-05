"""
Scalping Arise — Impact Classification

Deterministic impact classification for external events.
Normalizes provider-supplied impact or applies configurable rules.
"""

from __future__ import annotations

from app.modules.news_intelligence.config import NewsIntelligenceSettings, get_news_intelligence_settings
from app.modules.news_intelligence.models import EventImpact, NormalizedEvent


def classify_impact(
    event: NormalizedEvent,
    settings: NewsIntelligenceSettings | None = None,
) -> EventImpact:
    """
    Classify the impact level of an event.

    If the event already has a classified impact (not UNKNOWN), use it.
    Otherwise, classify based on category and title keywords.
    """
    settings = settings or get_news_intelligence_settings()

    # If already classified by provider, normalize and return
    if event.impact != EventImpact.UNKNOWN:
        return _normalize_impact(event.impact)

    # Classify from category
    category_lower = event.category.lower()
    high_categories = {c.lower() for c in settings.high_impact_categories}

    if category_lower in high_categories:
        return EventImpact.HIGH

    # Classify from title keywords
    title_lower = event.title.lower()
    high_keywords = {
        "fomc", "federal reserve", "fed rate", "interest rate",
        "non-farm", "nfp", "payroll", "cpi", "inflation",
        "gdp", "unemployment", "retail sales", "ppi",
        "geopolitical", "war", "sanctions", "crisis",
        "rate decision", "monetary policy",
    }
    medium_keywords = {
        "trade balance", "consumer confidence", "pmi",
        "manufacturing", "services", "housing",
        "speech", "testimony", "minutes",
        "bond auction", "treasury",
    }

    for kw in high_keywords:
        if kw in title_lower:
            return EventImpact.HIGH

    for kw in medium_keywords:
        if kw in title_lower:
            return EventImpact.MEDIUM

    return EventImpact.LOW


def _normalize_impact(impact: EventImpact) -> EventImpact:
    """Ensure impact is one of the valid levels."""
    if impact in (EventImpact.LOW, EventImpact.MEDIUM, EventImpact.HIGH):
        return impact
    return EventImpact.UNKNOWN
