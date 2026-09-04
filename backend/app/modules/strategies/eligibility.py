"""
Scalping Arise — Strategy Eligibility Gate

Checks whether a strategy is eligible for detailed evaluation
before running conditions. Produces structured eligibility results.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.market_analysis.models import AnalysisResult, AnalysisStatus
from app.modules.market_data.models import SourceType
from app.modules.strategies.models import (
    EligibilityCheck,
    EligibilityCheckStatus,
    EligibilityResult,
    SourceCompatibilityPolicy,
    StrategyDefinition,
    TimeframeContext,
)
from app.modules.technical_features.models import FeatureResult, FeatureSetStatus

logger = logging.getLogger(__name__)


def check_source_compatibility(
    policy: SourceCompatibilityPolicy,
    source_types: list[str],
) -> tuple[bool, str]:
    """
    Check if the data sources satisfy the strategy's compatibility policy.

    Returns (passes, reason).
    """
    if not source_types:
        return False, "No source types available"

    unique_sources = set(source_types)

    if policy == SourceCompatibilityPolicy.SPOT_ONLY:
        if all(s == SourceType.SPOT.value for s in unique_sources):
            return True, "All sources are SPOT"
        return False, (
            f"SPOT_ONLY policy requires SPOT data, "
            f"but found: {', '.join(sorted(unique_sources))}"
        )

    if policy == SourceCompatibilityPolicy.SPOT_PREFERRED:
        if all(s == SourceType.SPOT.value for s in unique_sources):
            return True, "All sources are SPOT (preferred)"
        if all(s == SourceType.FUTURES_PROXY.value for s in unique_sources):
            return True, (
                "FUTURES_PROXY data accepted under SPOT_PREFERRED policy "
                "(explicit fallback — not SPOT)"
            )
        return False, (
            f"Mixed/incompatible sources under SPOT_PREFERRED: "
            f"{', '.join(sorted(unique_sources))}"
        )

    # FUTURES_PROXY_ALLOWED
    return True, "All sources accepted under FUTURES_PROXY_ALLOWED policy"


def run_eligibility_gate(
    strategy: StrategyDefinition,
    required_timeframes: list[str],
    timeframe_contexts: list[TimeframeContext],
    source_types_used: list[str],
    market_regime: Optional[str],
    feature_set_status: Optional[FeatureSetStatus],
    analysis_status: Optional[AnalysisStatus],
) -> EligibilityResult:
    """
    Run the eligibility gate for a strategy.

    Checks in order:
    1. Market data available (analysis completed)
    2. Required timeframes available
    3. Required feature sets usable
    4. Source compatibility
    5. Market regime compatible

    Returns a structured EligibilityResult.
    """
    checks: list[EligibilityCheck] = []
    eligible = True
    blocked_by: Optional[str] = None

    # --- Check 1: Market Analysis Available ---
    if analysis_status == AnalysisStatus.AVAILABLE:
        checks.append(EligibilityCheck(
            check_name="market_analysis_available",
            expected_state="available",
            actual_state="available",
            status=EligibilityCheckStatus.PASSED,
            reason="Market analysis completed successfully",
        ))
    elif analysis_status is None:
        checks.append(EligibilityCheck(
            check_name="market_analysis_available",
            expected_state="available",
            actual_state="missing",
            status=EligibilityCheckStatus.FAILED,
            reason="Market analysis was not provided",
        ))
        eligible = False
        blocked_by = "market_analysis_available"
    else:
        checks.append(EligibilityCheck(
            check_name="market_analysis_available",
            expected_state="available",
            actual_state=analysis_status.value,
            status=EligibilityCheckStatus.FAILED,
            reason=f"Market analysis is {analysis_status.value}",
        ))
        eligible = False
        blocked_by = "market_analysis_available"

    # --- Check 2: Required Timeframes Available ---
    available_tfs = {ctx.timeframe for ctx in timeframe_contexts}
    missing_tfs = [tf for tf in required_timeframes if tf not in available_tfs]

    if not missing_tfs:
        checks.append(EligibilityCheck(
            check_name="required_timeframes_available",
            expected_state=f"all of {required_timeframes}",
            actual_state=f"available: {sorted(available_tfs)}",
            status=EligibilityCheckStatus.PASSED,
            reason="All required timeframes have data",
        ))
    else:
        if eligible:
            eligible = False
            blocked_by = "required_timeframes_available"
        checks.append(EligibilityCheck(
            check_name="required_timeframes_available",
            expected_state=f"all of {required_timeframes}",
            actual_state=f"missing: {missing_tfs}",
            status=EligibilityCheckStatus.FAILED,
            reason=f"Missing required timeframes: {', '.join(missing_tfs)}",
        ))

    # --- Check 3: Feature Set Status ---
    if feature_set_status == FeatureSetStatus.READY:
        checks.append(EligibilityCheck(
            check_name="feature_set_usable",
            expected_state="ready",
            actual_state="ready",
            status=EligibilityCheckStatus.PASSED,
            reason="Feature set is ready",
        ))
    elif feature_set_status == FeatureSetStatus.WARMING_UP:
        if eligible:
            eligible = False
            blocked_by = "feature_set_usable"
        checks.append(EligibilityCheck(
            check_name="feature_set_usable",
            expected_state="ready",
            actual_state="warming_up",
            status=EligibilityCheckStatus.FAILED,
            reason="Feature set is still warming up",
        ))
    elif feature_set_status is None:
        if eligible:
            eligible = False
            blocked_by = "feature_set_usable"
        checks.append(EligibilityCheck(
            check_name="feature_set_usable",
            expected_state="ready",
            actual_state="missing",
            status=EligibilityCheckStatus.FAILED,
            reason="Feature set status was not provided",
        ))
    else:
        if eligible:
            eligible = False
            blocked_by = "feature_set_usable"
        checks.append(EligibilityCheck(
            check_name="feature_set_usable",
            expected_state="ready",
            actual_state=feature_set_status.value,
            status=EligibilityCheckStatus.FAILED,
            reason=f"Feature set is {feature_set_status.value}",
        ))

    # --- Check 4: Source Compatibility ---
    source_passes, source_reason = check_source_compatibility(
        strategy.source_compatibility_policy,
        source_types_used,
    )
    if source_passes:
        checks.append(EligibilityCheck(
            check_name="source_compatibility",
            expected_state=strategy.source_compatibility_policy.value,
            actual_state=f"sources: {', '.join(sorted(set(source_types_used)))}",
            status=EligibilityCheckStatus.PASSED,
            reason=source_reason,
        ))
    else:
        if eligible:
            eligible = False
            blocked_by = "source_compatibility"
        checks.append(EligibilityCheck(
            check_name="source_compatibility",
            expected_state=strategy.source_compatibility_policy.value,
            actual_state=f"sources: {', '.join(sorted(set(source_types_used)))}",
            status=EligibilityCheckStatus.FAILED,
            reason=source_reason,
        ))

    # --- Check 5: Market Regime Compatible ---
    if market_regime and strategy.applicable_market_regimes:
        if market_regime in strategy.applicable_market_regimes:
            checks.append(EligibilityCheck(
                check_name="regime_compatible",
                expected_state=f"one of {strategy.applicable_market_regimes}",
                actual_state=market_regime,
                status=EligibilityCheckStatus.PASSED,
                reason=f"Current regime '{market_regime}' is compatible",
            ))
        else:
            if eligible:
                eligible = False
                blocked_by = "regime_compatible"
            checks.append(EligibilityCheck(
                check_name="regime_compatible",
                expected_state=f"one of {strategy.applicable_market_regimes}",
                actual_state=market_regime,
                status=EligibilityCheckStatus.FAILED,
                reason=(
                    f"'{strategy.strategy_name}' is not applicable because "
                    f"the current market regime is '{market_regime}'. "
                    f"Applicable regimes: {', '.join(strategy.applicable_market_regimes)}"
                ),
            ))
    elif market_regime is None:
        if eligible:
            eligible = False
            blocked_by = "regime_compatible"
        checks.append(EligibilityCheck(
            check_name="regime_compatible",
            expected_state=f"one of {strategy.applicable_market_regimes}",
            actual_state="unknown",
            status=EligibilityCheckStatus.FAILED,
            reason="Market regime is not available",
        ))
    else:
        # Strategy has no regime restrictions — always passes
        checks.append(EligibilityCheck(
            check_name="regime_compatible",
            expected_state="no restriction",
            actual_state="no restriction",
            status=EligibilityCheckStatus.PASSED,
            reason="Strategy has no market regime restrictions",
        ))

    return EligibilityResult(
        eligible=eligible,
        checks=checks,
        blocked_by=blocked_by,
    )
