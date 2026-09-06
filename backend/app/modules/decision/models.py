"""
Scalping Arise — Decision Engine Models (Phase 10)

Strongly typed models for final decisions, gate results, state machine,
explainability, provenance, audit trail, conflict reports, system readiness,
monitoring counters, and emergency controls.

Phase 10 is an orchestrator + safety layer. It consumes outputs from
Phases 6, 7, and 8 and produces a FinalDecision with full traceability.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ===========================================================================
# Enums — type-safe decision states
# ===========================================================================

class FinalDecisionState(str, Enum):
    """
    Full lifecycle state machine for a final decision.

    Transitions:
        EVALUATING → WAITING | NO_TRADE | BLOCKED | INVALID | ACTIONABLE
        WAITING    → ACTIONABLE | NO_TRADE | BLOCKED | INVALID | EXPIRED
        ACTIONABLE → EXPIRED | INVALIDATED
        Any        → EXPIRED (TTL elapsed)
        Any        → INVALIDATED (manual override or market shift)
    """

    EVALUATING = "evaluating"
    WAITING = "waiting"
    ACTIONABLE = "actionable"
    NO_TRADE = "no_trade"
    BLOCKED = "blocked"
    INVALID = "invalid"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class FinalDecisionDirection(str, Enum):
    """Directional action for an actionable decision."""

    BUY = "buy"
    SELL = "sell"
    NONE = "none"


class GateStatus(str, Enum):
    """Result of a single gate evaluation."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class GateName(str, Enum):
    """Identifiers for each gate in the decision pipeline."""

    EMERGENCY_DISABLE = "emergency_disable"
    SIGNAL_FRESHNESS = "signal_freshness"
    SIGNAL_QUALITY = "signal_quality"
    SIGNAL_CONFIDENCE = "signal_confidence"
    EVENT_RISK = "event_risk"
    STRATEGY_STATE = "strategy_state"
    PLAN_VALIDITY = "plan_validity"
    PLAN_RISK_LIMITS = "plan_risk_limits"
    PLAN_RR_MINIMUM = "plan_rr_minimum"
    PLAN_FRESHNESS = "plan_freshness"
    SYSTEM_READINESS = "system_readiness"
    CONFLICT_CHECK = "conflict_check"
    IDEMPOTENCY = "idempotency"


class ConflictType(str, Enum):
    """Type of conflict detected between signal and plan."""

    DIRECTION_MISMATCH = "direction_mismatch"
    CONFIDENCE_CONTRADICTION = "confidence_contradiction"
    INTELLIGENCE_VETO = "intelligence_veto"
    STRATEGY_STATE_BLOCK = "strategy_state_block"
    RISK_LIMIT_BREACH = "risk_limit_breach"


class ProvenanceSource(str, Enum):
    """Which module contributed data to a decision."""

    MARKET_DATA = "market_data"
    MARKET_ANALYSIS = "market_analysis"
    TECHNICAL_FEATURES = "technical_features"
    STRATEGIES = "strategies"
    SIGNAL_ENGINE = "signal_engine"
    TRADE_PLANNING = "trade_planning"
    NEWS_INTELLIGENCE = "news_intelligence"
    BACKTESTING = "backtesting"
    DECISION_ENGINE = "decision_engine"


class AuditAction(str, Enum):
    """Actions recorded in the audit trail."""

    CREATED = "created"
    GATE_EVALUATED = "gate_evaluated"
    STATE_TRANSITION = "state_transition"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    EMERGENCY_DISABLE = "emergency_disable"
    EMERGENCY_ENABLE = "emergency_enable"
    RETENTION_CLEANUP = "retention_cleanup"


# ===========================================================================
# Gate Result
# ===========================================================================

class GateResult(BaseModel):
    """Result of evaluating a single gate."""

    gate: GateName
    status: GateStatus
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evaluation_ms: float = Field(default=0.0, ge=0.0, description="Evaluation time in milliseconds")


class GateDefinition(BaseModel):
    """Defines a gate configuration for the pipeline."""

    gate: GateName
    enabled: bool = True
    required: bool = True
    fail_policy: str = Field(
        default="fail_closed",
        description="Behavior when gate encounters an error: fail_open or fail_closed",
    )
    description: str = ""


# ===========================================================================
# Explainability
# ===========================================================================

