"""
Scalping Arise — Event Risk Filter

Determines ALLOW / RESTRICT / BLOCK based on event impact,
relevance, timing, and protection windows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.modules.news_intelligence.config import NewsIntelligenceSettings, get_news_intelligence_settings
from app.modules.news_intelligence.models import (
    EventDecision,
    EventImpact,
    EventRelevance,
    EventRiskResult,
    NormalizedEvent,
)


def evaluate_event_risk(
    event: NormalizedEvent,
    relevance: EventRelevance,
    now: Optional[datetime] = None,
    settings: NewsIntelligenceSettings | None = None,
) -> EventRiskResult:
    """
    Evaluate the risk of a single event.

    Decision logic:
    - NOT_RELEVANT → ALLOW
    - RELEVANT + HIGH + inside window → BLOCK
    - RELEVANT + MEDIUM + inside window → RESTRICT
    - RELEVANT + HIGH + outside window → RESTRICT
    - RELEVANT + MEDIUM + outside window → ALLOW
    - RELEVANT + LOW → ALLOW
    - UNKNOWN relevance + HIGH impact → RESTRICT (cautious)
    - UNKNOWN relevance + non-HIGH → ALLOW
    """
    settings = settings or get_news_intelligence_settings()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    reasons: list[str] = []
    decision = EventDecision.ALLOW

    # Not relevant → always ALLOW
    if relevance == EventRelevance.NOT_RELEVANT:
        return EventRiskResult(
            event=event,
            relevance=relevance,
            decision=EventDecision.ALLOW,
            reasons=["Event not relevant to instrument"],
        )

    # Unknown relevance handling
    if relevance == EventRelevance.UNKNOWN:
        if event.impact == EventImpact.HIGH:
            return EventRiskResult(
                event=event,
                relevance=relevance,
                decision=EventDecision.RESTRICT,
                reasons=["UNKNOWN relevance with HIGH impact — restricting as precaution"],
            )
        return EventRiskResult(
            event=event,
            relevance=relevance,
            decision=EventDecision.ALLOW,
            reasons=["UNKNOWN relevance with non-HIGH impact — allowing"],
        )

    # RELEVANT — evaluate timing windows
    event_time = event.timestamp
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)

    minutes_until = (event_time - now).total_seconds() / 60.0
    minutes_since = -minutes_until

    # Determine protection windows based on impact
    if event.impact == EventImpact.HIGH:
        pre_seconds = settings.event_pre_window_seconds
        post_seconds = settings.event_post_window_seconds
    elif event.impact == EventImpact.MEDIUM:
        pre_seconds = settings.event_medium_pre_window_seconds
        post_seconds = settings.event_medium_post_window_seconds
    else:
        pre_seconds = 0
        post_seconds = 0

    within_pre = 0 <= minutes_until <= (pre_seconds / 60.0)
    within_post = 0 <= minutes_since <= (post_seconds / 60.0)
    within_window = within_pre or within_post

    # Decision based on impact + timing
    if event.impact == EventImpact.HIGH:
        if within_window:
            decision = EventDecision.BLOCK
            reasons.append("HIGH impact event within protection window")
        else:
            decision = EventDecision.RESTRICT
            reasons.append("HIGH impact event — outside window but still relevant")
    elif event.impact == EventImpact.MEDIUM:
        if within_window:
            decision = EventDecision.RESTRICT
            reasons.append("MEDIUM impact event within protection window")
        else:
            decision = EventDecision.ALLOW
            reasons.append("MEDIUM impact event — outside protection window")
    else:
        decision = EventDecision.ALLOW
        reasons.append(f"{event.impact.value.upper()} impact event — no restriction")

    return EventRiskResult(
        event=event,
        relevance=relevance,
        decision=decision,
        within_pre_window=within_pre,
        within_post_window=within_post,
        minutes_until_event=round(minutes_until, 1) if minutes_until > 0 else None,
        minutes_since_event=round(minutes_since, 1) if minutes_since > 0 else None,
        reasons=reasons,
    )
