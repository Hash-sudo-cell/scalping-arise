"""
Scalping Arise — Gate Engine

Evaluates each gate in the decision pipeline. Gates are modular,
configurable, and each returns a GateResult. The engine runs gates
in order and short-circuits on required gate failures.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.modules.decision.config import DecisionEngineSettings, FailPolicy
from app.modules.decision.models import (
    FinalDecisionDirection,
    GateDefinition,
    GateName,
    GateResult,
    GateStatus,
    ProvenanceSource,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Gate pipeline definition
# ---------------------------------------------------------------------------

def build_default_gate_pipeline() -> list[GateDefinition]:
    """Build the default gate pipeline in evaluation order."""
    return [
        GateDefinition(
            gate=GateName.EMERGENCY_DISABLE,
            enabled=True,
            required=True,
            description="Master kill switch — blocks all decisions when active",
        ),
        GateDefinition(
            gate=GateName.SIGNAL_FRESHNESS,
            enabled=True,
            required=True,
            description="Ensures the signal is recent enough to act on",
        ),
        GateDefinition(
            gate=GateName.SIGNAL_QUALITY,
            enabled=True,
            required=True,
            description="Ensures signal quality meets minimum threshold",
        ),
        GateDefinition(
            gate=GateName.SIGNAL_CONFIDENCE,
            enabled=True,
            required=True,
            description="Ensures signal confidence meets minimum threshold",
        ),
        GateDefinition(
            gate=GateName.EVENT_RISK,
            enabled=True,
            required=False,
            description="Checks event/news risk clearance from Phase 8",
        ),
        GateDefinition(
            gate=GateName.STRATEGY_STATE,
            enabled=True,
            required=False,
            description="Checks strategy performance state from Phase 8",
        ),
        GateDefinition(
            gate=GateName.PLAN_VALIDITY,
            enabled=True,
            required=True,
            description="Ensures trade plan is valid and complete",
        ),
        GateDefinition(
            gate=GateName.PLAN_RISK_LIMITS,
            enabled=True,
            required=True,
            description="Ensures plan risk is within configured limits",
        ),
        GateDefinition(
            gate=GateName.PLAN_RR_MINIMUM,
            enabled=True,
            required=True,
            description="Ensures plan risk:reward meets minimum threshold",
        ),
        GateDefinition(
            gate=GateName.PLAN_FRESHNESS,
            enabled=True,
            required=True,
            description="Ensures trade plan is recent enough",
        ),
        GateDefinition(
            gate=GateName.SYSTEM_READINESS,
            enabled=True,
            required=True,
            description="Ensures system modules are healthy",
        ),
        GateDefinition(
            gate=GateName.CONFLICT_CHECK,
            enabled=True,
            required=False,
            description="Checks for conflicts between signal and plan",
        ),
    ]


# ---------------------------------------------------------------------------
# Individual gate evaluators
# ---------------------------------------------------------------------------

def _eval_emergency_disable(
    settings: DecisionEngineSettings,
    **_kwargs: Any,
) -> GateResult:
    """Gate: emergency kill switch."""
    if settings.emergency_disable:
        return GateResult(
            gate=GateName.EMERGENCY_DISABLE,
            status=GateStatus.FAILED,
            reason="Emergency disable is active — all decisions blocked",
        )
    return GateResult(
        gate=GateName.EMERGENCY_DISABLE,
        status=GateStatus.PASSED,
        reason="Emergency disable is not active",
    )


def _eval_signal_freshness(
    *,
    signal_age_seconds: Optional[float] = None,
    decision_ttl: int = 300,
    **_kwargs: Any,
) -> GateResult:
    """Gate: signal freshness — signal must not be older than the decision TTL."""
    if signal_age_seconds is None:
        return GateResult(
            gate=GateName.SIGNAL_FRESHNESS,
            status=GateStatus.PASSED,
            reason="Signal age not provided — skipping freshness check",
        )
    if signal_age_seconds > decision_ttl:
        return GateResult(
            gate=GateName.SIGNAL_FRESHNESS,
            status=GateStatus.FAILED,
            reason=f"Signal is {signal_age_seconds:.0f}s old, max allowed is {decision_ttl}s",
            details={"age_seconds": signal_age_seconds, "max_seconds": decision_ttl},
        )
    return GateResult(
        gate=GateName.SIGNAL_FRESHNESS,
        status=GateStatus.PASSED,
        reason=f"Signal age {signal_age_seconds:.0f}s is within TTL",
        details={"age_seconds": signal_age_seconds},
    )


def _eval_signal_quality(
    *,
    signal_quality: Optional[int] = None,
    min_quality: int = 40,
    **_kwargs: Any,
) -> GateResult:
    """Gate: signal quality threshold."""
    if signal_quality is None:
        return GateResult(
            gate=GateName.SIGNAL_QUALITY,
            status=GateStatus.FAILED,
            reason="Signal quality score not available",
        )
    if signal_quality < min_quality:
        return GateResult(
            gate=GateName.SIGNAL_QUALITY,
            status=GateStatus.FAILED,
            reason=f"Signal quality {signal_quality} is below minimum {min_quality}",
            details={"quality": signal_quality, "min_required": min_quality},
        )
    return GateResult(
        gate=GateName.SIGNAL_QUALITY,
        status=GateStatus.PASSED,
        reason=f"Signal quality {signal_quality} meets threshold {min_quality}",
        details={"quality": signal_quality},
    )


def _eval_signal_confidence(
    *,
    signal_confidence: Optional[int] = None,
    min_confidence: int = 50,
    **_kwargs: Any,
) -> GateResult:
    """Gate: signal confidence threshold."""
    if signal_confidence is None:
        return GateResult(
            gate=GateName.SIGNAL_CONFIDENCE,
            status=GateStatus.FAILED,
            reason="Signal confidence score not available",
        )
    if signal_confidence < min_confidence:
        return GateResult(
            gate=GateName.SIGNAL_CONFIDENCE,
            status=GateStatus.FAILED,
            reason=f"Signal confidence {signal_confidence} is below minimum {min_confidence}",
            details={"confidence": signal_confidence, "min_required": min_confidence},
        )
    return GateResult(
        gate=GateName.SIGNAL_CONFIDENCE,
        status=GateStatus.PASSED,
        reason=f"Signal confidence {signal_confidence} meets threshold {min_confidence}",
        details={"confidence": signal_confidence},
    )


def _eval_event_risk(
    *,
    event_decision: Optional[str] = None,
    fail_policy: FailPolicy = FailPolicy.FAIL_CLOSED,
    **_kwargs: Any,
) -> GateResult:
    """Gate: event risk clearance from Phase 8."""
    if event_decision is None:
        if fail_policy == FailPolicy.FAIL_OPEN:
            return GateResult(
                gate=GateName.EVENT_RISK,
                status=GateStatus.SKIPPED,
                reason="Event intelligence unavailable — fail-open policy applied",
            )
        return GateResult(
            gate=GateName.EVENT_RISK,
            status=GateStatus.FAILED,
            reason="Event intelligence unavailable — fail-closed policy applied",
        )
    if event_decision == "block":
        return GateResult(
            gate=GateName.EVENT_RISK,
            status=GateStatus.FAILED,
            reason="Event intelligence issued a BLOCK decision",
            details={"event_decision": event_decision},
        )
    if event_decision == "restrict":
        return GateResult(
            gate=GateName.EVENT_RISK,
            status=GateStatus.PASSED,
            reason="Event intelligence issued RESTRICT — decision allowed with caution",
            details={"event_decision": event_decision},
        )
    return GateResult(
        gate=GateName.EVENT_RISK,
        status=GateStatus.PASSED,
        reason="Event intelligence issued ALLOW",
        details={"event_decision": event_decision},
    )


def _eval_strategy_state(
    *,
    strategy_performance_state: Optional[str] = None,
    fail_policy: FailPolicy = FailPolicy.FAIL_CLOSED,
    **_kwargs: Any,
) -> GateResult:
    """Gate: strategy performance state from Phase 8."""
    if strategy_performance_state is None:
        if fail_policy == FailPolicy.FAIL_OPEN:
            return GateResult(
                gate=GateName.STRATEGY_STATE,
                status=GateStatus.SKIPPED,
                reason="Strategy state unavailable — fail-open policy applied",
            )
        return GateResult(
            gate=GateName.STRATEGY_STATE,
            status=GateStatus.FAILED,
            reason="Strategy state unavailable — fail-closed policy applied",
        )
    if strategy_performance_state == "disabled":
        return GateResult(
            gate=GateName.STRATEGY_STATE,
            status=GateStatus.FAILED,
            reason="Strategy is in DISABLED state — trading blocked",
            details={"strategy_state": strategy_performance_state},
        )
    if strategy_performance_state == "restricted":
        return GateResult(
            gate=GateName.STRATEGY_STATE,
            status=GateStatus.PASSED,
            reason="Strategy is in RESTRICTED state — proceeding with caution",
            details={"strategy_state": strategy_performance_state},
        )
    return GateResult(
        gate=GateName.STRATEGY_STATE,
        status=GateStatus.PASSED,
        reason=f"Strategy state is {strategy_performance_state}",
        details={"strategy_state": strategy_performance_state},
    )


def _eval_plan_validity(
    *,
    plan_valid: Optional[bool] = None,
    plan_state: Optional[str] = None,
    **_kwargs: Any,
) -> GateResult:
    """Gate: trade plan validity."""
    if plan_valid is None or plan_state is None:
        return GateResult(
            gate=GateName.PLAN_VALIDITY,
            status=GateStatus.FAILED,
            reason="Trade plan not available",
        )
    if not plan_valid:
        return GateResult(
            gate=GateName.PLAN_VALIDITY,
            status=GateStatus.FAILED,
            reason=f"Trade plan is not valid (state: {plan_state})",
            details={"plan_state": plan_state},
        )
    return GateResult(
        gate=GateName.PLAN_VALIDITY,
        status=GateStatus.PASSED,
        reason=f"Trade plan is valid (state: {plan_state})",
        details={"plan_state": plan_state},
    )


def _eval_plan_risk_limits(
    *,
    plan_within_risk_limits: Optional[bool] = None,
    **_kwargs: Any,
) -> GateResult:
    """Gate: plan risk limits."""
    if plan_within_risk_limits is None:
        return GateResult(
            gate=GateName.PLAN_RISK_LIMITS,
            status=GateStatus.FAILED,
            reason="Risk assessment not available",
        )
    if not plan_within_risk_limits:
        return GateResult(
            gate=GateName.PLAN_RISK_LIMITS,
            status=GateStatus.FAILED,
            reason="Trade plan exceeds configured risk limits",
        )
    return GateResult(
        gate=GateName.PLAN_RISK_LIMITS,
        status=GateStatus.PASSED,
        reason="Trade plan is within risk limits",
    )


def _eval_plan_rr_minimum(
    *,
    plan_risk_reward: Optional[float] = None,
    min_risk_reward: float = 1.5,
    **_kwargs: Any,
) -> GateResult:
    """Gate: plan minimum risk:reward ratio."""
    if plan_risk_reward is None:
        return GateResult(
            gate=GateName.PLAN_RR_MINIMUM,
            status=GateStatus.FAILED,
            reason="Risk:reward ratio not available",
        )
    if plan_risk_reward < min_risk_reward:
        return GateResult(
            gate=GateName.PLAN_RR_MINIMUM,
            status=GateStatus.FAILED,
            reason=f"R:R {plan_risk_reward:.2f} is below minimum {min_risk_reward}",
            details={"risk_reward": plan_risk_reward, "min_required": min_risk_reward},
        )
    return GateResult(
        gate=GateName.PLAN_RR_MINIMUM,
        status=GateStatus.PASSED,
        reason=f"R:R {plan_risk_reward:.2f} meets minimum {min_risk_reward}",
        details={"risk_reward": plan_risk_reward},
    )


def _eval_plan_freshness(
    *,
    plan_age_seconds: Optional[float] = None,
    max_age_seconds: int = 120,
    **_kwargs: Any,
) -> GateResult:
    """Gate: plan freshness — plan must not be older than max_age."""
    if plan_age_seconds is None:
        return GateResult(
            gate=GateName.PLAN_FRESHNESS,
            status=GateStatus.PASSED,
            reason="Plan age not provided — skipping freshness check",
        )
    if plan_age_seconds > max_age_seconds:
        return GateResult(
            gate=GateName.PLAN_FRESHNESS,
            status=GateStatus.FAILED,
            reason=f"Plan is {plan_age_seconds:.0f}s old, max allowed is {max_age_seconds}s",
            details={"age_seconds": plan_age_seconds, "max_seconds": max_age_seconds},
        )
    return GateResult(
        gate=GateName.PLAN_FRESHNESS,
        status=GateStatus.PASSED,
        reason=f"Plan age {plan_age_seconds:.0f}s is within limit",
        details={"age_seconds": plan_age_seconds},
    )


def _eval_system_readiness(
    *,
    system_ready: Optional[bool] = None,
    **_kwargs: Any,
) -> GateResult:
    """Gate: system readiness."""
    if system_ready is None:
        return GateResult(
            gate=GateName.SYSTEM_READINESS,
            status=GateStatus.FAILED,
            reason="System readiness check not performed",
        )
    if not system_ready:
        return GateResult(
            gate=GateName.SYSTEM_READINESS,
            status=GateStatus.FAILED,
            reason="System is not ready — critical modules unhealthy",
        )
    return GateResult(
        gate=GateName.SYSTEM_READINESS,
        status=GateStatus.PASSED,
        reason="System is ready — all critical modules healthy",
    )


def _eval_conflict_check(
    *,
    has_conflicts: Optional[bool] = None,
    conflict_severity: Optional[float] = None,
    **_kwargs: Any,
) -> GateResult:
    """Gate: conflict check between signal and plan."""
    if has_conflicts is None:
        return GateResult(
            gate=GateName.CONFLICT_CHECK,
            status=GateStatus.SKIPPED,
            reason="No conflict data available — skipping",
        )
    if has_conflicts and conflict_severity is not None and conflict_severity >= 0.8:
        return GateResult(
            gate=GateName.CONFLICT_CHECK,
            status=GateStatus.FAILED,
            reason=f"Critical conflict detected (severity: {conflict_severity:.2f})",
            details={"severity": conflict_severity},
        )
    if has_conflicts:
        return GateResult(
            gate=GateName.CONFLICT_CHECK,
            status=GateStatus.PASSED,
            reason=f"Minor conflict detected (severity: {conflict_severity or 0.0:.2f}) — proceeding",
            details={"severity": conflict_severity or 0.0},
        )
    return GateResult(
        gate=GateName.CONFLICT_CHECK,
        status=GateStatus.PASSED,
        reason="No conflicts detected",
    )


# ---------------------------------------------------------------------------
# Gate dispatch table
# ---------------------------------------------------------------------------

_GATE_EVALUATORS: dict[GateName, Any] = {
    GateName.EMERGENCY_DISABLE: _eval_emergency_disable,
    GateName.SIGNAL_FRESHNESS: _eval_signal_freshness,
    GateName.SIGNAL_QUALITY: _eval_signal_quality,
    GateName.SIGNAL_CONFIDENCE: _eval_signal_confidence,
    GateName.EVENT_RISK: _eval_event_risk,
    GateName.STRATEGY_STATE: _eval_strategy_state,
    GateName.PLAN_VALIDITY: _eval_plan_validity,
    GateName.PLAN_RISK_LIMITS: _eval_plan_risk_limits,
    GateName.PLAN_RR_MINIMUM: _eval_plan_rr_minimum,
    GateName.PLAN_FRESHNESS: _eval_plan_freshness,
    GateName.SYSTEM_READINESS: _eval_system_readiness,
    GateName.CONFLICT_CHECK: _eval_conflict_check,
}


# ---------------------------------------------------------------------------
# Gate Engine
# ---------------------------------------------------------------------------

class GateEngine:
    """
    Evaluates the full gate pipeline for a decision.

    Runs each gate in order, short-circuits on required gate failures,
    and returns the full list of GateResults.
    """

    def __init__(
        self,
        settings: Optional[DecisionEngineSettings] = None,
        pipeline: Optional[list[GateDefinition]] = None,
    ) -> None:
        self._settings = settings
        self._pipeline = pipeline or build_default_gate_pipeline()

    def evaluate(
        self,
        *,
        signal_age_seconds: Optional[float] = None,
        signal_quality: Optional[int] = None,
        signal_confidence: Optional[int] = None,
        event_decision: Optional[str] = None,
        strategy_performance_state: Optional[str] = None,
        plan_valid: Optional[bool] = None,
        plan_state: Optional[str] = None,
        plan_within_risk_limits: Optional[bool] = None,
        plan_risk_reward: Optional[float] = None,
        plan_age_seconds: Optional[float] = None,
        system_ready: Optional[bool] = None,
        has_conflicts: Optional[bool] = None,
        conflict_severity: Optional[float] = None,
    ) -> list[GateResult]:
        """
        Run the full gate pipeline.

        Returns the list of GateResults in pipeline order.
        Short-circuits: if a required gate fails, subsequent gates
        are recorded as SKIPPED.
        """
        from app.modules.decision.config import get_decision_engine_settings

        settings = self._settings or get_decision_engine_settings()

        context: dict[str, Any] = {
            "signal_age_seconds": signal_age_seconds,
            "signal_quality": signal_quality,
            "signal_confidence": signal_confidence,
            "event_decision": event_decision,
            "strategy_performance_state": strategy_performance_state,
            "plan_valid": plan_valid,
            "plan_state": plan_state,
            "plan_within_risk_limits": plan_within_risk_limits,
            "plan_risk_reward": plan_risk_reward,
            "plan_age_seconds": plan_age_seconds,
            "system_ready": system_ready,
            "has_conflicts": has_conflicts,
            "conflict_severity": conflict_severity,
            "decision_ttl": settings.decision_ttl_seconds,
            "min_quality": settings.min_signal_quality,
            "min_confidence": settings.min_signal_confidence,
            "min_risk_reward": settings.min_risk_reward,
            "max_age_seconds": settings.max_plan_age_seconds,
        }

        results: list[GateResult] = []
        short_circuited = False

        for gate_def in self._pipeline:
            if not gate_def.enabled:
                results.append(GateResult(
                    gate=gate_def.gate,
                    status=GateStatus.SKIPPED,
                    reason="Gate is disabled",
                ))
                continue

            if short_circuited:
                results.append(GateResult(
                    gate=gate_def.gate,
                    status=GateStatus.SKIPPED,
                    reason="Skipped due to prior required gate failure",
                ))
                continue

            evaluator = _GATE_EVALUATORS.get(gate_def.gate)
            if evaluator is None:
                results.append(GateResult(
                    gate=gate_def.gate,
                    status=GateStatus.ERROR,
                    reason=f"No evaluator registered for gate {gate_def.gate.value}",
                ))
                if gate_def.required:
                    short_circuited = True
                continue

            # Determine fail policy for this gate
            if gate_def.gate == GateName.EVENT_RISK:
                fail_policy = settings.event_risk_fail_policy
            elif gate_def.gate == GateName.STRATEGY_STATE:
                fail_policy = settings.strategy_state_fail_policy
            elif gate_def.fail_policy == "fail_open":
                fail_policy = FailPolicy.FAIL_OPEN
            else:
                fail_policy = FailPolicy.FAIL_CLOSED

            # Evaluate with timing
            t0 = time.monotonic()
            try:
                result = evaluator(
                    settings=settings,
                    fail_policy=fail_policy,
                    **context,
                )
            except Exception as exc:
                logger.exception("Gate %s raised exception", gate_def.gate.value)
                # Apply fail policy on exception
                if fail_policy == FailPolicy.FAIL_OPEN:
                    result = GateResult(
                        gate=gate_def.gate,
                        status=GateStatus.SKIPPED,
                        reason=f"Gate raised exception — fail-open applied: {exc}",
                    )
                else:
                    result = GateResult(
                        gate=gate_def.gate,
                        status=GateStatus.FAILED,
                        reason=f"Gate raised exception — fail-closed applied: {exc}",
                    )
            elapsed_ms = (time.monotonic() - t0) * 1000
            result.evaluation_ms = round(elapsed_ms, 3)
            results.append(result)

            # Short-circuit on required gate failure
            if gate_def.required and result.status == GateStatus.FAILED:
                short_circuited = True
                logger.info(
                    "Gate engine short-circuited at %s (required gate failed)",
                    gate_def.gate.value,
                )

        return results

    def count_gates(self, results: list[GateResult]) -> dict[str, int]:
        """Count gate results by status."""
        counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "total": len(results)}
        for r in results:
            if r.status == GateStatus.PASSED:
                counts["passed"] += 1
            elif r.status == GateStatus.FAILED:
                counts["failed"] += 1
            elif r.status == GateStatus.SKIPPED:
                counts["skipped"] += 1
            elif r.status == GateStatus.ERROR:
                counts["error"] += 1
        return counts

    def any_required_failed(self, results: list[GateResult]) -> bool:
        """Check if any required gate failed (considering pipeline order)."""
        for gate_def in self._pipeline:
            if not gate_def.enabled or not gate_def.required:
                continue
            for r in results:
                if r.gate == gate_def.gate and r.status == GateStatus.FAILED:
                    return True
        return False