class ReasonItem(BaseModel):
    """A single reason in the explainability chain."""

    code: str = Field(description="Machine-readable reason code")
    message: str = Field(description="Human-readable explanation")
    source: ProvenanceSource = Field(description="Which module produced this reason")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Relative importance of this reason")
    evidence: list[str] = Field(default_factory=list, description="Supporting evidence strings")


class ExplainabilityChain(BaseModel):
    """
    Complete explainability output for a decision.

    Provides a human-readable chain of reasons that led to the final decision,
    ordered by relevance and weight.
    """

    summary: str = Field(description="One-line summary of the decision rationale")
    reasons: list[ReasonItem] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list, description="List of factor names that contributed")
    blocking_factors: list[str] = Field(default_factory=list, description="List of factor names that blocked the decision")
    confidence_breakdown: dict[str, float] = Field(default_factory=dict, description="Confidence contribution by source")


# ===========================================================================
# Provenance
# ===========================================================================

class ModuleContribution(BaseModel):
    """Tracks what a specific module contributed to a decision."""

    source: ProvenanceSource
    module_version: str = Field(default="1.0.0")
    data_provided: list[str] = Field(default_factory=list, description="Data fields contributed")
    evaluation_time_ms: float = Field(default=0.0, ge=0.0)
    healthy: bool = Field(default=True, description="Whether the module was healthy during evaluation")


class ProvenanceRecord(BaseModel):
    """
    Complete provenance tracking for a decision.

    Records which modules contributed, their versions, and health state
    at the time of evaluation.
    """

    decision_id: str
    contributions: list[ModuleContribution] = Field(default_factory=list)
    total_evaluation_ms: float = Field(default=0.0, ge=0.0)
    modules_healthy: int = Field(default=0, ge=0)
    modules_total: int = Field(default=0, ge=0)


# ===========================================================================
# Audit Trail
# ===========================================================================

class AuditEntry(BaseModel):
    """A single immutable audit trail entry."""

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str
    action: AuditAction
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_before: Optional[FinalDecisionState] = None
    state_after: Optional[FinalDecisionState] = None
    details: dict[str, Any] = Field(default_factory=dict)
    gate: Optional[GateName] = None
    gate_status: Optional[GateStatus] = None


# ===========================================================================
# Conflict Report
# ===========================================================================

class ConflictDetail(BaseModel):
    """A specific conflict detected between pipeline components."""

    conflict_type: ConflictType
    description: str
    severity: float = Field(ge=0.0, le=1.0, description="0.0 = minor, 1.0 = critical")
    involved_components: list[str] = Field(default_factory=list)
    resolution: str = Field(default="", description="How the conflict was resolved or would be resolved")


class ConflictReport(BaseModel):
    """Aggregated conflict report for a decision evaluation."""

    has_conflicts: bool
    conflicts: list[ConflictDetail] = Field(default_factory=list)
    overall_severity: float = Field(default=0.0, ge=0.0, le=1.0)
    resolution_applied: str = Field(default="")


# ===========================================================================
# System Readiness
# ===========================================================================

class ModuleReadiness(BaseModel):
    """Readiness status of a single module."""

    module: ProvenanceSource
    healthy: bool
    latency_ms: float = Field(default=0.0, ge=0.0)
    error: Optional[str] = None
    last_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SystemReadiness(BaseModel):
    """Aggregated system readiness across all modules."""

    ready: bool
    healthy_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    modules: list[ModuleReadiness] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall_latency_ms: float = Field(default=0.0, ge=0.0)


# ===========================================================================
# Monitoring Counters
# ===========================================================================

class MonitoringCounters(BaseModel):
    """Counters and gauges for the decision engine."""

    total_evaluations: int = Field(default=0, ge=0)
    actionable_decisions: int = Field(default=0, ge=0)
    no_trade_decisions: int = Field(default=0, ge=0)
    blocked_decisions: int = Field(default=0, ge=0)
    invalid_decisions: int = Field(default=0, ge=0)
    expired_decisions: int = Field(default=0, ge=0)
    gate_failures: dict[str, int] = Field(default_factory=dict, description="Gate name → failure count")
    avg_evaluation_ms: float = Field(default=0.0, ge=0.0)
    emergency_disable_count: int = Field(default=0, ge=0)
    idempotency_cache_hits: int = Field(default=0, ge=0)
    idempotency_cache_misses: int = Field(default=0, ge=0)
    retention_cleanups: int = Field(default=0, ge=0)
    last_evaluation_at: Optional[datetime] = None


# ===========================================================================
# Final Decision
# ===========================================================================

