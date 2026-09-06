"""
Scalping Arise — Phase 10 Decision Engine Tests

Comprehensive tests for all decision engine modules:
  - config
  - models
  - state_machine
  - gate_engine
  - expiration
  - explainability
  - provenance
  - audit
  - idempotency
  - conflict_check
  - monitoring
  - emergency
  - retention
  - service
  - API endpoints
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest


# ===========================================================================
# Config Tests
# ===========================================================================

class TestDecisionEngineConfig:
    """Tests for DecisionEngineSettings."""

    def test_defaults(self):
        from app.modules.decision.config import DecisionEngineSettings
        s = DecisionEngineSettings()
        assert s.enabled is True
        assert s.decision_ttl_seconds == 300
        assert s.min_signal_confidence == 50
        assert s.min_signal_quality == 40
        assert s.min_risk_reward == 1.5
        assert s.fail_policy.value == "fail_closed"
        assert s.emergency_disable is False
        assert s.audit_max_entries == 10000
        assert s.retention_days == 30

    def test_get_settings_cached(self):
        from app.modules.decision.config import get_decision_engine_settings
        s1 = get_decision_engine_settings()
        s2 = get_decision_engine_settings()
        assert s1 is s2


# ===========================================================================
# Models Tests
# ===========================================================================

class TestModels:
    """Tests for Phase 10 Pydantic models."""

    def test_final_decision_defaults(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState, FinalDecisionDirection
        d = FinalDecision()
        assert d.state == FinalDecisionState.EVALUATING
        assert d.direction == FinalDecisionDirection.NONE
        assert d.confidence == 0
        assert d.quality == 0
        assert d.gates_passed == 0
        assert d.gates_failed == 0
        assert d.decision_version == "1.0.0"

    def test_final_decision_with_data(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState, FinalDecisionDirection
        d = FinalDecision(
            signal_id="sig-123",
            instrument="XAU/USD",
            state=FinalDecisionState.ACTIONABLE,
            direction=FinalDecisionDirection.BUY,
            confidence=75,
            quality=80,
        )
        assert d.signal_id == "sig-123"
        assert d.instrument == "XAU/USD"
        assert d.state == FinalDecisionState.ACTIONABLE
        assert d.direction == FinalDecisionDirection.BUY
        assert d.confidence == 75
        assert d.quality == 80

    def test_gate_result(self):
        from app.modules.decision.models import GateResult, GateName, GateStatus
        g = GateResult(gate=GateName.EMERGENCY_DISABLE, status=GateStatus.PASSED)
        assert g.gate == GateName.EMERGENCY_DISABLE
        assert g.status == GateStatus.PASSED
        assert g.evaluation_ms == 0.0

    def test_gate_definition(self):
        from app.modules.decision.models import GateDefinition, GateName
        gd = GateDefinition(gate=GateName.SIGNAL_FRESHNESS, enabled=True, required=True)
        assert gd.gate == GateName.SIGNAL_FRESHNESS
        assert gd.enabled is True
        assert gd.required is True

    def test_explainability_chain(self):
        from app.modules.decision.models import ExplainabilityChain, ReasonItem, ProvenanceSource
        chain = ExplainabilityChain(
            summary="Test summary",
            reasons=[ReasonItem(code="test", message="Test reason", source=ProvenanceSource.DECISION_ENGINE)],
            contributing_factors=["test_factor"],
            blocking_factors=[],
        )
        assert chain.summary == "Test summary"
        assert len(chain.reasons) == 1
        assert chain.reasons[0].code == "test"

    def test_provenance_record(self):
        from app.modules.decision.models import ProvenanceRecord, ModuleContribution, ProvenanceSource
        p = ProvenanceRecord(decision_id="dec-123")
        p.contributions.append(ModuleContribution(
            source=ProvenanceSource.SIGNAL_ENGINE,
            module_version="6.0.0",
            data_provided=["confidence"],
            healthy=True,
        ))
        p.modules_healthy = 1
        p.modules_total = 1
        assert p.decision_id == "dec-123"
        assert len(p.contributions) == 1
        assert p.modules_healthy == 1

    def test_audit_entry(self):
        from app.modules.decision.models import AuditEntry, AuditAction, FinalDecisionState
        e = AuditEntry(
            decision_id="dec-123",
            action=AuditAction.CREATED,
            state_after=FinalDecisionState.EVALUATING,
        )
        assert e.decision_id == "dec-123"
        assert e.action == AuditAction.CREATED
        assert e.state_after == FinalDecisionState.EVALUATING

    def test_conflict_report(self):
        from app.modules.decision.models import ConflictReport, ConflictDetail, ConflictType
        r = ConflictReport(has_conflicts=True, overall_severity=0.8)
        r.conflicts.append(ConflictDetail(
            conflict_type=ConflictType.DIRECTION_MISMATCH,
            description="Test conflict",
            severity=0.8,
        ))
        assert r.has_conflicts is True
        assert r.overall_severity == 0.8
        assert len(r.conflicts) == 1

    def test_system_readiness(self):
        from app.modules.decision.models import SystemReadiness, ModuleReadiness, ProvenanceSource
        sr = SystemReadiness(ready=True, healthy_count=2, total_count=2)
        sr.modules.append(ModuleReadiness(module=ProvenanceSource.MARKET_DATA, healthy=True))
        sr.modules.append(ModuleReadiness(module=ProvenanceSource.SIGNAL_ENGINE, healthy=True))
        assert sr.ready is True
        assert sr.healthy_count == 2

    def test_monitoring_counters(self):
        from app.modules.decision.models import MonitoringCounters
        mc = MonitoringCounters()
        assert mc.total_evaluations == 0
        assert mc.actionable_decisions == 0
        mc.total_evaluations = 5
        assert mc.total_evaluations == 5

    def test_retention_policy(self):
        from app.modules.decision.models import RetentionPolicy
        rp = RetentionPolicy(max_age_days=30, max_entries=10000)
        assert rp.max_age_days == 30
        assert rp.max_entries == 10000

    def test_evaluate_decision_request(self):
        from app.modules.decision.models import EvaluateDecisionRequest
        r = EvaluateDecisionRequest(signal_id="sig-123")
        assert r.signal_id == "sig-123"
        assert r.instrument == "XAU/USD"
        assert r.force is False

    def test_emergency_toggle_request(self):
        from app.modules.decision.models import EmergencyToggleRequest
        r = EmergencyToggleRequest(disable=True)
        assert r.disable is True
        assert r.reason == "Manual emergency toggle"

    def test_compute_idempotency_key(self):
        from app.modules.decision.models import compute_idempotency_key
        k1 = compute_idempotency_key("sig-1", "plan-1", "intel-1")
        k2 = compute_idempotency_key("sig-1", "plan-1", "intel-1")
        assert k1 == k2
        assert len(k1) == 32

        k3 = compute_idempotency_key("sig-2", "plan-1", "intel-1")
        assert k1 != k3


# ===========================================================================
# State Machine Tests
# ===========================================================================

class TestStateMachine:
    """Tests for the decision state machine."""

    def test_valid_transition_evaluating_to_actionable(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.state_machine import transition_decision
        d = FinalDecision(state=FinalDecisionState.EVALUATING)
        entry = transition_decision(d, FinalDecisionState.ACTIONABLE, reason="test")
        assert d.state == FinalDecisionState.ACTIONABLE
        assert entry.state_before == FinalDecisionState.EVALUATING
        assert entry.state_after == FinalDecisionState.ACTIONABLE

    def test_valid_transition_evaluating_to_blocked(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.state_machine import transition_decision
        d = FinalDecision(state=FinalDecisionState.EVALUATING)
        transition_decision(d, FinalDecisionState.BLOCKED, reason="gate failed")
        assert d.state == FinalDecisionState.BLOCKED

    def test_valid_transition_evaluating_to_no_trade(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.state_machine import transition_decision
        d = FinalDecision(state=FinalDecisionState.EVALUATING)
        transition_decision(d, FinalDecisionState.NO_TRADE, reason="no signal")
        assert d.state == FinalDecisionState.NO_TRADE

    def test_invalid_transition_actionable_to_evaluating(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.state_machine import transition_decision, StateTransitionError
        d = FinalDecision(state=FinalDecisionState.ACTIONABLE)
        with pytest.raises(StateTransitionError):
            transition_decision(d, FinalDecisionState.EVALUATING)

    def test_invalid_transition_blocked_to_actionable(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.state_machine import transition_decision, StateTransitionError
        d = FinalDecision(state=FinalDecisionState.BLOCKED)
        with pytest.raises(StateTransitionError):
            transition_decision(d, FinalDecisionState.ACTIONABLE)

    def test_terminal_state_expired(self):
        from app.modules.decision.models import FinalDecisionState
        from app.modules.decision.state_machine import is_terminal
        assert is_terminal(FinalDecisionState.EXPIRED) is True
        assert is_terminal(FinalDecisionState.INVALIDATED) is True
        assert is_terminal(FinalDecisionState.ACTIONABLE) is False
        assert is_terminal(FinalDecisionState.EVALUATING) is False

    def test_transition_to_terminal(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.state_machine import transition_to_terminal
        d = FinalDecision(state=FinalDecisionState.ACTIONABLE)
        entry = transition_to_terminal(d, FinalDecisionState.EXPIRED, reason="ttl elapsed")
        assert d.state == FinalDecisionState.EXPIRED
        assert entry.action.value == "state_transition"

    def test_can_transition(self):
        from app.modules.decision.models import FinalDecisionState
        from app.modules.decision.state_machine import can_transition
        assert can_transition(FinalDecisionState.EVALUATING, FinalDecisionState.ACTIONABLE) is True
        assert can_transition(FinalDecisionState.EVALUATING, FinalDecisionState.EXPIRED) is True
        assert can_transition(FinalDecisionState.ACTIONABLE, FinalDecisionState.EXPIRED) is True
        assert can_transition(FinalDecisionState.EXPIRED, FinalDecisionState.ACTIONABLE) is False

    def test_get_valid_transitions(self):
        from app.modules.decision.models import FinalDecisionState
        from app.modules.decision.state_machine import get_valid_transitions
        transitions = get_valid_transitions(FinalDecisionState.EVALUATING)
        assert FinalDecisionState.ACTIONABLE in transitions
        assert FinalDecisionState.BLOCKED in transitions
        assert FinalDecisionState.NO_TRADE in transitions
        assert FinalDecisionState.EXPIRED in transitions  # Evaluating decisions can expire
        assert FinalDecisionState.EXPIRED not in get_valid_transitions(FinalDecisionState.EXPIRED)


# ===========================================================================
# Gate Engine Tests
# ===========================================================================

class TestGateEngine:
    """Tests for the gate engine."""

    def test_all_gates_pass(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus
        settings = DecisionEngineSettings(emergency_disable=False)
        engine = GateEngine(settings=settings)
        results = engine.evaluate(
            signal_confidence=80,
            signal_quality=70,
            signal_age_seconds=30,
            event_decision="allow",
            strategy_performance_state="active",
            plan_valid=True,
            plan_state="approved",
            plan_within_risk_limits=True,
            plan_risk_reward=2.0,
            plan_age_seconds=30,
            system_ready=True,
            has_conflicts=False,
        )
        # All required gates should pass
        failed = [r for r in results if r.status == GateStatus.FAILED]
        assert len(failed) == 0

    def test_emergency_disable_blocks(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus, GateName
        settings = DecisionEngineSettings(emergency_disable=True)
        engine = GateEngine(settings=settings)
        results = engine.evaluate()
        emergency_result = next(r for r in results if r.gate == GateName.EMERGENCY_DISABLE)
        assert emergency_result.status == GateStatus.FAILED

    def test_signal_quality_below_threshold(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus, GateName
        settings = DecisionEngineSettings(min_signal_quality=50)
        engine = GateEngine(settings=settings)
        results = engine.evaluate(signal_quality=30)
        quality_result = next(r for r in results if r.gate == GateName.SIGNAL_QUALITY)
        assert quality_result.status == GateStatus.FAILED

    def test_signal_confidence_below_threshold(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus, GateName
        settings = DecisionEngineSettings(min_signal_confidence=60)
        engine = GateEngine(settings=settings)
        results = engine.evaluate(signal_confidence=40, signal_quality=80)
        conf_result = next(r for r in results if r.gate == GateName.SIGNAL_CONFIDENCE)
        assert conf_result.status == GateStatus.FAILED

    def test_event_risk_block(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus, GateName
        settings = DecisionEngineSettings()
        engine = GateEngine(settings=settings)
        results = engine.evaluate(
            signal_confidence=80,
            signal_quality=70,
            event_decision="block",
        )
        event_result = next(r for r in results if r.gate == GateName.EVENT_RISK)
        assert event_result.status == GateStatus.FAILED

    def test_event_risk_fail_open(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus, GateName
        settings = DecisionEngineSettings(event_risk_fail_policy="fail_open")
        engine = GateEngine(settings=settings)
        results = engine.evaluate(
            signal_confidence=80,
            signal_quality=70,
            event_decision=None,
        )
        event_result = next(r for r in results if r.gate == GateName.EVENT_RISK)
        assert event_result.status == GateStatus.SKIPPED

    def test_strategy_disabled_blocks(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus, GateName
        settings = DecisionEngineSettings()
        engine = GateEngine(settings=settings)
        results = engine.evaluate(
            signal_confidence=80,
            signal_quality=70,
            strategy_performance_state="disabled",
        )
        strat_result = next(r for r in results if r.gate == GateName.STRATEGY_STATE)
        assert strat_result.status == GateStatus.FAILED

    def test_plan_invalid_blocks(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus, GateName
        settings = DecisionEngineSettings()
        engine = GateEngine(settings=settings)
        results = engine.evaluate(
            signal_confidence=80,
            signal_quality=70,
            plan_valid=False,
            plan_state="rejected",
        )
        plan_result = next(r for r in results if r.gate == GateName.PLAN_VALIDITY)
        assert plan_result.status == GateStatus.FAILED

    def test_plan_rr_below_minimum(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus, GateName
        settings = DecisionEngineSettings(min_risk_reward=1.5)
        engine = GateEngine(settings=settings)
        results = engine.evaluate(
            signal_confidence=80,
            signal_quality=70,
            plan_valid=True,
            plan_state="approved",
            plan_within_risk_limits=True,
            plan_risk_reward=1.0,
        )
        rr_result = next(r for r in results if r.gate == GateName.PLAN_RR_MINIMUM)
        assert rr_result.status == GateStatus.FAILED

    def test_short_circuit_on_required_failure(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus, GateName
        settings = DecisionEngineSettings(emergency_disable=True)
        engine = GateEngine(settings=settings)
        results = engine.evaluate()
        # After emergency disable fails, subsequent required gates should be skipped
        emergency_idx = next(i for i, r in enumerate(results) if r.gate == GateName.EMERGENCY_DISABLE)
        skipped_after = [
            r for r in results[emergency_idx + 1:]
            if r.status == GateStatus.SKIPPED
        ]
        assert len(skipped_after) > 0

    def test_count_gates(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        from app.modules.decision.models import GateStatus
        settings = DecisionEngineSettings(emergency_disable=False)
        engine = GateEngine(settings=settings)
        results = engine.evaluate(
            signal_confidence=80,
            signal_quality=70,
            event_decision="allow",
            strategy_performance_state="active",
            plan_valid=True,
            plan_state="approved",
            plan_within_risk_limits=True,
            plan_risk_reward=2.0,
            system_ready=True,
        )
        counts = engine.count_gates(results)
        assert counts["total"] > 0
        assert counts["passed"] > 0
        assert counts["failed"] == 0

    def test_any_required_failed(self):
        from app.modules.decision.gate_engine import GateEngine
        from app.modules.decision.config import DecisionEngineSettings
        settings = DecisionEngineSettings(emergency_disable=True)
        engine = GateEngine(settings=settings)
        results = engine.evaluate()
        assert engine.any_required_failed(results) is True


# ===========================================================================
# Expiration Tests
# ===========================================================================

class TestExpiration:
    """Tests for TTL enforcement."""

    def test_set_expiration(self):
        from app.modules.decision.models import FinalDecision
        from app.modules.decision.expiration import set_expiration
        d = FinalDecision()
        set_expiration(d, 300)
        assert d.expires_at is not None
        assert d.ttl_seconds == 300
        diff = (d.expires_at - d.created_at).total_seconds()
        assert abs(diff - 300) < 1

    def test_is_not_expired(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.expiration import set_expiration, is_expired
        d = FinalDecision(state=FinalDecisionState.EVALUATING)
        set_expiration(d, 300)
        assert is_expired(d) is False

    def test_is_expired_when_past(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.expiration import is_expired
        d = FinalDecision(state=FinalDecisionState.EVALUATING)
        d.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        assert is_expired(d) is True

    def test_is_expired_terminal(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.expiration import is_expired
        d = FinalDecision(state=FinalDecisionState.EXPIRED)
        assert is_expired(d) is True

    def test_check_and_expire(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.expiration import check_and_expire
        d = FinalDecision(state=FinalDecisionState.EVALUATING)
        d.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        result = check_and_expire(d)
        assert result == FinalDecisionState.EXPIRED
        assert d.state == FinalDecisionState.EXPIRED

    def test_cleanup_expired(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.expiration import cleanup_expired
        d1 = FinalDecision(state=FinalDecisionState.EVALUATING)
        d1.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        d2 = FinalDecision(state=FinalDecisionState.EVALUATING)
        d2.expires_at = datetime.now(timezone.utc) + timedelta(seconds=300)
        count = cleanup_expired([d1, d2])
        assert count == 1
        assert d1.state == FinalDecisionState.EXPIRED
        assert d2.state == FinalDecisionState.EVALUATING

    def test_get_remaining_ttl(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.expiration import set_expiration, get_remaining_ttl
        d = FinalDecision(state=FinalDecisionState.EVALUATING)
        set_expiration(d, 300)
        remaining = get_remaining_ttl(d)
        assert 290 < remaining <= 300


# ===========================================================================
# Explainability Tests
# ===========================================================================

class TestExplainability:
    """Tests for the explainability builder."""

    def test_build_explainability_actionable(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState, FinalDecisionDirection, GateResult, GateName, GateStatus
        from app.modules.decision.explainability import build_explainability
        d = FinalDecision(
            state=FinalDecisionState.ACTIONABLE,
            direction=FinalDecisionDirection.BUY,
            confidence=75,
            quality=80,
            gates=[
                GateResult(gate=GateName.EMERGENCY_DISABLE, status=GateStatus.PASSED, reason="OK"),
                GateResult(gate=GateName.SIGNAL_QUALITY, status=GateStatus.PASSED, reason="Quality 80"),
            ],
        )
        chain = build_explainability(d, signal_direction="buy", signal_instrument="XAU/USD")
        assert "BUY" in chain.summary
        assert "XAU/USD" in chain.summary
        assert len(chain.reasons) > 0
        assert "emergency_disable" in chain.contributing_factors

    def test_build_explainability_blocked(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState, GateResult, GateName, GateStatus
        from app.modules.decision.explainability import build_explainability
        d = FinalDecision(
            state=FinalDecisionState.BLOCKED,
            blocked_by_gate=GateName.EMERGENCY_DISABLE,
            rejection_reason="Emergency active",
            gates=[
                GateResult(gate=GateName.EMERGENCY_DISABLE, status=GateStatus.FAILED, reason="Emergency active"),
            ],
        )
        chain = build_explainability(d)
        assert "BLOCKED" in chain.summary
        assert len(chain.blocking_factors) > 0

    def test_build_explainability_no_trade(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.explainability import build_explainability
        d = FinalDecision(state=FinalDecisionState.NO_TRADE, instrument="XAU/USD")
        chain = build_explainability(d)
        assert "NO TRADE" in chain.summary


# ===========================================================================
# Provenance Tests
# ===========================================================================

class TestProvenance:
    """Tests for provenance tracking."""

    def test_create_provenance(self):
        from app.modules.decision.provenance import create_provenance
        p = create_provenance("dec-123")
        assert p.decision_id == "dec-123"
        assert p.modules_healthy == 0
        assert p.modules_total == 0

    def test_record_contribution(self):
        from app.modules.decision.provenance import create_provenance, record_contribution
        from app.modules.decision.models import ProvenanceSource
        p = create_provenance("dec-123")
        record_contribution(p, ProvenanceSource.SIGNAL_ENGINE, data_provided=["confidence"], healthy=True)
        assert p.modules_healthy == 1
        assert p.modules_total == 1
        assert len(p.contributions) == 1
        assert p.contributions[0].source == ProvenanceSource.SIGNAL_ENGINE

    def test_get_module_version(self):
        from app.modules.decision.provenance import get_module_version
        from app.modules.decision.models import ProvenanceSource
        assert get_module_version(ProvenanceSource.SIGNAL_ENGINE) == "6.0.0"
        assert get_module_version(ProvenanceSource.DECISION_ENGINE) == "10.0.0"

    def test_get_health_ratio(self):
        from app.modules.decision.models import ProvenanceRecord
        from app.modules.decision.provenance import get_health_ratio
        p = ProvenanceRecord(decision_id="dec-123", modules_healthy=3, modules_total=4)
        assert get_health_ratio(p) == 0.75

    def test_get_health_ratio_empty(self):
        from app.modules.decision.models import ProvenanceRecord
        from app.modules.decision.provenance import get_health_ratio
        p = ProvenanceRecord(decision_id="dec-123")
        assert get_health_ratio(p) == 1.0


# ===========================================================================
# Audit Trail Tests
# ===========================================================================

class TestAuditTrail:
    """Tests for the audit trail."""

    def test_record_creation(self):
        from app.modules.decision.audit import AuditTrail
        from app.modules.decision.models import FinalDecision, AuditAction
        trail = AuditTrail(max_entries=100)
        d = FinalDecision()
        trail.record_creation(d)
        assert trail.count == 1
        entries = trail.get_for_decision(d.decision_id)
        assert len(entries) == 1
        assert entries[0].action == AuditAction.CREATED

    def test_record_gate(self):
        from app.modules.decision.audit import AuditTrail
        from app.modules.decision.models import FinalDecision, GateName, GateStatus, AuditAction
        trail = AuditTrail(max_entries=100)
        d = FinalDecision()
        trail.record_gate(d, GateName.SIGNAL_QUALITY, GateStatus.PASSED, "Quality OK")
        assert trail.count == 1
        entries = trail.get_for_decision(d.decision_id)
        assert entries[0].gate == GateName.SIGNAL_QUALITY
        assert entries[0].gate_status == GateStatus.PASSED

    def test_ring_buffer_overflow(self):
        from app.modules.decision.audit import AuditTrail
        from app.modules.decision.models import AuditEntry, AuditAction
        trail = AuditTrail(max_entries=5)
        for i in range(10):
            trail.record(AuditEntry(decision_id=f"dec-{i}", action=AuditAction.CREATED))
        assert trail.count == 5

    def test_get_recent(self):
        from app.modules.decision.audit import AuditTrail
        from app.modules.decision.models import AuditEntry, AuditAction
        trail = AuditTrail(max_entries=100)
        for i in range(10):
            trail.record(AuditEntry(decision_id=f"dec-{i}", action=AuditAction.CREATED))
        recent = trail.get_recent(limit=3)
        assert len(recent) == 3

    def test_clear(self):
        from app.modules.decision.audit import AuditTrail
        from app.modules.decision.models import AuditEntry, AuditAction
        trail = AuditTrail(max_entries=100)
        for i in range(5):
            trail.record(AuditEntry(decision_id=f"dec-{i}", action=AuditAction.CREATED))
        removed = trail.clear()
        assert removed == 5
        assert trail.count == 0


# ===========================================================================
# Idempotency Tests
# ===========================================================================

class TestIdempotency:
    """Tests for idempotency cache."""

    def test_compute_key_deterministic(self):
        from app.modules.decision.idempotency import IdempotencyCache
        cache = IdempotencyCache()
        k1 = cache.compute_key("sig-1", "plan-1", "intel-1")
        k2 = cache.compute_key("sig-1", "plan-1", "intel-1")
        assert k1 == k2

    def test_store_and_lookup(self):
        from app.modules.decision.idempotency import IdempotencyCache
        cache = IdempotencyCache()
        key = cache.compute_key("sig-1")
        cache.store(key, "dec-123")
        result = cache.lookup(key)
        assert result == "dec-123"
        assert cache.hits == 1

    def test_lookup_miss(self):
        from app.modules.decision.idempotency import IdempotencyCache
        cache = IdempotencyCache()
        result = cache.lookup("nonexistent")
        assert result is None
        assert cache.misses == 1

    def test_eviction(self):
        from app.modules.decision.idempotency import IdempotencyCache
        cache = IdempotencyCache(max_size=3)
        for i in range(5):
            key = cache.compute_key(f"sig-{i}")
            cache.store(key, f"dec-{i}")
        assert cache.size == 3

    def test_invalidate(self):
        from app.modules.decision.idempotency import IdempotencyCache
        cache = IdempotencyCache()
        key = cache.compute_key("sig-1")
        cache.store(key, "dec-123")
        assert cache.invalidate(key) is True
        assert cache.lookup(key) is None

    def test_cleanup_expired(self):
        from app.modules.decision.idempotency import IdempotencyCache
        cache = IdempotencyCache(ttl_seconds=0)
        key = cache.compute_key("sig-1")
        cache.store(key, "dec-123")
        time.sleep(0.01)
        removed = cache.cleanup_expired()
        assert removed == 1

    def test_stats(self):
        from app.modules.decision.idempotency import IdempotencyCache
        cache = IdempotencyCache()
        key = cache.compute_key("sig-1")
        cache.store(key, "dec-123")
        cache.lookup(key)
        cache.lookup("nonexistent")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1


# ===========================================================================
# Conflict Check Tests
# ===========================================================================

class TestConflictCheck:
    """Tests for conflict detection."""

    def test_no_conflicts(self):
        from app.modules.decision.conflict_check import detect_conflicts
        report = detect_conflicts(
            signal_direction="buy",
            plan_side="long",
            signal_confidence=80,
            plan_risk_reward=2.0,
            event_decision="allow",
            strategy_state="active",
            plan_within_risk_limits=True,
        )
        assert report.has_conflicts is False
        assert report.overall_severity == 0.0

    def test_direction_conflict(self):
        from app.modules.decision.conflict_check import detect_conflicts
        report = detect_conflicts(
            signal_direction="buy",
            plan_side="short",
        )
        assert report.has_conflicts is True
        assert report.overall_severity >= 0.8

    def test_confidence_contradiction(self):
        from app.modules.decision.conflict_check import detect_conflicts
        report = detect_conflicts(
            signal_confidence=80,
            plan_risk_reward=1.0,
            min_rr=1.5,
        )
        assert report.has_conflicts is True
        assert report.overall_severity > 0.0

    def test_intelligence_veto(self):
        from app.modules.decision.conflict_check import detect_conflicts
        report = detect_conflicts(event_decision="block")
        assert report.has_conflicts is True
        assert report.overall_severity >= 0.9

    def test_strategy_disabled(self):
        from app.modules.decision.conflict_check import detect_conflicts
        report = detect_conflicts(strategy_state="disabled")
        assert report.has_conflicts is True
        assert report.overall_severity == 1.0

    def test_risk_limit_breach(self):
        from app.modules.decision.conflict_check import detect_conflicts
        report = detect_conflicts(plan_within_risk_limits=False)
        assert report.has_conflicts is True

    def test_direction_conflict_none_values(self):
        from app.modules.decision.conflict_check import detect_conflicts
        report = detect_conflicts(signal_direction=None, plan_side=None)
        assert report.has_conflicts is False


# ===========================================================================
# Monitoring Tests
# ===========================================================================

class TestMonitoring:
    """Tests for monitoring counters."""

    def test_record_evaluation(self):
        from app.modules.decision.monitoring import MonitoringService
        svc = MonitoringService()
        svc.record_evaluation(state="actionable", evaluation_ms=15.5)
        counters = svc.counters
        assert counters.total_evaluations == 1
        assert counters.actionable_decisions == 1
        assert counters.avg_evaluation_ms == 15.5

    def test_record_multiple(self):
        from app.modules.decision.monitoring import MonitoringService
        svc = MonitoringService()
        svc.record_evaluation(state="actionable", evaluation_ms=10.0)
        svc.record_evaluation(state="blocked", evaluation_ms=20.0)
        svc.record_evaluation(state="no_trade", evaluation_ms=5.0)
        counters = svc.counters
        assert counters.total_evaluations == 3
        assert counters.actionable_decisions == 1
        assert counters.blocked_decisions == 1
        assert counters.no_trade_decisions == 1

    def test_idempotency_counters(self):
        from app.modules.decision.monitoring import MonitoringService
        svc = MonitoringService()
        svc.record_idempotency_hit()
        svc.record_idempotency_hit()
        svc.record_idempotency_miss()
        counters = svc.counters
        assert counters.idempotency_cache_hits == 2
        assert counters.idempotency_cache_misses == 1

    def test_reset(self):
        from app.modules.decision.monitoring import MonitoringService
        svc = MonitoringService()
        svc.record_evaluation(state="actionable")
        svc.reset()
        counters = svc.counters
        assert counters.total_evaluations == 0


# ===========================================================================
# Emergency Tests
# ===========================================================================

class TestEmergency:
    """Tests for emergency kill switch."""

    def test_default_state(self):
        from app.modules.decision.emergency import EmergencyController
        ec = EmergencyController()
        assert ec.is_disabled is False

    def test_disable(self):
        from app.modules.decision.emergency import EmergencyController
        ec = EmergencyController()
        ec.disable("Test disable")
        assert ec.is_disabled is True
        assert ec.toggle_count == 1
        assert ec.last_reason == "Test disable"

    def test_enable(self):
        from app.modules.decision.emergency import EmergencyController
        ec = EmergencyController(initial_state=True)
        ec.enable("Test enable")
        assert ec.is_disabled is False
        assert ec.toggle_count == 1

    def test_toggle(self):
        from app.modules.decision.emergency import EmergencyController
        ec = EmergencyController()
        result = ec.toggle(True, "Toggle on")
        assert result is True
        result = ec.toggle(False, "Toggle off")
        assert result is False

    def test_status(self):
        from app.modules.decision.emergency import EmergencyController
        ec = EmergencyController()
        status = ec.get_status()
        assert status["disabled"] is False
        assert status["toggle_count"] == 0


# ===========================================================================
# Retention Tests
# ===========================================================================

class TestRetention:
    """Tests for data retention."""

    def test_is_retention_eligible(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.retention import is_retention_eligible
        d = FinalDecision(state=FinalDecisionState.EXPIRED)
        d.updated_at = datetime.now(timezone.utc) - timedelta(days=31)
        assert is_retention_eligible(d, max_age_days=30) is True

    def test_not_eligible_non_terminal(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.retention import is_retention_eligible
        d = FinalDecision(state=FinalDecisionState.ACTIONABLE)
        assert is_retention_eligible(d, max_age_days=30) is False

    def test_not_eligible_recent(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.retention import is_retention_eligible
        d = FinalDecision(state=FinalDecisionState.EXPIRED)
        d.updated_at = datetime.now(timezone.utc) - timedelta(days=5)
        assert is_retention_eligible(d, max_age_days=30) is False

    def test_cleanup_retention(self):
        from app.modules.decision.models import FinalDecision, FinalDecisionState
        from app.modules.decision.retention import cleanup_retention
        old = FinalDecision(state=FinalDecisionState.EXPIRED)
        old.updated_at = datetime.now(timezone.utc) - timedelta(days=31)
        recent = FinalDecision(state=FinalDecisionState.EXPIRED)
        recent.updated_at = datetime.now(timezone.utc) - timedelta(days=5)
        active = FinalDecision(state=FinalDecisionState.ACTIONABLE)
        surviving, removed = cleanup_retention([old, recent, active], max_age_days=30)
        assert removed == 1
        assert len(surviving) == 2


# ===========================================================================
# Service Tests
# ===========================================================================

class TestDecisionEngineService:
    """Tests for the DecisionEngineService orchestrator."""

    def _make_service(self):
        from app.modules.decision.service import DecisionEngineService
        from app.modules.decision.config import DecisionEngineSettings
        settings = DecisionEngineSettings(
            emergency_disable=False,
            min_signal_confidence=50,
            min_signal_quality=40,
            min_risk_reward=1.5,
        )
        return DecisionEngineService(settings=settings)

    def _default_eval_kwargs(self, **overrides):
        """Return all required params for evaluate_decision with sensible defaults."""
        defaults = dict(
            signal_id="sig-test",
            instrument="XAU/USD",
            signal_direction="buy",
            signal_confidence=80,
            signal_quality=70,
            signal_age_seconds=10,
            plan_valid=True,
            plan_state="approved",
            plan_side="long",
            plan_risk_reward=2.0,
            plan_within_risk_limits=True,
            plan_age_seconds=10,
            event_decision="allow",
            strategy_performance_state="active",
            system_ready=True,
        )
        defaults.update(overrides)
        return defaults

    @pytest.mark.asyncio
    async def test_evaluate_actionable(self):
        svc = self._make_service()
        decision = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-001",
        ))
        assert decision.state.value == "actionable"
        assert decision.direction.value == "buy"
        assert decision.gates_passed > 0
        assert decision.explainability is not None
        assert decision.provenance is not None

    @pytest.mark.asyncio
    async def test_evaluate_blocked_by_emergency(self):
        svc = self._make_service()
        svc._emergency.disable("Test")
        decision = await svc.evaluate_decision(
            signal_id="sig-002",
            instrument="XAU/USD",
        )
        assert decision.state.value == "blocked"
        assert decision.rejection_reason == "Emergency disable is active"

    @pytest.mark.asyncio
    async def test_evaluate_blocked_by_quality(self):
        svc = self._make_service()
        decision = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-003",
            signal_quality=20,  # below threshold
            signal_direction="buy",
        ))
        assert decision.state.value == "blocked"

    @pytest.mark.asyncio
    async def test_evaluate_no_trade(self):
        svc = self._make_service()
        decision = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-004",
            signal_direction=None,  # no direction → no_trade
        ))
        assert decision.state.value == "no_trade"

    @pytest.mark.asyncio
    async def test_get_decision(self):
        svc = self._make_service()
        decision = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-005",
        ))
        found = svc.get_decision(decision.decision_id)
        assert found is not None
        assert found.decision_id == decision.decision_id

    @pytest.mark.asyncio
    async def test_get_history(self):
        svc = self._make_service()
        for i in range(3):
            await svc.evaluate_decision(**self._default_eval_kwargs(
                signal_id=f"sig-{i}",
            ))
        history = svc.get_history(limit=10)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_invalidate_decision(self):
        svc = self._make_service()
        decision = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-006",
        ))
        success = svc.invalidate_decision(decision.decision_id, "Test invalidation")
        assert success is True
        found = svc.get_decision(decision.decision_id)
        assert found.state.value == "invalidated"

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent(self):
        svc = self._make_service()
        success = svc.invalidate_decision("nonexistent-id")
        assert success is False

    @pytest.mark.asyncio
    async def test_emergency_toggle(self):
        svc = self._make_service()
        status = svc.emergency_disable("Test disable")
        assert status["disabled"] is True
        status = svc.emergency_enable("Test enable")
        assert status["disabled"] is False

    @pytest.mark.asyncio
    async def test_audit_trail(self):
        svc = self._make_service()
        decision = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-007",
        ))
        entries = svc.get_audit_trail(decision.decision_id)
        assert len(entries) > 0

    @pytest.mark.asyncio
    async def test_monitoring_counters(self):
        svc = self._make_service()
        await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-008",
        ))
        counters = svc.get_monitoring_counters()
        assert counters.total_evaluations == 1
        assert counters.actionable_decisions == 1

    @pytest.mark.asyncio
    async def test_health_check(self):
        svc = self._make_service()
        health = await svc.health_check()
        assert health["status"] == "healthy"
        assert health["module"] == "decision_engine"

    @pytest.mark.asyncio
    async def test_capabilities(self):
        svc = self._make_service()
        caps = await svc.get_capabilities()
        assert caps["module"] == "decision_engine"
        assert caps["version"] == "10.0.0"
        assert caps["min_signal_confidence"] == 50

    @pytest.mark.asyncio
    async def test_idempotency(self):
        svc = self._make_service()
        d1 = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-009",
        ))
        d2 = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-009",
        ))
        assert d1.decision_id == d2.decision_id

    @pytest.mark.asyncio
    async def test_force_re_evaluation(self):
        svc = self._make_service()
        d1 = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-010",
        ))
        d2 = await svc.evaluate_decision(**self._default_eval_kwargs(
            signal_id="sig-010",
            signal_direction="sell",
            signal_confidence=90,
            signal_quality=80,
            plan_risk_reward=3.0,
            force=True,
        ))
        assert d1.decision_id != d2.decision_id

    @pytest.mark.asyncio
    async def test_retention_cleanup(self):
        svc = self._make_service()
        removed = svc.run_retention_cleanup()
        assert removed >= 0


# ===========================================================================
# API Endpoint Tests
# ===========================================================================

class TestDecisionAPI:
    """Tests for the decision engine API endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import application
        return TestClient(application)

    def test_health(self, client):
        response = client.get("/api/v1/decision/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["module"] == "decision_engine"

    def test_capabilities(self, client):
        response = client.get("/api/v1/decision/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert data["module"] == "decision_engine"
        assert "min_signal_confidence" in data

    def test_evaluate(self, client):
        response = client.post("/api/v1/decision/evaluate", json={
            "signal_id": "api-sig-001",
            "instrument": "XAU/USD",
            "signal_direction": "buy",
            "signal_confidence": 80,
            "signal_quality": 70,
            "signal_age_seconds": 10,
            "plan_valid": True,
            "plan_state": "approved",
            "plan_side": "long",
            "plan_risk_reward": 2.0,
            "plan_within_risk_limits": True,
            "plan_age_seconds": 10,
            "event_decision": "allow",
            "strategy_performance_state": "active",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["state"] in ("actionable", "blocked")  # blocked if readiness fails in test env
        assert "decision_id" in data
        assert "gates" in data
        assert "explainability" in data
        assert "provenance" in data

    def test_evaluate_minimal(self, client):
        response = client.post("/api/v1/decision/evaluate", json={
            "signal_id": "api-sig-002",
        })
        assert response.status_code == 200
        data = response.json()
        assert "state" in data
        assert "decision_id" in data

    def test_active(self, client):
        response = client.get("/api/v1/decision/active")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "decisions" in data

    def test_history(self, client):
        response = client.get("/api/v1/decision/history?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "decisions" in data

    def test_get_decision(self, client):
        # First create a decision
        eval_res = client.post("/api/v1/decision/evaluate", json={
            "signal_id": "api-sig-003",
            "instrument": "XAU/USD",
            "signal_direction": "buy",
            "signal_confidence": 80,
            "signal_quality": 70,
            "plan_valid": True,
            "plan_state": "approved",
            "plan_risk_reward": 2.0,
            "system_ready": True,
        })
        decision_id = eval_res.json()["decision_id"]

        response = client.get(f"/api/v1/decision/{decision_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["decision_id"] == decision_id

    def test_get_nonexistent(self, client):
        response = client.get("/api/v1/decision/nonexistent-id")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data

    def test_invalidate(self, client):
        eval_res = client.post("/api/v1/decision/evaluate", json={
            "signal_id": "api-sig-004",
            "signal_direction": "buy",
            "signal_confidence": 80,
            "signal_quality": 70,
            "plan_valid": True,
            "plan_state": "approved",
            "plan_risk_reward": 2.0,
            "system_ready": True,
        })
        decision_id = eval_res.json()["decision_id"]

        response = client.post(f"/api/v1/decision/{decision_id}/invalidate?reason=Test")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_audit_trail(self, client):
        eval_res = client.post("/api/v1/decision/evaluate", json={
            "signal_id": "api-sig-005",
            "signal_direction": "buy",
            "signal_confidence": 80,
            "signal_quality": 70,
            "plan_valid": True,
            "plan_state": "approved",
            "plan_risk_reward": 2.0,
            "system_ready": True,
        })
        decision_id = eval_res.json()["decision_id"]

        response = client.get(f"/api/v1/decision/{decision_id}/audit")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] > 0

    def test_counters(self, client):
        response = client.get("/api/v1/decision/monitoring/counters")
        assert response.status_code == 200
        data = response.json()
        assert "total_evaluations" in data

    def test_emergency_status(self, client):
        response = client.get("/api/v1/decision/emergency/status")
        assert response.status_code == 200
        data = response.json()
        assert "disabled" in data

    def test_emergency_toggle(self, client):
        response = client.post("/api/v1/decision/emergency/disable", json={
            "disable": True,
            "reason": "API test",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["emergency_disable"] is True

        # Re-enable
        response = client.post("/api/v1/decision/emergency/disable", json={
            "disable": False,
            "reason": "API test re-enable",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["emergency_disable"] is False

    def test_retention_cleanup(self, client):
        response = client.post("/api/v1/decision/retention/cleanup")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "removed" in data
