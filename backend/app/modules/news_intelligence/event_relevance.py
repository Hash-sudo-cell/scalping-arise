"""
Scalping Arise — Event Relevance Engine

Determines whether an event is relevant to a specific instrument.
Uses explicit rules — no AI scoring, no silent assumptions.
"""

from __future__ import annotations

from app.modules.news_intelligence.config import NewsIntelligenceSettings, get_news_intelligence_settings
from app.modules.news_intelligence.models import EventRelevance, NormalizedEvent


def assess_relevance(
    event: NormalizedEvent,
    instrument: str,
    settings: NewsIntelligenceSettings | None = None,
) -> EventRelevance:
    """
    Determine event relevance to an instrument.

    Rules (evaluated in order):
    1. If event.affected_instruments contains the instrument → RELEVANT
    2. If event.affected_currencies overlap with instrument currencies → RELEVANT
    3. If event category is in high_impact_categories AND instrument is USD-denominated → RELEVANT
    4. Otherwise → NOT_RELEVANT

    Returns UNKNOWN only when insufficient data to make a determination.
    """
    settings = settings or get_news_intelligence_settings()

    # Extract currencies from instrument string (e.g. "XAU/USD" → ["XAU", "USD"])
    instrument_currencies = _extract_instrument_currencies(instrument)

    # Rule 1: Direct instrument match
    if event.affected_instruments:
        for affected in event.affected_instruments:
            if _fuzzy_instrument_match(affected, instrument):
                return EventRelevance.RELEVANT

    # Rule 2: Currency overlap
    if event.affected_currencies and instrument_currencies:
        event_currencies_upper = {c.upper() for c in event.affected_currencies}
        if event_currencies_upper & instrument_currencies:
            return EventRelevance.RELEVANT

    # Rule 3: High-impact category for USD instruments
    if "USD" in instrument_currencies:
        if event.category.lower() in {c.lower() for c in settings.high_impact_categories}:
            return EventRelevance.RELEVANT

    # Rule 4: Unknown if event has no structured data at all
    if not event.affected_instruments and not event.affected_currencies and not event.category:
        return EventRelevance.UNKNOWN

    return EventRelevance.NOT_RELEVANT


def _extract_instrument_currencies(instrument: str) -> set[str]:
    """
    Extract currency codes from an instrument string.

    Examples:
        XAU/USD → {XAU, USD}
        BTC/USD → {BTC, USD}
        EUR/USD → {EUR, USD}
        US30 → {USD}
    """
    normalized = instrument.upper().replace(" ", "")
    if "/" in normalized:
        parts = normalized.split("/")
        return {p for p in parts if p}
    # Single token — assume it's USD-related if it starts with USD
    if normalized.startswith("USD"):
        return {"USD", normalized}
    return {normalized}


def _fuzzy_instrument_match(affected: str, instrument: str) -> bool:
    """
    Fuzzy match between an affected instrument string and the target.

    Handles variations like "XAUUSD" matching "XAU/USD".
    """
    affected_clean = affected.upper().replace("/", "").replace(" ", "")
    instrument_clean = instrument.upper().replace("/", "").replace(" ", "")
    return affected_clean == instrument_clean
