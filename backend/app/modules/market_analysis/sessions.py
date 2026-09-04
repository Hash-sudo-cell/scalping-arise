"""
Scalping Arise — Market Session Classification

Deterministic session classification based on UTC timestamps.
Session boundaries are configuration-driven.

Supported sessions:
    ASIAN, LONDON, NEW_YORK, OVERLAP, OFF_SESSION
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.modules.market_analysis.config import MarketAnalysisSettings, get_market_analysis_settings
from app.modules.market_analysis.models import MarketSession

logger = logging.getLogger(__name__)


def classify_session(
    timestamp: datetime,
    settings: MarketAnalysisSettings | None = None,
) -> MarketSession:
    """
    Classify a UTC timestamp into a market session.

    Session rules (all hours in UTC):
        - OVERLAP: London and New York both open
        - LONDON: London open, New York closed
        - NEW_YORK: New York open, London closed
        - ASIAN: Asian session hours
        - OFF_SESSION: None of the above

    Args:
        timestamp: UTC datetime to classify.
        settings: Optional settings override (uses defaults if None).

    Returns:
        MarketSession classification.
    """
    cfg = settings or get_market_analysis_settings()
    hour = timestamp.hour

    london_open = cfg.session_london_start <= hour < cfg.session_london_end
    ny_open = cfg.session_newyork_start <= hour < cfg.session_newyork_end
    asian_open = cfg.session_asian_start <= hour < cfg.session_asian_end

    # Overlap: both London and New York open
    if london_open and ny_open:
        return MarketSession.OVERLAP

    if london_open:
        return MarketSession.LONDON

    if ny_open:
        return MarketSession.NEW_YORK

    if asian_open:
        return MarketSession.ASIAN

    return MarketSession.OFF_SESSION
