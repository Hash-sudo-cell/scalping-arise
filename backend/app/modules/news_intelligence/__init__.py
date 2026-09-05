"""
Scalping Arise — News Intelligence Module

Phase 8: News, Event & Performance Intelligence.
"""

from app.modules.news_intelligence.config import (
    NewsIntelligenceSettings,
    get_news_intelligence_settings,
)
from app.modules.news_intelligence.event_freshness import check_event_freshness
from app.modules.news_intelligence.event_normalizer import normalize_event
from app.modules.news_intelligence.event_provider import EventProvider, MockEventProvider
from app.modules.news_intelligence.event_relevance import assess_relevance
from app.modules.news_intelligence.event_risk_filter import evaluate_event_risk
from app.modules.news_intelligence.impact_classification import classify_impact
from app.modules.news_intelligence.models import (
    EventDataStatus,
    EventDecision,
    EventImpact,
    EventRelevance,
    EventRiskResult,
    FailPolicy,
    IntelligenceContext,
    IntelligenceDecision,
    NormalizedEvent,
    OverallDecision,
    RecoveryState,
    StrategyPerformanceMetrics,
    StrategyPerformanceState,
    StrategyStateRecord,
    TradeOutcome,
)
from app.modules.news_intelligence.performance_tracker import PerformanceTracker
from app.modules.news_intelligence.service import NewsIntelligenceService
from app.modules.news_intelligence.strategy_state import (
    create_initial_state,
    evaluate_strategy_state,
)
from app.modules.news_intelligence.unified_decision import synthesize_decision

__all__ = [
    # Service
    "NewsIntelligenceService",
    # Config
    "NewsIntelligenceSettings",
    "get_news_intelligence_settings",
    # Provider
    "EventProvider",
    "MockEventProvider",
    # Models
    "EventDataStatus",
    "EventDecision",
    "EventImpact",
    "EventRelevance",
    "EventRiskResult",
    "FailPolicy",
    "IntelligenceContext",
    "IntelligenceDecision",
    "NormalizedEvent",
    "OverallDecision",
    "RecoveryState",
    "StrategyPerformanceMetrics",
    "StrategyPerformanceState",
    "StrategyStateRecord",
    "TradeOutcome",
    # Functions
    "assess_relevance",
    "check_event_freshness",
    "classify_impact",
    "create_initial_state",
    "evaluate_event_risk",
    "evaluate_strategy_state",
    "normalize_event",
    "synthesize_decision",
]
