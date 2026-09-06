"""
Scalping Arise — Decision Engine Service

Central orchestrator for Phase 10: Final Decision, Explainability
and Production Readiness.

This service is an orchestrator + safety layer. It does NOT:
  - Generate signals (Phase 6)
  - Plan trades (Phase 7)
  - Fetch market data (Phase 2)
  - Evaluate strategies (Phase 5)

It DOES:
  - Consume SignalRecord (Phase 6), TradePlan (Phase 7), IntelligenceDecision (Phase 8)
  - Run configurable gates against all inputs
  - Produce FinalDecision with full explainability, provenance, and audit trail

Flow:
    SignalRecord (Phase 6) ──────────┐
                                      │
    IntelligenceDecision (Phase 8) ──┤
                                      │
    TradePlan (Phase 7) ─────────────┤
                                      ├──→ Decision Engine Service
    System Readiness ────────────────┤         │
                                      │    Gate Engine
    Emergency Disable ───────────────┘         │
                                      State Machine
                                               │
                                      Explainability
                                               │
                                      Provenance
                                               │
                                      Audit Trail
                                               │
                                      FinalDecision
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from app.modules.decision.audit import AuditTrail
from app.modules.decision.config import DecisionEngineSettings, get_decision_engine_settings
from app.modules.decision.conflict_check import detect_conflicts
from app.modules.decision.emergency import EmergencyController
from app.modules.decision.explainability import (
    add_plan_context,
    add_signal_context,
    build_explainability,
)
from app.modules.decision.expiration import (
    cleanup_expired,
    get_remaining_ttl,
    set_expiration,
)
from app.modules.decision.gate_engine import GateEngine
from app.modules.decision.idempotency import IdempotencyCache
from app.modules.decision.models import (
    AuditAction,
    FinalDecision,
    FinalDecisionDirection,
    FinalDecisionState,
    GateStatus,
    MonitoringCounters,
)
from app.modules.decision.monitoring import MonitoringService
from app.modules.decision.provenance import (
    attach_provenance,
    record_contribution,
)
from app.modules.decision.retention import enforce_retention
from app.modules.decision.state_machine import (
    transition_decision,
    transition_to_terminal,
)
from app.modules.market_data.service import MarketDataService

logger = logging.getLogger(__name__)


class DecisionEngineService:
    """
    Central decision engine orchestration service.

    Consumes Phase 6 signals, Phase 7 plans, and Phase 8 intelligence
    to produce a unified FinalDecision with full traceability.
    """

    def __init__(
        self,
        settings: Optional[DecisionEngineSettings] = None,
        market_data_service: Optional[MarketDataService] = None,
    ) -> None:
        self._settings = settings or get_decision_engine_settings()
        self._market_data = market_data_service

        # Sub-components
        self._gate_engine = GateEngine(settings=self._settings)
        self._audit = AuditTrail(max_entries=self._settings.audit_max_entries)
        self._idempotency = IdempotencyCache(
            max_size=self._settings.idempotency_cache_size,
            ttl_seconds=self._settings.idempotency_ttl_seconds,
        )
        self._monitoring = MonitoringService()
        self._emergency = EmergencyController(
            initial_state=self._settings.emergency_disable,
        )

        # Decision storage (ring buffer)
        self._history: deque[FinalDecision] = deque(
            maxlen=self._settings.decision_history_max_size,
        )
        self._active: deque[FinalDecision] = deque(
            maxlen=self._settings.active_decisions_max_size,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate_decision(
        self,
        *,
        signal_id: str,
        instrument: str = "XAU/USD",
        signal_direction: Optional[str] = None,
        signal_confidence: Optional[int] = None,
        signal_quality: Optional[int] = None,
        signal_age_seconds: Optional[float] = None,
        plan_id: Optional[str] = None,
        plan_valid: Optional[bool] = None,
        plan_state: Optional[str] = None,
        plan_side: Optional[str] = None,
        plan_risk_reward: Optional[float] = None,
        plan_within_risk_limits: Optional[bool] = None,
        plan_age_seconds: Optional[float] = None,
        intelligence_id: Optional[str] = None,
        event_decision: Optional[str] = None,
        strategy_performance_state: Optional[str] = None,
        force: bool = False,
        system_ready: Optional[bool] = None,
    ) -> FinalDecision:
        """
        Run the full decision pipeline for a signal.

        This is the main entry point. It:
        1. Checks emergency disable
        2. Checks idempotency
        3. Creates a FinalDecision in EVALUATING state
        4. Records provenance
        5. Runs the gate engine
        6. Detects conflicts
        7. Builds explainability
        8. Transitions to the final state
        9. Records audit trail
        10. Updates monitoring counters

        Args:
            signal_id: Phase 6 signal ID.
            instrument: Instrument being traded.
            signal_direction: Signal direction (buy/sell).
            signal_confidence: Signal confidence (0-100).
            signal_quality: Signal quality (0-100).
            signal_age_seconds: How old the signal is.
            plan_id: Phase 7 trade plan ID.
            plan_valid: Whether the plan is valid.
            plan_state: Plan lifecycle state.
            plan_side: Plan side (long/short).
            plan_risk_reward: Plan risk:reward ratio.
            plan_within_risk_limits: Whether plan is within risk limits.
            plan_age_seconds: How old the plan is.
            intelligence_id: Phase 8 intelligence decision ID.
            event_decision: Event risk decision (allow/restrict/block).
            strategy_performance_state: Strategy state (active/monitored/restricted/disabled).
            force: Force re-evaluation even if idempotent.
            system_ready: Override for system readiness check. If None, the real readiness check runs.

        Returns:
            FinalDecision with full traceability.
        """
        t_start = __import__("time").monotonic()

        # ----------------------------------------------------------
        # 1. Emergency disable check
        # ----------------------------------------------------------
        if self._emergency.is_disabled:
            decision = FinalDecision(
                signal_id=signal_id,
                instrument=instrument,
                state=FinalDecisionState.BLOCKED,
                direction=FinalDecisionDirection.NONE,
                rejection_reason="Emergency disable is active",
                blocked_by_gate=None,
            )
            self._audit.record_creation(decision)
            self._audit.record_emergency(True, self._emergency.last_reason)
            self._history.append(decision)
            self._monitoring.record_evaluation(state="blocked")
            self._monitoring.record_emergency_toggle()
            return decision

        # ----------------------------------------------------------
        # 2. Idempotency check
        # ----------------------------------------------------------
        idem_key = self._idempotency.compute_key(signal_id, plan_id, intelligence_id)
        if not force:
            cached_id = self._idempotency.lookup(idem_key)
            if cached_id is not None:
                # Return the cached decision
                self._monitoring.record_idempotency_hit()
                for d in self._history:
                    if d.decision_id == cached_id:
                        return d
                # Cache stale — fall through to re-evaluate
            else:
                self._monitoring.record_idempotency_miss()

        # ----------------------------------------------------------
        # 3. Create decision in EVALUATING state
        # ----------------------------------------------------------
        decision = FinalDecision(
            signal_id=signal_id,
            instrument=instrument,
            idempotency_key=idem_key,
        )
        self._audit.record_creation(decision)

        # Set expiration
        set_expiration(decision, self._settings.decision_ttl_seconds)

        # ----------------------------------------------------------
        # 4. Provenance
        # ----------------------------------------------------------
        provenance = attach_provenance(decision)
        record_contribution(
            provenance,
            __import__("app.modules.decision.models", fromlist=["ProvenanceSource"]).ProvenanceSource.DECISION_ENGINE,
            data_provided=["signal_id", "instrument"],
            healthy=True,
        )

        # Record signal engine contribution
        if signal_confidence is not None or signal_quality is not None:
            record_contribution(
                provenance,
                __import__("app.modules.decision.models", fromlist=["ProvenanceSource"]).ProvenanceSource.SIGNAL_ENGINE,
                data_provided=["confidence", "quality", "direction"],
                healthy=True,
            )

        # Record trade planning contribution
        if plan_valid is not None:
            record_contribution(
                provenance,
                __import__("app.modules.decision.models", fromlist=["ProvenanceSource"]).ProvenanceSource.TRADE_PLANNING,
                data_provided=["plan_valid", "risk_reward", "plan_side"],
                healthy=plan_valid is not None,
            )

        # Record intelligence contribution
        if event_decision is not None or strategy_performance_state is not None:
            record_contribution(
                provenance,
                __import__("app.modules.decision.models", fromlist=["ProvenanceSource"]).ProvenanceSource.NEWS_INTELLIGENCE,
                data_provided=["event_decision", "strategy_state"],
                healthy=True,
            )

        # ----------------------------------------------------------
        # 5. Conflict detection (pre-gate)
        # ----------------------------------------------------------
        conflict_report = detect_conflicts(
            signal_direction=signal_direction,
            plan_side=plan_side,
            signal_confidence=signal_confidence,
            plan_risk_reward=plan_risk_reward,
            event_decision=event_decision,
            strategy_state=strategy_performance_state,
            plan_within_risk_limits=plan_within_risk_limits,
            min_confidence=self._settings.min_signal_confidence,
            min_rr=self._settings.min_risk_reward,
        )
        decision.conflicts = conflict_report

        # ----------------------------------------------------------
        # 6. Gate engine evaluation
        # ----------------------------------------------------------
        from app.modules.decision.readiness import check_system_readiness_sync
        if system_ready is not None:
            # Use provided override
            readiness_ready = system_ready
        else:
            readiness_result = check_system_readiness_sync(self._settings)
            readiness_ready = readiness_result.ready

        gate_results = self._gate_engine.evaluate(
            signal_age_seconds=signal_age_seconds,
            signal_quality=signal_quality,
            signal_confidence=signal_confidence,
            event_decision=event_decision,
            strategy_performance_state=strategy_performance_state,
            plan_valid=plan_valid,
            plan_state=plan_state,
            plan_within_risk_limits=plan_within_risk_limits,
            plan_risk_reward=plan_risk_reward,
            plan_age_seconds=plan_age_seconds,
            system_ready=readiness_ready,
            has_conflicts=conflict_report.has_conflicts,
            conflict_severity=conflict_report.overall_severity,
        )
        decision.gates = gate_results

        # Count gates
        counts = self._gate_engine.count_gates(gate_results)
        decision.gates_passed = counts["passed"]
        decision.gates_failed = counts["failed"]
        decision.gates_total = counts["total"]

        # Record each gate in audit
        for gr in gate_results:
            self._audit.record_gate(decision, gr.gate, gr.status, gr.reason)

        # ----------------------------------------------------------
        # 7. Determine final state
        # ----------------------------------------------------------
        any_required_failed = self._gate_engine.any_required_failed(gate_results)

        if any_required_failed:
            # Find the first required gate that failed
            failed_gate = next(
                (gr for gr in gate_results if gr.status == GateStatus.FAILED),
                None,
            )
            decision.blocked_by_gate = failed_gate.gate if failed_gate else None
            decision.rejection_reason = failed_gate.reason if failed_gate else "Required gate failed"
            transition_decision(
                decision,
                FinalDecisionState.BLOCKED,
                reason=decision.rejection_reason,
            )
        else:
            # All required gates passed — determine direction
            if signal_direction and signal_direction.lower() in ("buy", "sell"):
                direction_val = signal_direction.lower()
                decision.direction = FinalDecisionDirection(direction_val)
                transition_decision(
                    decision,
                    FinalDecisionState.ACTIONABLE,
                    reason="All gates passed, signal actionable",
                )
            else:
                transition_decision(
                    decision,
                    FinalDecisionState.NO_TRADE,
                    reason="No clear directional signal",
                )

        # ----------------------------------------------------------
        # 8. Composite scores
        # ----------------------------------------------------------
        decision.confidence = signal_confidence or 0
        decision.quality = signal_quality or 0

        # ----------------------------------------------------------
        # 9. Explainability
        # ----------------------------------------------------------
        decision.explainability = build_explainability(
            decision,
            signal_direction=signal_direction,
            signal_instrument=instrument,
        )

        # ----------------------------------------------------------
        # 10. Store decision
        # ----------------------------------------------------------
        self._history.append(decision)
        if not self._is_terminal(decision.state):
            self._active.append(decision)

        # Store in idempotency cache
        self._idempotency.store(idem_key, decision.decision_id)

        # ----------------------------------------------------------
        # 11. Monitoring
        # ----------------------------------------------------------
        elapsed_ms = (__import__("time").monotonic() - t_start) * 1000
        gate_failure_counts = {}
        for gr in gate_results:
            if gr.status == GateStatus.FAILED:
                gate_failure_counts[gr.gate.value] = gate_failure_counts.get(gr.gate.value, 0) + 1

        self._monitoring.record_evaluation(
            state=decision.state.value,
            evaluation_ms=round(elapsed_ms, 3),
            gate_failures=gate_failure_counts if gate_failure_counts else None,
        )

        logger.info(
            "Decision %s: signal=%s state=%s direction=%s confidence=%d quality=%d gates=%d/%d (%.1fms)",
            decision.decision_id[:8],
            signal_id[:8] if len(signal_id) > 8 else signal_id,
            decision.state.value,
            decision.direction.value,
            decision.confidence,
            decision.quality,
            decision.gates_passed,
            decision.gates_total,
            elapsed_ms,
        )

        return decision

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_decision(self, decision_id: str) -> Optional[FinalDecision]:
        """Get a decision by ID."""
        for d in self._history:
            if d.decision_id == decision_id:
                return d
        return None

    def get_active_decisions(self) -> list[FinalDecision]:
        """Get all active (non-terminal) decisions, sorted by created_at descending."""
        self._cleanup_expired_active()
        return sorted(self._active, key=lambda d: d.created_at, reverse=True)

    def get_history(self, limit: int = 20) -> list[FinalDecision]:
        """Get recent decision history, most recent first."""
        return sorted(self._history, key=lambda d: d.created_at, reverse=True)[:limit]

    def invalidate_decision(self, decision_id: str, reason: str = "Manual invalidation") -> bool:
        """
        Manually invalidate a decision by ID.

        Returns True if the decision was found and invalidated.
        """
        decision = self.get_decision(decision_id)
        if decision is None:
            return False

        if self._is_terminal(decision.state):
            return False

        transition_to_terminal(
            decision,
            FinalDecisionState.INVALIDATED,
            reason=reason,
        )
        self._audit.record_invalidation(decision, reason)

        # Remove from active
        self._active = deque(
            [d for d in self._active if d.decision_id != decision_id],
            maxlen=self._settings.active_decisions_max_size,
        )

        return True

    # ------------------------------------------------------------------
    # Emergency
    # ------------------------------------------------------------------

    def emergency_disable(self, reason: str = "Manual emergency disable") -> dict:
        """Activate emergency disable."""
        self._emergency.disable(reason)
        self._audit.record_emergency(True, reason)
        self._monitoring.record_emergency_toggle()
        return self._emergency.get_status()

    def emergency_enable(self, reason: str = "Manual emergency enable") -> dict:
        """Deactivate emergency disable."""
        self._emergency.enable(reason)
        self._audit.record_emergency(False, reason)
        self._monitoring.record_emergency_toggle()
        return self._emergency.get_status()

    def get_emergency_status(self) -> dict:
        """Get the current emergency status."""
        return self._emergency.get_status()

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def get_audit_trail(self, decision_id: str) -> list[dict]:
        """Get the full audit trail for a decision."""
        entries = self._audit.get_for_decision(decision_id)
        return [e.model_dump(mode="json") for e in entries]

    def get_recent_audit(self, limit: int = 50) -> list[dict]:
        """Get recent audit entries."""
        entries = self._audit.get_recent(limit)
        return [e.model_dump(mode="json") for e in entries]

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    def get_monitoring_counters(self) -> MonitoringCounters:
        """Get the current monitoring counters."""
        return self._monitoring.counters

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    async def get_readiness(self) -> dict:
        """Get system readiness status."""
        from app.modules.decision.readiness import check_system_readiness
        readiness = await check_system_readiness(self._settings)
        return readiness.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    def run_retention_cleanup(self) -> int:
        """Run retention cleanup on the decision history."""
        decisions_list = list(self._history)
        removed = enforce_retention(decisions_list, self._settings)

        # enforce_retention modifies in-place, rebuild the deque
        self._history = deque(decisions_list, maxlen=self._settings.decision_history_max_size)

        if removed > 0:
            self._monitoring.record_retention_cleanup(removed)
            self._audit.record_retention_cleanup(removed)

        return removed

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """Decision engine health check."""
        return {
            "status": "healthy",
            "module": "decision_engine",
            "version": "10.0.0",
            "enabled": self._settings.enabled,
            "emergency_disable": self._emergency.is_disabled,
            "history_size": len(self._history),
            "active_size": len(self._active),
            "audit_size": self._audit.count,
            "idempotency_size": self._idempotency.size,
        }

    async def get_capabilities(self) -> dict:
        """Expose decision engine capabilities and configuration."""
        return {
            "module": "decision_engine",
            "version": "10.0.0",
            "enabled": self._settings.enabled,
            "decision_ttl_seconds": self._settings.decision_ttl_seconds,
            "min_signal_confidence": self._settings.min_signal_confidence,
            "min_signal_quality": self._settings.min_signal_quality,
            "min_risk_reward": self._settings.min_risk_reward,
            "max_plan_age_seconds": self._settings.max_plan_age_seconds,
            "fail_policy": self._settings.fail_policy.value,
            "emergency_disable": self._emergency.is_disabled,
            "audit_max_entries": self._settings.audit_max_entries,
            "retention_days": self._settings.retention_days,
            "idempotency_cache_size": self._settings.idempotency_cache_size,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_terminal(self, state: FinalDecisionState) -> bool:
        """Check if a state is terminal (no further transitions possible)."""
        from app.modules.decision.state_machine import is_terminal
        return is_terminal(state)

    def _cleanup_expired_active(self) -> None:
        """Remove expired decisions from the active list."""
        from app.modules.decision.expiration import is_expired
        active_list = [d for d in self._active if not is_expired(d)]
        self._active = deque(active_list, maxlen=self._settings.active_decisions_max_size)