class FinalDecision(BaseModel):
    """
    The complete output of the Phase 10 decision engine.

    This is the single source of truth for whether a trade should be taken.
    It combines signal evaluation, intelligence clearance, and trade plan
    validation into a unified decision with full traceability.
    """

    # Identity
    decision_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique decision identifier",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the decision was created",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="When the decision was last updated",
    )

    # State machine
    state: FinalDecisionState = Field(
        default=FinalDecisionState.EVALUATING,
        description="Current lifecycle state",
    )

    # Direction (only meaningful when state is ACTIONABLE)
    direction: FinalDecisionDirection = Field(
        default=FinalDecisionDirection.NONE,
        description="Trading direction if ACTIONABLE",
    )

    # Source references
    signal_id: Optional[str] = Field(default=None, description="Phase 6 signal ID")
    plan_id: Optional[str] = Field(default=None, description="Phase 7 trade plan ID")
    intelligence_id: Optional[str] = Field(default=None, description="Phase 8 intelligence decision ID")
    instrument: str = Field(default="XAU/USD", description="Instrument this decision is for")

    # Gate results
    gates: list[GateResult] = Field(default_factory=list)
    gates_passed: int = Field(default=0, ge=0)
    gates_failed: int = Field(default=0, ge=0)
    gates_total: int = Field(default=0, ge=0)

    # Composite scores
    confidence: int = Field(default=0, ge=0, le=100, description="Composite confidence score 0-100")
    quality: int = Field(default=0, ge=0, le=100, description="Composite quality score 0-100")

    # Explainability
    explainability: Optional[ExplainabilityChain] = None

    # Provenance
    provenance: Optional[ProvenanceRecord] = None

    # Conflicts
    conflicts: Optional[ConflictReport] = None

    # Timing
    ttl_seconds: int = Field(default=300, ge=0, description="Time-to-live in seconds")
    expires_at: Optional[datetime] = Field(default=None, description="When this decision expires")

    # Rejection/blocking
    rejection_reason: Optional[str] = Field(default=None, description="Why the decision was rejected/blocked")
    blocked_by_gate: Optional[GateName] = Field(default=None, description="Which gate blocked the decision")

    # Metadata
    decision_version: str = Field(default="1.0.0", description="Decision logic version")
    idempotency_key: Optional[str] = Field(default=None, description="Idempotency key for deduplication")


# ===========================================================================
# Retention Policy
# ===========================================================================

class RetentionPolicy(BaseModel):
    """Data retention configuration and state."""

    max_age_days: int = Field(default=30, ge=1, le=365)
    max_entries: int = Field(default=10000, ge=100, le=1000000)
    entries_removed: int = Field(default=0, ge=0)
    last_cleanup: Optional[datetime] = None


# ===========================================================================
# API Request/Response Models
# ===========================================================================

class EvaluateDecisionRequest(BaseModel):
    """Request to evaluate a decision for a signal."""

    signal_id: str = Field(description="Phase 6 signal ID to evaluate")
    instrument: str = Field(default="XAU/USD", description="Instrument")
    force: bool = Field(default=False, description="Force re-evaluation even if idempotent")
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)


class DecisionSummary(BaseModel):
    """Compact decision summary for list responses."""

    decision_id: str
    state: FinalDecisionState
    direction: FinalDecisionDirection
    instrument: str
    signal_id: Optional[str] = None
    confidence: int = 0
    quality: int = 0
    gates_passed: int = 0
    gates_failed: int = 0
    rejection_reason: Optional[str] = None
    created_at: str
    expires_at: Optional[str] = None


class EmergencyToggleRequest(BaseModel):
    """Request to toggle emergency disable."""

    disable: bool = Field(description="True to disable, False to re-enable")
    reason: str = Field(default="Manual emergency toggle", description="Reason for the toggle")


class EmergencyToggleResponse(BaseModel):
    """Response from emergency toggle."""

    success: bool
    emergency_disable: bool
    message: str
    toggled_at: str


# ===========================================================================
# Helpers
# ===========================================================================

def compute_idempotency_key(
    signal_id: str,
    plan_id: Optional[str] = None,
    intelligence_id: Optional[str] = None,
) -> str:
    """
    Compute a deterministic idempotency key from input references.

    Same inputs always produce the same key, enabling deduplication.
    """
    payload = {
        "signal_id": signal_id,
        "plan_id": plan_id or "",
        "intelligence_id": intelligence_id or "",
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
