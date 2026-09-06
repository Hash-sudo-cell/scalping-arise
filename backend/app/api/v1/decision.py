"""
Scalping Arise — Decision Engine API Endpoints

Phase 10 API for final decisions, explainability, provenance,
audit trail, emergency controls, and system readiness.

This module is an orchestrator + safety layer. It does NOT:
  - Generate signals (Phase 6)
  - Plan trades (Phase 7)
  - Fetch market data (Phase 2)
  - Evaluate strategies (Phase 5)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.modules.decision.config import get_decision_engine_settings
from app.modules.decision.service import DecisionEngineService

router = APIRouter(prefix="/decision", tags=["decision"])

# Service singleton — same pattern as other modules
_service: Optional[DecisionEngineService] = None


def _get_service() -> DecisionEngineService:
    """Get or create the decision engine service singleton."""
    global _service
    if _service is None:
        settings = get_decision_engine_settings()
        _service = DecisionEngineService(settings=settings)
    return _service


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    """Request to evaluate a decision for a signal."""

    signal_id: str = Field(description="Phase 6 signal ID to evaluate")
    instrument: str = Field(default="XAU/USD", description="Instrument")
    signal_direction: Optional[str] = Field(default=None, description="Signal direction (buy/sell)")
    signal_confidence: Optional[int] = Field(default=None, ge=0, le=100)
    signal_quality: Optional[int] = Field(default=None, ge=0, le=100)
    signal_age_seconds: Optional[float] = Field(default=None, ge=0)
    plan_id: Optional[str] = Field(default=None, description="Phase 7 trade plan ID")
    plan_valid: Optional[bool] = Field(default=None)
    plan_state: Optional[str] = Field(default=None)
    plan_side: Optional[str] = Field(default=None)
    plan_risk_reward: Optional[float] = Field(default=None, ge=0)
    plan_within_risk_limits: Optional[bool] = Field(default=None)
    plan_age_seconds: Optional[float] = Field(default=None, ge=0)
    intelligence_id: Optional[str] = Field(default=None)
    event_decision: Optional[str] = Field(default=None, description="allow/restrict/block")
    strategy_performance_state: Optional[str] = Field(default=None)
    force: bool = Field(default=False, description="Force re-evaluation")


class DecisionSummary(BaseModel):
    """Compact decision summary for list responses."""

    decision_id: str
    state: str
    direction: str
    instrument: str
    signal_id: Optional[str] = None
    plan_id: Optional[str] = None
    intelligence_id: Optional[str] = None
    confidence: int = 0
    quality: int = 0
    gates_passed: int = 0
    gates_failed: int = 0
    gates_total: int = 0
    rejection_reason: Optional[str] = None
    blocked_by_gate: Optional[str] = None
    created_at: str
    expires_at: Optional[str] = None


class EmergencyToggleRequest(BaseModel):
    """Request to toggle emergency disable."""

    disable: bool = Field(description="True to disable, False to re-enable")
    reason: str = Field(default="Manual emergency toggle", description="Reason for the toggle")


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_decision(d) -> dict:
    """Serialize a FinalDecision to a JSON-compatible dict."""
    result = {
        "decision_id": d.decision_id,
        "state": d.state.value,
        "direction": d.direction.value,
        "instrument": d.instrument,
        "signal_id": d.signal_id,
        "plan_id": d.plan_id,
        "intelligence_id": d.intelligence_id,
        "confidence": d.confidence,
        "quality": d.quality,
        "gates_passed": d.gates_passed,
        "gates_failed": d.gates_failed,
        "gates_total": d.gates_total,
        "rejection_reason": d.rejection_reason,
        "blocked_by_gate": d.blocked_by_gate.value if d.blocked_by_gate else None,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "expires_at": d.expires_at.isoformat() if d.expires_at else None,
        "ttl_seconds": d.ttl_seconds,
        "decision_version": d.decision_version,
        "idempotency_key": d.idempotency_key,
    }

    if d.gates:
        result["gates"] = [
            {
                "gate": g.gate.value,
                "status": g.status.value,
                "reason": g.reason,
                "evaluation_ms": g.evaluation_ms,
                "details": g.details,
            }
            for g in d.gates
        ]

    if d.explainability:
        result["explainability"] = {
            "summary": d.explainability.summary,
            "reasons": [
                {
                    "code": r.code,
                    "message": r.message,
                    "source": r.source.value,
                    "weight": r.weight,
                    "evidence": r.evidence,
                }
                for r in d.explainability.reasons
            ],
            "contributing_factors": d.explainability.contributing_factors,
            "blocking_factors": d.explainability.blocking_factors,
            "confidence_breakdown": d.explainability.confidence_breakdown,
        }

    if d.provenance:
        result["provenance"] = {
            "decision_id": d.provenance.decision_id,
            "total_evaluation_ms": d.provenance.total_evaluation_ms,
            "modules_healthy": d.provenance.modules_healthy,
            "modules_total": d.provenance.modules_total,
            "contributions": [
                {
                    "source": c.source.value,
                    "module_version": c.module_version,
                    "data_provided": c.data_provided,
                    "evaluation_time_ms": c.evaluation_time_ms,
                    "healthy": c.healthy,
                }
                for c in d.provenance.contributions
            ],
        }

    if d.conflicts:
        result["conflicts"] = {
            "has_conflicts": d.conflicts.has_conflicts,
            "overall_severity": d.conflicts.overall_severity,
            "resolution_applied": d.conflicts.resolution_applied,
            "conflicts": [
                {
                    "conflict_type": c.conflict_type.value,
                    "description": c.description,
                    "severity": c.severity,
                    "involved_components": c.involved_components,
                    "resolution": c.resolution,
                }
                for c in d.conflicts.conflicts
            ],
        }

    return result


def _serialize_decision_summary(d) -> dict:
    """Serialize a FinalDecision to a compact summary dict."""
    return {
        "decision_id": d.decision_id,
        "state": d.state.value,
        "direction": d.direction.value,
        "instrument": d.instrument,
        "signal_id": d.signal_id,
        "confidence": d.confidence,
        "quality": d.quality,
        "gates_passed": d.gates_passed,
        "gates_failed": d.gates_failed,
        "gates_total": d.gates_total,
        "rejection_reason": d.rejection_reason,
        "created_at": d.created_at.isoformat(),
        "expires_at": d.expires_at.isoformat() if d.expires_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/decision/health
# ---------------------------------------------------------------------------

@router.get("/health")
async def decision_health() -> dict:
    """Decision engine health check."""
    service = _get_service()
    return await service.health_check()


# ---------------------------------------------------------------------------
# GET /api/v1/decision/capabilities
# ---------------------------------------------------------------------------

@router.get("/capabilities")
async def decision_capabilities() -> dict:
    """Expose decision engine capabilities and configuration."""
    service = _get_service()
    return await service.get_capabilities()


# ---------------------------------------------------------------------------
# POST /api/v1/decision/evaluate
# ---------------------------------------------------------------------------

@router.post("/evaluate")
async def decision_evaluate(request: EvaluateRequest) -> dict:
    """
    Run the full decision pipeline for a signal.

    Consumes Phase 6 signal, Phase 7 plan, and Phase 8 intelligence
    to produce a FinalDecision with full traceability.
    """
    service = _get_service()
    decision = await service.evaluate_decision(
        signal_id=request.signal_id,
        instrument=request.instrument,
        signal_direction=request.signal_direction,
        signal_confidence=request.signal_confidence,
        signal_quality=request.signal_quality,
        signal_age_seconds=request.signal_age_seconds,
        plan_id=request.plan_id,
        plan_valid=request.plan_valid,
        plan_state=request.plan_state,
        plan_side=request.plan_side,
        plan_risk_reward=request.plan_risk_reward,
        plan_within_risk_limits=request.plan_within_risk_limits,
        plan_age_seconds=request.plan_age_seconds,
        intelligence_id=request.intelligence_id,
        event_decision=request.event_decision,
        strategy_performance_state=request.strategy_performance_state,
        force=request.force,
    )
    return _serialize_decision(decision)


# ---------------------------------------------------------------------------
# GET /api/v1/decision/active
# ---------------------------------------------------------------------------

@router.get("/active")
async def decision_active() -> dict:
    """List all active (non-terminal) decisions."""
    service = _get_service()
    decisions = service.get_active_decisions()
    return {
        "count": len(decisions),
        "decisions": [_serialize_decision_summary(d) for d in decisions],
    }


# ---------------------------------------------------------------------------
# GET /api/v1/decision/history
# ---------------------------------------------------------------------------

@router.get("/history")
async def decision_history(
    limit: int = Query(default=20, ge=1, le=100, description="Max entries to return"),
) -> dict:
    """Get recent decision history."""
    service = _get_service()
    decisions = service.get_history(limit=limit)
    return {
        "count": len(decisions),
        "decisions": [_serialize_decision_summary(d) for d in decisions],
    }


# ---------------------------------------------------------------------------
# GET /api/v1/decision/monitoring/counters
# ---------------------------------------------------------------------------

@router.get("/monitoring/counters")
async def decision_counters() -> dict:
    """Get monitoring counters."""
    service = _get_service()
    counters = service.get_monitoring_counters()
    return counters.model_dump(mode="json")


# ---------------------------------------------------------------------------
# POST /api/v1/decision/emergency/disable
# ---------------------------------------------------------------------------

@router.post("/emergency/disable")
async def decision_emergency_disable(request: EmergencyToggleRequest) -> dict:
    """Toggle emergency disable."""
    service = _get_service()
    if request.disable:
        status = service.emergency_disable(request.reason)
    else:
        status = service.emergency_enable(request.reason)
    return {
        "success": True,
        "emergency_disable": status["disabled"],
        "message": f"Emergency {'disabled' if status['disabled'] else 'enabled'}",
        "toggled_at": status["toggled_at"],
        "toggle_count": status["toggle_count"],
        "last_reason": status["last_reason"],
    }


# ---------------------------------------------------------------------------
# GET /api/v1/decision/emergency/status
# ---------------------------------------------------------------------------

@router.get("/emergency/status")
async def decision_emergency_status() -> dict:
    """Get emergency disable status."""
    service = _get_service()
    return service.get_emergency_status()


# ---------------------------------------------------------------------------
# GET /api/v1/decision/readiness
# ---------------------------------------------------------------------------

@router.get("/readiness")
async def decision_readiness() -> dict:
    """Get system readiness status."""
    service = _get_service()
    return await service.get_readiness()


# ---------------------------------------------------------------------------
# POST /api/v1/decision/retention/cleanup
# ---------------------------------------------------------------------------

@router.post("/retention/cleanup")
async def decision_retention_cleanup() -> dict:
    """Run retention cleanup."""
    service = _get_service()
    removed = service.run_retention_cleanup()
    return {"success": True, "removed": removed}


# ---------------------------------------------------------------------------
# GET /api/v1/decision/{decision_id}
# ---------------------------------------------------------------------------

@router.get("/{decision_id}")
async def decision_get(decision_id: str) -> dict:
    """Get a specific decision by ID."""
    service = _get_service()
    decision = service.get_decision(decision_id)
    if decision is None:
        return {"error": f"Decision {decision_id} not found"}
    return _serialize_decision(decision)


# ---------------------------------------------------------------------------
# POST /api/v1/decision/{decision_id}/invalidate
# ---------------------------------------------------------------------------

@router.post("/{decision_id}/invalidate")
async def decision_invalidate(
    decision_id: str,
    reason: str = Query(default="Manual invalidation", description="Reason"),
) -> dict:
    """Manually invalidate a decision."""
    service = _get_service()
    success = service.invalidate_decision(decision_id, reason)
    if not success:
        return {"success": False, "error": f"Decision {decision_id} not found or already terminal"}
    return {"success": True, "decision_id": decision_id, "reason": reason}


# ---------------------------------------------------------------------------
# GET /api/v1/decision/{decision_id}/audit
# ---------------------------------------------------------------------------

@router.get("/{decision_id}/audit")
async def decision_audit(decision_id: str) -> dict:
    """Get the full audit trail for a decision."""
    service = _get_service()
    entries = service.get_audit_trail(decision_id)
    return {
        "decision_id": decision_id,
        "count": len(entries),
        "entries": entries,
    }
