"""
Scalping Arise — News Intelligence Service

Orchestrates the full Phase 8 intelligence pipeline:
  Provider → Normalizer → Relevance → Impact → Risk Filter → State Machine → Unified Decision

Single entry point: `get_intelligence_decision(instrument, signal_id, strategy_id)`

Does NOT implement execution, backtesting, or optimization.
Pure intelligence/risk-context layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.modules.news_intelligence.config import NewsIntelligenceSettings, get_news_intelligence_settings
from app.modules.news_intelligence.event_freshness import check_event_freshness
from app.modules.news_intelligence.event_normalizer import normalize_event
from app.modules.news_intelligence.event_provider import EventProvider, MockEventProvider
from app.modules.news_intelligence.event_relevance import assess_relevance
from app.modules.news_intelligence.event_risk_filter import evaluate_event_risk
from app.modules.news_intelligence.impact_classification import classify_impact
from app.modules.news_intelligence.models import (
    EventDecision,
    EventDataStatus,
    EventFreshness,
    EventIntelligenceSummaryAgg,
    EventRiskResult,
    FailPolicy,
    IntelligenceContext,
    IntelligenceDecision,
    NormalizedEvent,
    OverallDecision,
    StrategyPerformanceMetrics,
    StrategyPerformanceState,
    StrategyStateRecord,
    TradeOutcome,
)
from app.modules.news_intelligence.performance_tracker import PerformanceTracker
from app.modules.news_intelligence.strategy_state import (
    create_initial_state,
    evaluate_strategy_state,
)
from app.modules.news_intelligence.unified_decision import synthesize_decision


class NewsIntelligenceService:
    """
    Orchestrates the full Phase 8 intelligence pipeline.

    Pipeline:
        1. Fetch raw events from provider
        2. Normalize events
        3. Classify impact
        4. Assess relevance
        5. Evaluate risk per event
        6. Aggregate event intelligence
        7. Check event data freshness
        8. Evaluate strategy performance state
        9. Synthesize unified decision
    """

    def __init__(
        self,
        provider: EventProvider | None = None,
        settings: NewsIntelligenceSettings | None = None,
    ) -> None:
        self._settings = settings or get_news_intelligence_settings()
        self._provider = provider or MockEventProvider()
        self._performance_tracker = PerformanceTracker(settings=self._settings)
        self._strategy_states: dict[str, StrategyStateRecord] = {}
        self._raw_events: list[dict] = []

    # ------------------------------------------------------------------
    # Strategy Performance Recording
    # ------------------------------------------------------------------

    def record_trade_outcome(self, outcome: TradeOutcome) -> None:
        """Record a realized trade outcome for performance tracking."""
        self._performance_tracker.record_outcome(outcome)
        # Trigger state evaluation
        self._update_strategy_state(outcome.strategy_id)

    def get_strategy_state(self, strategy_id: str) -> StrategyStateRecord:
        """Get current state for a strategy."""
        if strategy_id not in self._strategy_states:
            self._strategy_states[strategy_id] = create_initial_state(strategy_id)
        return self._strategy_states[strategy_id]

    def get_strategy_metrics(self, strategy_id: str) -> StrategyPerformanceMetrics:
        """Get computed performance metrics for a strategy."""
        return self._performance_tracker.compute_metrics(strategy_id)

    def clear_strategy_outcomes(self, strategy_id: str | None = None) -> None:
        """Clear outcomes for a strategy or all strategies."""
        self._performance_tracker.clear(strategy_id)
        if strategy_id:
            self._strategy_states.pop(strategy_id, None)
        else:
            self._strategy_states.clear()

    # ------------------------------------------------------------------
    # Raw Event Ingestion
    # ------------------------------------------------------------------

    def ingest_raw_events(self, events: list[dict]) -> None:
        """
        Ingest raw event dicts for processing.

        Call this when you have raw event data from external sources.
        """
        self._raw_events.extend(events)

    def clear_events(self) -> None:
        """Clear all stored raw events."""
        self._raw_events.clear()

    # ------------------------------------------------------------------
    # Intelligence Pipeline
    # ------------------------------------------------------------------

    async def get_intelligence_decision(
        self,
        instrument: str,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
    ) -> IntelligenceDecision:
        """
        Run the full intelligence pipeline and produce a unified decision.

        Args:
            instrument: Target instrument (e.g. "XAU/USD").
            signal_id: Optional signal ID for context.
            strategy_id: Optional strategy ID for performance context.

        Returns:
            IntelligenceDecision with overall decision, reasons, and restrictions.
        """
        # 1. Fetch events from provider
        provider_events = await self._fetch_events(instrument)

        # 2. Normalize raw events
        all_normalized = provider_events + [
            normalize_event(raw, source="ingested") for raw in self._raw_events
        ]

        # 3. Check freshness
        freshness = await self._check_freshness()

        # 4. Process events → relevance → impact → risk
        risk_results = self._process_events(all_normalized, instrument)

        # 5. Aggregate event intelligence
        event_summary = self._aggregate_events(risk_results, freshness)

        # 6. Get strategy state
        strategy_record = None
        if strategy_id:
            strategy_record = self.get_strategy_state(strategy_id)

        # 7. Build context
        context = IntelligenceContext(
            event_summary=event_summary,
            strategy_state=strategy_record,
            event_data_status=freshness.status,
            fallback_policy=self._settings.event_fail_policy,
        )

        # 8. Synthesize unified decision
        return synthesize_decision(
            instrument=instrument,
            context=context,
            signal_id=signal_id,
            strategy_id=strategy_id,
            settings=self._settings,
        )

    # ------------------------------------------------------------------
    # Private Pipeline Steps
    # ------------------------------------------------------------------

    async def _fetch_events(self, instrument: str) -> list[NormalizedEvent]:
        """Fetch events from the provider."""
        try:
            raw_events = await self._provider.fetch_events(instrument=instrument)
            return raw_events
        except Exception:
            return []

    async def _check_freshness(self) -> EventFreshness:
        """Check event data freshness."""
        try:
            last_update = await self._provider.get_latest_update_time()
            return check_event_freshness(last_update, settings=self._settings)
        except Exception:
            return EventFreshness(
                status=EventDataStatus.UNAVAILABLE,
                data_age_seconds=999999,
                max_age_seconds=self._settings.event_data_max_age_seconds,
                reason="Provider freshness check failed",
            )

    def _process_events(
        self,
        events: list[NormalizedEvent],
        instrument: str,
    ) -> list[EventRiskResult]:
        """Process events through relevance → impact → risk filter."""
        now = datetime.now(timezone.utc)
        results: list[EventRiskResult] = []

        for event in events:
            # Classify impact
            event.impact = classify_impact(event, settings=self._settings)

            # Assess relevance
            relevance = assess_relevance(event, instrument, settings=self._settings)

            # Evaluate risk
            risk = evaluate_event_risk(
                event, relevance, now=now, settings=self._settings,
            )
            results.append(risk)

        return results

    def _aggregate_events(
        self,
        risk_results: list[EventRiskResult],
        freshness: EventFreshness,
    ) -> EventIntelligenceSummaryAgg:
        """Aggregate event risk results into a summary."""
        total = len(risk_results)
        relevant = sum(1 for r in risk_results if r.relevance.value == "relevant")
        high_impact = sum(
            1 for r in risk_results
            if r.event.impact.value == "high"
        )

        # Worst decision wins
        decisions = [r.decision for r in risk_results]
        if EventDecision.BLOCK in decisions:
            agg_decision = EventDecision.BLOCK
        elif EventDecision.RESTRICT in decisions:
            agg_decision = EventDecision.RESTRICT
        else:
            agg_decision = EventDecision.ALLOW

        reasons = []
        for r in risk_results:
            reasons.extend(r.reasons)

        return EventIntelligenceSummaryAgg(
            total_events=total,
            relevant_events=relevant,
            high_impact_events=high_impact,
            event_decision=agg_decision,
            freshness=freshness,
            risk_results=risk_results,
            reasons=reasons,
        )

    def _update_strategy_state(self, strategy_id: str) -> None:
        """Update strategy state after a new outcome is recorded."""
        metrics = self._performance_tracker.compute_metrics(strategy_id)
        current = self.get_strategy_state(strategy_id)

        new_state, new_recovery, reasons = evaluate_strategy_state(
            strategy_id=strategy_id,
            metrics=metrics,
            current_state=current.state,
            recovery_state=current.recovery_state,
            settings=self._settings,
        )

        current.state = new_state
        current.recovery_state = new_recovery
        current.metrics = metrics
        current.sample_size = metrics.total_trades
        current.state_reasons = reasons
        current.last_evaluation = datetime.now(timezone.utc)

        if new_state != current.state:
            current.last_state_change = datetime.now(timezone.utc)
