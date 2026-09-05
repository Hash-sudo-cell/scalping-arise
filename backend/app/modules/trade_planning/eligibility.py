"""
Scalping Arise — Signal Eligibility Gate

Determines whether a Phase 6 signal is eligible for trade planning.
Checks signal state, confidence, quality, and instrument availability.
"""

from __future__ import annotations

from typing import Optional

from app.modules.signal_engine.models import DecisionType, SignalRecord, SignalState
from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.instrument_specs import is_instrument_supported
from app.modules.trade_planning.models import EligibilityCheck, EligibilityResult


def check_signal_eligibility(
    signal: SignalRecord,
    settings: Optional[TradePlanningSettings] = None,
) -> EligibilityResult:
    """
    Evaluate whether a signal is eligible for trade planning.

    Checks performed:
    1. Signal decision is BUY or SELL (not NO_TRADE)
    2. Signal state is ACTIVE (if require_signal_active)
    3. Confidence meets minimum threshold
    4. Quality meets minimum threshold
    5. Instrument is supported
    """
    settings = settings or get_trade_planning_settings()
    checks: list[EligibilityCheck] = []

    # 1. Decision must be actionable
    decision_ok = signal.decision in (DecisionType.BUY, DecisionType.SELL)
    checks.append(EligibilityCheck(
        check_name="signal_decision",
        passed=decision_ok,
        reason="" if decision_ok else f"Signal decision is {signal.decision.value}, not actionable",
    ))

    # 2. Signal state must be ACTIVE
    if settings.require_signal_active:
        state_ok = signal.state == SignalState.ACTIVE
        checks.append(EligibilityCheck(
            check_name="signal_state",
            passed=state_ok,
            reason="" if state_ok else f"Signal state is {signal.state.value}, expected active",
        ))

    # 3. Confidence threshold
    confidence_ok = True
    if signal.confidence is not None:
        confidence_ok = signal.confidence.confidence_0_100 >= settings.min_signal_confidence_0_100
        checks.append(EligibilityCheck(
            check_name="signal_confidence",
            passed=confidence_ok,
            reason=(
                "" if confidence_ok
                else f"Confidence {signal.confidence.confidence_0_100} < minimum {settings.min_signal_confidence_0_100}"
            ),
        ))
    else:
        checks.append(EligibilityCheck(
            check_name="signal_confidence",
            passed=False,
            reason="Signal has no confidence score",
        ))

    # 4. Quality threshold
    quality_ok = True
    if signal.quality is not None:
        quality_ok = signal.quality.score >= settings.min_signal_quality_0_100
        checks.append(EligibilityCheck(
            check_name="signal_quality",
            passed=quality_ok,
            reason=(
                "" if quality_ok
                else f"Quality {signal.quality.score} < minimum {settings.min_signal_quality_0_100}"
            ),
        ))
    else:
        checks.append(EligibilityCheck(
            check_name="signal_quality",
            passed=False,
            reason="Signal has no quality score",
        ))

    # 5. Instrument support
    instrument_ok = is_instrument_supported(signal.instrument)
    checks.append(EligibilityCheck(
        check_name="instrument_supported",
        passed=instrument_ok,
        reason="" if instrument_ok else f"Instrument {signal.instrument} not registered",
    ))

    # Aggregate
    all_passed = all(c.passed for c in checks)
    blocked = next((c.check_name for c in checks if not c.passed), None)

    return EligibilityResult(
        eligible=all_passed,
        checks=checks,
        blocked_by=blocked,
    )
