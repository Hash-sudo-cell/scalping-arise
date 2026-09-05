"""
Scalping Arise — Phase 8: News, Event & Performance Intelligence Tests

Comprehensive deterministic tests for the Phase 8 module.
No network access. All external dependencies mocked.
Target: ~110+ tests covering all Phase 8 components.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from app.modules.news_intelligence.config import (
    NewsIntelligenceSettings,
    get_news_intelligence_settings,
)
from app.modules.news_intelligence.event_freshness import check_event_freshness
from app.modules.news_intelligence.event_normalizer import normalize_event
from app.modules.news_intelligence.event_provider import MockEventProvider
from app.modules.news_intelligence.event_relevance import assess_relevance
from app.modules.news_intelligence.event_risk_filter import evaluate_event_risk
from app.modules.news_intelligence.impact_classification import classify_impact
from app.modules.news_intelligence.models import (
    EventDataStatus,
    EventDecision,
    EventFreshness,
    EventImpact,
    EventIntelligenceSummaryAgg,
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


# ===================================================================
# Fixtures
# ===================================================================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_event(
    *,
    impact: EventImpact = EventImpact.HIGH,
    relevance_instruments: list[str] | None = None,
    relevance_currencies: list[str] | None = None,
    category: str = "central_bank",
    title: str = "FOMC Rate Decision",
    timestamp: Optional[datetime] = None,
    event_id: str | None = None,
) -> NormalizedEvent:
    """Create a normalized event fixture."""
    return NormalizedEvent(
        event_id=event_id or str(uuid.uuid4()),
        timestamp=timestamp or _now(),
        title=title,
        description="Test event",
        source="test",
        category=category,
        impact=impact,
        affected_instruments=relevance_instruments or [],
        affected_currencies=relevance_currencies or [],
        created_at=_now(),
    )


def _make_settings(**overrides) -> NewsIntelligenceSettings:
    """Create settings with optional overrides."""
    defaults = {
        "intelligence_enabled": True,
        "event_data_max_age_seconds": 300,
        "event_pre_window_seconds": 1800,
        "event_post_window_seconds": 1800,
        "event_medium_pre_window_seconds": 600,
        "event_medium_post_window_seconds": 600,
        "event_fail_policy": FailPolicy.FAIL_CLOSED,
        "relevant_currencies": ["USD", "XAU", "GOLD"],
        "high_impact_categories": ["central_bank", "interest_rate", "employment", "inflation", "geopolitical"],
        "min_performance_sample": 20,
        "min_win_rate": 0.40,
        "max_drawdown_pct": 15.0,
        "max_consecutive_losses": 5,
        "min_profit_factor": 1.0,
        "recent_trades_window": 10,
        "recovery_min_sample": 10,
        "recovery_min_win_rate": 0.50,
        "recovery_max_drawdown_pct": 10.0,
        "recovery_min_profit_factor": 1.2,
    }
    defaults.update(overrides)
    return NewsIntelligenceSettings(**defaults)


def _make_trade_outcome(
    strategy_id: str = "test_strat",
    is_winner: bool = True,
    pnl: float = 10.0,
) -> TradeOutcome:
    return TradeOutcome(
        strategy_id=strategy_id,
        instrument="XAU/USD",
        direction="long",
        entry_price=2000.0,
        exit_price=2010.0 if is_winner else 1990.0,
        pnl=pnl if is_winner else -pnl,
        is_winner=is_winner,
    )


# ===================================================================
# Config Tests
# ===================================================================

class TestNewsIntelligenceSettings:
    def test_default_settings(self):
        settings = _make_settings()
        assert settings.intelligence_enabled is True
        assert settings.event_data_max_age_seconds == 300
        assert settings.event_fail_policy == FailPolicy.FAIL_CLOSED
        assert settings.min_performance_sample == 20

    def test_is_enabled_property(self):
        settings = _make_settings(intelligence_enabled=True)
        assert settings.is_enabled is True

    def test_settings_validation_min_win_rate(self):
        with pytest.raises(Exception):
            _make_settings(min_win_rate=1.5)

    def test_settings_validation_max_drawdown(self):
        with pytest.raises(Exception):
            _make_settings(max_drawdown_pct=150.0)


# ===================================================================
# Event Normalizer Tests
# ===================================================================

class TestEventNormalizer:
    def test_normalize_raw_event(self):
        raw = {
            "title": "NFP Release",
            "timestamp": "2026-01-15T13:30:00Z",
            "impact": "high",
            "category": "employment",
            "instruments": ["XAU/USD"],
            "currencies": ["USD"],
        }
        event = normalize_event(raw, source="test")
        assert event.title == "NFP Release"
        assert event.impact == EventImpact.HIGH
        assert event.source == "test"
        assert "XAU/USD" in event.affected_instruments
        assert "USD" in event.affected_currencies

    def test_normalize_missing_fields(self):
        raw = {"title": "Minimal Event"}
        event = normalize_event(raw)
        assert event.title == "Minimal Event"
        assert event.impact == EventImpact.UNKNOWN
        assert event.category == "general"
        assert event.affected_instruments == []
        assert event.affected_currencies == []

    def test_normalize_empty_dict(self):
        event = normalize_event({})
        assert event.title == "Unknown Event"
        assert event.impact == EventImpact.UNKNOWN

    def test_normalize_various_timestamps(self):
        # String format
        e1 = normalize_event({"timestamp": "2026-06-01 12:00:00"})
        assert e1.timestamp.year == 2026

        # Unix timestamp
        e2 = normalize_event({"timestamp": 1700000000})
        assert e2.timestamp.year >= 2023

        # ISO format with Z
        e3 = normalize_event({"timestamp": "2026-01-15T13:30:00Z"})
        assert e3.timestamp.hour == 13

    def test_normalize_impact_variations(self):
        assert normalize_event({"impact": "HIGH"}).impact == EventImpact.HIGH
        assert normalize_event({"impact": "med"}).impact == EventImpact.MEDIUM
        assert normalize_event({"impact": "minor"}).impact == EventImpact.LOW
        assert normalize_event({"impact": "unknown_value"}).impact == EventImpact.UNKNOWN

    def test_normalize_currencies_string(self):
        event = normalize_event({"currency": "USD,EUR"})
        assert "USD" in event.affected_currencies
        assert "EUR" in event.affected_currencies


# ===================================================================
# Impact Classification Tests
# ===================================================================

class TestImpactClassification:
    def test_high_impact_event(self):
        event = _make_event(category="central_bank", impact=EventImpact.UNKNOWN)
        assert classify_impact(event) == EventImpact.HIGH

    def test_medium_impact_from_category(self):
        event = _make_event(category="housing", impact=EventImpact.UNKNOWN, title="Housing Starts Report")
        assert classify_impact(event) == EventImpact.MEDIUM

    def test_high_impact_from_title(self):
        event = _make_event(title="Federal Reserve Rate Decision", impact=EventImpact.UNKNOWN)
        assert classify_impact(event) == EventImpact.HIGH

    def test_medium_impact_from_title(self):
        event = _make_event(title="Consumer Confidence Index", category="general", impact=EventImpact.UNKNOWN)
        assert classify_impact(event) == EventImpact.MEDIUM

    def test_low_impact_unknown_event(self):
        event = _make_event(title="Random Event", category="other", impact=EventImpact.UNKNOWN)
        assert classify_impact(event) == EventImpact.LOW

    def test_preserves_existing_impact(self):
        event = _make_event(impact=EventImpact.MEDIUM)
        assert classify_impact(event) == EventImpact.MEDIUM


# ===================================================================
# Event Relevance Tests
# ===================================================================

class TestEventRelevance:
    def test_relevant_by_instrument_match(self):
        event = _make_event(relevance_instruments=["XAU/USD"])
        assert assess_relevance(event, "XAU/USD") == EventRelevance.RELEVANT

    def test_relevant_by_currency_match(self):
        event = _make_event(relevance_currencies=["USD"])
        assert assess_relevance(event, "XAU/USD") == EventRelevance.RELEVANT

    def test_relevant_by_high_impact_category(self):
        event = _make_event(category="central_bank", relevance_currencies=[])
        assert assess_relevance(event, "XAU/USD") == EventRelevance.RELEVANT

    def test_not_relevant(self):
        event = _make_event(
            category="entertainment",
            relevance_instruments=["AAPL"],
            relevance_currencies=["GBP"],
        )
        assert assess_relevance(event, "XAU/USD") == EventRelevance.NOT_RELEVANT

    def test_unknown_when_no_data(self):
        event = _make_event(category="", relevance_instruments=[], relevance_currencies=[])
        assert assess_relevance(event, "XAU/USD") == EventRelevance.UNKNOWN

    def test_fuzzy_instrument_match(self):
        event = _make_event(relevance_instruments=["XAUUSD"])
        assert assess_relevance(event, "XAU/USD") == EventRelevance.RELEVANT


# ===================================================================
# Event Freshness Tests
# ===================================================================

class TestEventFreshness:
    def test_fresh_data(self):
        now = _now()
        freshness = check_event_freshness(now)
        assert freshness.status == EventDataStatus.FRESH

    def test_stale_data(self):
        old = _now() - timedelta(seconds=600)
        freshness = check_event_freshness(old)
        assert freshness.status == EventDataStatus.STALE

    def test_unavailable_data(self):
        freshness = check_event_freshness(None)
        assert freshness.status == EventDataStatus.UNAVAILABLE

    def test_just_at_boundary(self):
        settings = _make_settings(event_data_max_age_seconds=300)
        now = _now()
        freshness = check_event_freshness(now, settings)
        assert freshness.status == EventDataStatus.FRESH


# ===================================================================
# Event Risk Filter Tests
# ===================================================================

class TestEventRiskFilter:
    def test_not_relevant_always_allow(self):
        event = _make_event(impact=EventImpact.HIGH)
        result = evaluate_event_risk(event, EventRelevance.NOT_RELEVANT)
        assert result.decision == EventDecision.ALLOW

    def test_relevant_high_impact_in_window(self):
        now = _now()
        event_time = now + timedelta(minutes=10)
        event = _make_event(impact=EventImpact.HIGH, timestamp=event_time)
        result = evaluate_event_risk(event, EventRelevance.RELEVANT, now=now)
        assert result.decision == EventDecision.BLOCK
        assert result.within_pre_window is True

    def test_relevant_high_impact_outside_window(self):
        now = _now()
        event_time = now + timedelta(hours=2)
        event = _make_event(impact=EventImpact.HIGH, timestamp=event_time)
        result = evaluate_event_risk(event, EventRelevance.RELEVANT, now=now)
        assert result.decision == EventDecision.RESTRICT

    def test_relevant_medium_impact_in_window(self):
        now = _now()
        event_time = now + timedelta(minutes=5)
        event = _make_event(impact=EventImpact.MEDIUM, timestamp=event_time)
        result = evaluate_event_risk(event, EventRelevance.RELEVANT, now=now)
        assert result.decision == EventDecision.RESTRICT
        assert result.within_pre_window is True

    def test_relevant_medium_impact_outside_window(self):
        now = _now()
        event_time = now + timedelta(minutes=30)
        event = _make_event(impact=EventImpact.MEDIUM, timestamp=event_time)
        result = evaluate_event_risk(event, EventRelevance.RELEVANT, now=now)
        assert result.decision == EventDecision.ALLOW

    def test_relevant_low_impact_always_allow(self):
        now = _now()
        event_time = now + timedelta(minutes=5)
        event = _make_event(impact=EventImpact.LOW, timestamp=event_time)
        result = evaluate_event_risk(event, EventRelevance.RELEVANT, now=now)
        assert result.decision == EventDecision.ALLOW

    def test_unknown_relevance_high_impact_restrict(self):
        event = _make_event(impact=EventImpact.HIGH)
        result = evaluate_event_risk(event, EventRelevance.UNKNOWN)
        assert result.decision == EventDecision.RESTRICT

    def test_unknown_relevance_non_high_allow(self):
        event = _make_event(impact=EventImpact.LOW)
        result = evaluate_event_risk(event, EventRelevance.UNKNOWN)
        assert result.decision == EventDecision.ALLOW


# ===================================================================
# Strategy State Machine Tests
# ===================================================================

class TestStrategyState:
    def test_initial_state(self):
        state = create_initial_state("test_strat")
        assert state.state == StrategyPerformanceState.ACTIVE
        assert state.sample_size == 0

    def test_insufficient_sample_stays_monitored(self):
        metrics = StrategyPerformanceMetrics(
            strategy_id="test", total_trades=5, winning_trades=2, losing_trades=3,
            win_rate=0.4, net_pnl=-10, average_win=5, average_loss=-5,
            profit_factor=0.8, max_drawdown=5, consecutive_losses=2,
            recent_win_rate=0.4, recent_trades=5,
        )
        state, recovery, reasons = evaluate_strategy_state("test", metrics)
        assert state == StrategyPerformanceState.MONITORED
        assert any("Sample size" in r for r in reasons)

    def test_healthy_active_stays_active(self):
        settings = _make_settings(min_performance_sample=5)
        metrics = StrategyPerformanceMetrics(
            strategy_id="test", total_trades=10, winning_trades=7, losing_trades=3,
            win_rate=0.7, net_pnl=50, average_win=10, average_loss=-5,
            profit_factor=2.0, max_drawdown=3, consecutive_losses=1,
            recent_win_rate=0.7, recent_trades=10,
        )
        state, recovery, reasons = evaluate_strategy_state(
            "test", metrics, settings=settings,
        )
        assert state == StrategyPerformanceState.ACTIVE

    def test_low_win_rate_activates_monitored(self):
        settings = _make_settings(min_performance_sample=5)
        metrics = StrategyPerformanceMetrics(
            strategy_id="test", total_trades=10, winning_trades=3, losing_trades=7,
            win_rate=0.3, net_pnl=-50, average_win=10, average_loss=-5,
            profit_factor=1.1, max_drawdown=3, consecutive_losses=2,
            recent_win_rate=0.3, recent_trades=10,
        )
        state, recovery, reasons = evaluate_strategy_state(
            "test", metrics, settings=settings,
        )
        assert state == StrategyPerformanceState.MONITORED

    def test_multiple_thresholds_restricted(self):
        settings = _make_settings(min_performance_sample=5)
        metrics = StrategyPerformanceMetrics(
            strategy_id="test", total_trades=10, winning_trades=2, losing_trades=8,
            win_rate=0.2, net_pnl=-100, average_win=5, average_loss=-15,
            profit_factor=0.25, max_drawdown=20, consecutive_losses=6,
            recent_win_rate=0.2, recent_trades=10,
        )
        state, recovery, reasons = evaluate_strategy_state(
            "test", metrics, settings=settings,
        )
        assert state == StrategyPerformanceState.RESTRICTED

    def test_restricted_can_disable_on_severe(self):
        settings = _make_settings(min_performance_sample=5)
        metrics = StrategyPerformanceMetrics(
            strategy_id="test", total_trades=10, winning_trades=1, losing_trades=9,
            win_rate=0.1, net_pnl=-200, average_win=5, average_loss=-25,
            profit_factor=0.1, max_drawdown=30, consecutive_losses=9,
            recent_win_rate=0.1, recent_trades=10,
        )
        state, recovery, reasons = evaluate_strategy_state(
            "test", metrics,
            current_state=StrategyPerformanceState.RESTRICTED,
            settings=settings,
        )
        assert state == StrategyPerformanceState.DISABLED
        assert recovery == RecoveryState.DISABLED

    def test_disabled_recovery_evaluation(self):
        settings = _make_settings(min_performance_sample=5, recovery_min_sample=5)
        metrics = StrategyPerformanceMetrics(
            strategy_id="test", total_trades=12, winning_trades=7, losing_trades=5,
            win_rate=0.583, net_pnl=20, average_win=10, average_loss=-5,
            profit_factor=1.5, max_drawdown=5, consecutive_losses=1,
            recent_win_rate=0.6, recent_trades=10,
        )
        state, recovery, reasons = evaluate_strategy_state(
            "test", metrics,
            current_state=StrategyPerformanceState.DISABLED,
            recovery_state=RecoveryState.RECOVERY_EVALUATION,
            settings=settings,
        )
        assert state == StrategyPerformanceState.RESTRICTED
        assert recovery == RecoveryState.RESTRICTED

    def test_monitored_recovers_to_active(self):
        settings = _make_settings(min_performance_sample=5)
        metrics = StrategyPerformanceMetrics(
            strategy_id="test", total_trades=10, winning_trades=7, losing_trades=3,
            win_rate=0.7, net_pnl=50, average_win=10, average_loss=-5,
            profit_factor=2.0, max_drawdown=3, consecutive_losses=1,
            recent_win_rate=0.7, recent_trades=10,
        )
        state, recovery, reasons = evaluate_strategy_state(
            "test", metrics,
            current_state=StrategyPerformanceState.MONITORED,
            settings=settings,
        )
        assert state == StrategyPerformanceState.ACTIVE


# ===================================================================
# Performance Tracker Tests
# ===================================================================

class TestPerformanceTracker:
    def test_record_and_compute(self):
        tracker = PerformanceTracker()
        for i in range(10):
            tracker.record_outcome(_make_trade_outcome(is_winner=i % 2 == 0))
        metrics = tracker.compute_metrics("test_strat")
        assert metrics.total_trades == 10
        assert metrics.winning_trades == 5
        assert metrics.losing_trades == 5
        assert metrics.win_rate == 0.5

    def test_empty_metrics(self):
        tracker = PerformanceTracker()
        metrics = tracker.compute_metrics("nonexistent")
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0

    def test_consecutive_losses(self):
        tracker = PerformanceTracker()
        for _ in range(3):
            tracker.record_outcome(_make_trade_outcome(is_winner=True))
        for _ in range(4):
            tracker.record_outcome(_make_trade_outcome(is_winner=False, pnl=10.0))
        metrics = tracker.compute_metrics("test_strat")
        assert metrics.consecutive_losses == 4

    def test_max_drawdown(self):
        tracker = PerformanceTracker()
        tracker.record_outcome(_make_trade_outcome(is_winner=True, pnl=100))
        tracker.record_outcome(_make_trade_outcome(is_winner=False, pnl=150))
        tracker.record_outcome(_make_trade_outcome(is_winner=False, pnl=100))
        metrics = tracker.compute_metrics("test_strat")
        assert metrics.max_drawdown > 0

    def test_profit_factor(self):
        tracker = PerformanceTracker()
        for _ in range(5):
            tracker.record_outcome(_make_trade_outcome(is_winner=True, pnl=20.0))
        for _ in range(2):
            tracker.record_outcome(_make_trade_outcome(is_winner=False, pnl=10.0))
        metrics = tracker.compute_metrics("test_strat")
        assert metrics.profit_factor == pytest.approx(5.0, rel=0.01)

    def test_clear(self):
        tracker = PerformanceTracker()
        tracker.record_outcome(_make_trade_outcome())
        tracker.clear("test_strat")
        assert tracker.compute_metrics("test_strat").total_trades == 0

    def test_clear_all(self):
        tracker = PerformanceTracker()
        tracker.record_outcome(_make_trade_outcome(strategy_id="a"))
        tracker.record_outcome(_make_trade_outcome(strategy_id="b"))
        tracker.clear()
        assert tracker.compute_metrics("a").total_trades == 0
        assert tracker.compute_metrics("b").total_trades == 0


# ===================================================================
# Unified Decision Engine Tests
# ===================================================================

class TestUnifiedDecision:
    def test_event_block_overrides_all(self):
        ctx = IntelligenceContext(
            event_summary=EventIntelligenceSummaryAgg(
                total_events=1, relevant_events=1, high_impact_events=1,
                event_decision=EventDecision.BLOCK, freshness=EventFreshness(
                    status=EventDataStatus.FRESH, data_age_seconds=10,
                    max_age_seconds=300,
                ),
            ),
            strategy_state=StrategyStateRecord(
                strategy_id="test", state=StrategyPerformanceState.ACTIVE, sample_size=10,
            ),
            event_data_status=EventDataStatus.FRESH,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert decision.overall_decision == OverallDecision.BLOCK

    def test_strategy_disabled_blocks(self):
        ctx = IntelligenceContext(
            event_summary=EventIntelligenceSummaryAgg(
                total_events=0, relevant_events=0, high_impact_events=0,
                event_decision=EventDecision.ALLOW, freshness=EventFreshness(
                    status=EventDataStatus.FRESH, data_age_seconds=10,
                    max_age_seconds=300,
                ),
            ),
            strategy_state=StrategyStateRecord(
                strategy_id="test", state=StrategyPerformanceState.DISABLED, sample_size=30,
            ),
            event_data_status=EventDataStatus.FRESH,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert decision.overall_decision == OverallDecision.BLOCK

    def test_both_restrict_blocks(self):
        ctx = IntelligenceContext(
            event_summary=EventIntelligenceSummaryAgg(
                total_events=1, relevant_events=1, high_impact_events=0,
                event_decision=EventDecision.RESTRICT, freshness=EventFreshness(
                    status=EventDataStatus.FRESH, data_age_seconds=10,
                    max_age_seconds=300,
                ),
            ),
            strategy_state=StrategyStateRecord(
                strategy_id="test", state=StrategyPerformanceState.RESTRICTED, sample_size=30,
            ),
            event_data_status=EventDataStatus.FRESH,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert decision.overall_decision == OverallDecision.BLOCK

    def test_event_restrict_only_restRICTS(self):
        ctx = IntelligenceContext(
            event_summary=EventIntelligenceSummaryAgg(
                total_events=1, relevant_events=1, high_impact_events=0,
                event_decision=EventDecision.RESTRICT, freshness=EventFreshness(
                    status=EventDataStatus.FRESH, data_age_seconds=10,
                    max_age_seconds=300,
                ),
            ),
            strategy_state=StrategyStateRecord(
                strategy_id="test", state=StrategyPerformanceState.ACTIVE, sample_size=10,
            ),
            event_data_status=EventDataStatus.FRESH,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert decision.overall_decision == OverallDecision.RESTRICT

    def test_strategy_restricted_only_restRICTS(self):
        ctx = IntelligenceContext(
            event_summary=EventIntelligenceSummaryAgg(
                total_events=0, relevant_events=0, high_impact_events=0,
                event_decision=EventDecision.ALLOW, freshness=EventFreshness(
                    status=EventDataStatus.FRESH, data_age_seconds=10,
                    max_age_seconds=300,
                ),
            ),
            strategy_state=StrategyStateRecord(
                strategy_id="test", state=StrategyPerformanceState.RESTRICTED, sample_size=30,
            ),
            event_data_status=EventDataStatus.FRESH,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert decision.overall_decision == OverallDecision.RESTRICT

    def test_all_clear_allows(self):
        ctx = IntelligenceContext(
            event_summary=EventIntelligenceSummaryAgg(
                total_events=0, relevant_events=0, high_impact_events=0,
                event_decision=EventDecision.ALLOW, freshness=EventFreshness(
                    status=EventDataStatus.FRESH, data_age_seconds=10,
                    max_age_seconds=300,
                ),
            ),
            strategy_state=StrategyStateRecord(
                strategy_id="test", state=StrategyPerformanceState.ACTIVE, sample_size=10,
            ),
            event_data_status=EventDataStatus.FRESH,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert decision.overall_decision == OverallDecision.ALLOW

    def test_fail_closed_restricts_on_unavailable(self):
        ctx = IntelligenceContext(
            event_data_status=EventDataStatus.UNAVAILABLE,
            fallback_policy=FailPolicy.FAIL_CLOSED,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert decision.overall_decision == OverallDecision.RESTRICT

    def test_fail_open_allows_on_unavailable(self):
        ctx = IntelligenceContext(
            event_data_status=EventDataStatus.UNAVAILABLE,
            fallback_policy=FailPolicy.FAIL_OPEN,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert decision.overall_decision == OverallDecision.ALLOW

    def test_monitored_strategy_includes_observation(self):
        ctx = IntelligenceContext(
            event_summary=EventIntelligenceSummaryAgg(
                total_events=0, relevant_events=0, high_impact_events=0,
                event_decision=EventDecision.ALLOW, freshness=EventFreshness(
                    status=EventDataStatus.FRESH, data_age_seconds=10,
                    max_age_seconds=300,
                ),
            ),
            strategy_state=StrategyStateRecord(
                strategy_id="test", state=StrategyPerformanceState.MONITORED, sample_size=15,
            ),
            event_data_status=EventDataStatus.FRESH,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert decision.overall_decision == OverallDecision.ALLOW
        assert any("monitored" in r.lower() for r in decision.restrictions)


# ===================================================================
# Service Integration Tests
# ===================================================================

class TestNewsIntelligenceService:
    def _make_service(
        self,
        provider_events: list[NormalizedEvent] | None = None,
        **settings_overrides,
    ) -> NewsIntelligenceService:
        provider = MockEventProvider(events=provider_events or [])
        settings = _make_settings(**settings_overrides)
        return NewsIntelligenceService(provider=provider, settings=settings)

    @pytest.mark.asyncio
    async def test_evaluate_empty_pipeline(self):
        service = self._make_service()
        decision = await service.get_intelligence_decision("XAU/USD")
        assert isinstance(decision, IntelligenceDecision)
        assert decision.instrument == "XAU/USD"

    @pytest.mark.asyncio
    async def test_evaluate_with_relevant_event(self):
        now = _now()
        event_time = now + timedelta(minutes=5)
        event = _make_event(
            impact=EventImpact.HIGH,
            relevance_instruments=["XAU/USD"],
            timestamp=event_time,
        )
        service = self._make_service(provider_events=[event])
        decision = await service.get_intelligence_decision("XAU/USD")
        assert decision.overall_decision == OverallDecision.BLOCK

    def test_strategy_performance_recording(self):
        service = self._make_service()
        for i in range(5):
            service.record_trade_outcome(_make_trade_outcome(is_winner=i % 2 == 0))
        state = service.get_strategy_state("test_strat")
        assert state.sample_size == 5

    def test_strategy_state_lifecycle(self):
        service = self._make_service(min_performance_sample=1, max_consecutive_losses=3)
        # Record 3 good trades (above min sample of 1)
        for _ in range(3):
            service.record_trade_outcome(_make_trade_outcome(is_winner=True, pnl=10.0))
        state = service.get_strategy_state("test_strat")
        assert state.state == StrategyPerformanceState.ACTIVE

        # Record 3 consecutive losses
        for _ in range(3):
            service.record_trade_outcome(_make_trade_outcome(is_winner=False, pnl=10.0))
        state = service.get_strategy_state("test_strat")
        # Should be at least monitored
        assert state.state in (
            StrategyPerformanceState.MONITORED,
            StrategyPerformanceState.RESTRICTED,
        )

    @pytest.mark.asyncio
    async def test_ingest_raw_events(self):
        service = self._make_service()
        service.ingest_raw_events([{
            "title": "Test Event",
            "impact": "low",
            "category": "general",
        }])
        decision = await service.get_intelligence_decision("XAU/USD")
        assert isinstance(decision, IntelligenceDecision)

    def test_clear_strategy_outcomes(self):
        service = self._make_service()
        service.record_trade_outcome(_make_trade_outcome())
        service.clear_strategy_outcomes("test_strat")
        assert service.get_strategy_metrics("test_strat").total_trades == 0

    @pytest.mark.asyncio
    async def test_provider_failure_returns_empty(self):
        provider = MockEventProvider()
        provider.set_available(False)
        service = NewsIntelligenceService(provider=provider)
        # Should not raise
        decision = await service.get_intelligence_decision("XAU/USD")
        assert isinstance(decision, IntelligenceDecision)


# ===================================================================
# Freshness Separate Mechanism Tests
# ===================================================================

class TestEventFreshnessSeparate:
    def test_fresh_vs_stale_distinction(self):
        """Event freshness is separate from market-data freshness."""
        now = _now()
        fresh = check_event_freshness(now)
        stale = check_event_freshness(now - timedelta(seconds=600))
        assert fresh.status == EventDataStatus.FRESH
        assert stale.status == EventDataStatus.STALE

    def test_unavailable_is_separate(self):
        """Unavailable is its own status, not STALE."""
        result = check_event_freshness(None)
        assert result.status == EventDataStatus.UNAVAILABLE


# ===================================================================
# Edge Case Tests
# ===================================================================

class TestEdgeCases:
    def test_event_id_uniqueness(self):
        e1 = _make_event()
        e2 = _make_event()
        assert e1.event_id != e2.event_id

    def test_zero_pnl_trade(self):
        outcome = TradeOutcome(
            strategy_id="test", instrument="XAU/USD", direction="long",
            entry_price=2000, exit_price=2000, pnl=0, is_winner=False,
        )
        tracker = PerformanceTracker()
        tracker.record_outcome(outcome)
        metrics = tracker.compute_metrics("test")
        assert metrics.total_trades == 1
        assert metrics.net_pnl == 0.0

    def test_all_winning_trades(self):
        tracker = PerformanceTracker()
        for _ in range(5):
            tracker.record_outcome(_make_trade_outcome(is_winner=True, pnl=20.0))
        metrics = tracker.compute_metrics("test_strat")
        assert metrics.consecutive_losses == 0
        assert metrics.win_rate == 1.0

    def test_all_losing_trades(self):
        tracker = PerformanceTracker()
        for _ in range(5):
            tracker.record_outcome(_make_trade_outcome(is_winner=False, pnl=10.0))
        metrics = tracker.compute_metrics("test_strat")
        assert metrics.consecutive_losses == 5
        assert metrics.win_rate == 0.0

    def test_decision_has_required_fields(self):
        ctx = IntelligenceContext(
            event_data_status=EventDataStatus.FRESH,
        )
        decision = synthesize_decision("XAU/USD", ctx, signal_id="sig1", strategy_id="strat1")
        assert decision.instrument == "XAU/USD"
        assert decision.signal_id == "sig1"
        assert decision.strategy_id == "strat1"
        assert decision.decision_id
        assert decision.timestamp

    def test_restricted_has_reasons(self):
        ctx = IntelligenceContext(
            event_summary=EventIntelligenceSummaryAgg(
                total_events=1, relevant_events=1, high_impact_events=0,
                event_decision=EventDecision.RESTRICT, freshness=EventFreshness(
                    status=EventDataStatus.FRESH, data_age_seconds=10,
                    max_age_seconds=300,
                ),
            ),
            event_data_status=EventDataStatus.FRESH,
        )
        decision = synthesize_decision("XAU/USD", ctx)
        assert len(decision.reasons) > 0

    def test_strategy_metrics_dict_fields(self):
        """Verify all StrategyPerformanceMetrics fields are accessible."""
        metrics = StrategyPerformanceMetrics(
            strategy_id="test", total_trades=10, winning_trades=6, losing_trades=4,
            win_rate=0.6, net_pnl=30, average_win=10, average_loss=-5,
            profit_factor=3.0, max_drawdown=5, consecutive_losses=2,
            recent_win_rate=0.5, recent_trades=8,
        )
        # Access all fields
        assert metrics.strategy_id == "test"
        assert metrics.total_trades == 10
        assert metrics.win_rate == 0.6
        assert metrics.profit_factor == 3.0
        assert metrics.consecutive_losses == 2

    def test_event_risk_result_has_reasons(self):
        event = _make_event(impact=EventImpact.HIGH)
        result = evaluate_event_risk(event, EventRelevance.RELEVANT, now=_now() - timedelta(hours=1))
        assert len(result.reasons) > 0

    def test_event_risk_result_timing_fields(self):
        now = _now()
        event_time = now + timedelta(minutes=10)
        event = _make_event(impact=EventImpact.HIGH, timestamp=event_time)
        result = evaluate_event_risk(event, EventRelevance.RELEVANT, now=now)
        assert result.minutes_until_event is not None
        assert result.minutes_until_event > 0

    def test_normalized_event_has_created_at(self):
        event = _make_event()
        assert event.created_at is not None
