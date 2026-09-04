"""
Scalping Arise — Strategy Evaluation Service

Central orchestration layer for strategy evaluation.
Consumes outputs from Phase 3 (Market Analysis) and Phase 4 (Technical Features),
applies strategy definitions through the eligibility gate, condition engine,
invalidation evaluator, and quality scorer, producing structured evaluation results.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_analysis.models import AnalysisResult, AnalysisStatus, TrendState
from app.modules.market_data.models import Instrument, Timeframe
from app.modules.market_data.service import MarketDataService
from app.modules.market_analysis.service import MarketAnalysisService
from app.modules.technical_features.models import FeatureResult, FeatureSetStatus, TimeframeFeatureResult
from app.modules.technical_features.service import TechnicalFeatureService
from app.modules.strategies.config import StrategyEngineSettings, get_strategy_engine_settings
from app.modules.strategies.definitions import get_all_strategy_definitions, get_strategy_definition
from app.modules.strategies.eligibility import run_eligibility_gate
from app.modules.strategies.condition_engine import evaluate_conditions
from app.modules.strategies.invalidation import evaluate_invalidation_rules
from app.modules.strategies.quality import calculate_quality_score
from app.modules.strategies.models import (
    ConditionStatus,
    EligibilityResult,
    StrategyCapability,
    StrategyDefinition,
    StrategyDirection,
    StrategyEvaluationResult,
    StrategyEvaluationStatus,
    TimeframeContext,
)

logger = logging.getLogger(__name__)


def _determine_direction(
    analysis: Optional[AnalysisResult],
    features: Optional[FeatureResult],
) -> StrategyDirection:
    """Determine directional context from analysis and feature data."""
    # Prefer analysis trend
    if analysis and analysis.trend:
        if analysis.trend.state == TrendState.BULLISH:
            return StrategyDirection.BULLISH
        if analysis.trend.state == TrendState.BEARISH:
            return StrategyDirection.BEARISH
        if analysis.trend.state == TrendState.RANGING:
            return StrategyDirection.NEUTRAL

    # Fallback to EMA alignment
    if features and features.trend:
        from app.modules.technical_features.models import EMAAlignment
        if features.trend.alignment == EMAAlignment.BULLISH:
            return StrategyDirection.BULLISH
        if features.trend.alignment == EMAAlignment.BEARISH:
            return StrategyDirection.BEARISH

    return StrategyDirection.NONE


def _get_regime_state(analysis: Optional[AnalysisResult]) -> Optional[str]:
    """Extract regime state string from analysis."""
    if analysis and analysis.regime:
        return analysis.regime.state.value
    return None


def _build_timeframe_context(
    tf_result: TimeframeFeatureResult,
) -> TimeframeContext:
    """Build a TimeframeContext from a TimeframeFeatureResult."""
    meta = tf_result.result.metadata
    if meta:
        return TimeframeContext(
            timeframe=tf_result.timeframe,
            source_type=meta.source_type,
            provider=meta.provider,
            provider_instrument=meta.provider_instrument,
            candle_count=meta.candle_count,
        )
    return TimeframeContext(
        timeframe=tf_result.timeframe,
        source_type="unknown",
        provider="unknown",
        provider_instrument="unknown",
        candle_count=0,
    )


class StrategyEvaluationService:
    """
    Central strategy evaluation orchestration service.

    Flow:
        Phase 3 Market Analysis ──┐
                                  │
        Phase 4 Technical Features├──→ Strategy Evaluation Service
                                  │
        Strategy Definitions ─────┘
                                      ↓
                                 Eligibility Gate
                                      ↓
                                 Condition Evaluation
                                      ↓
                                 Invalidation Evaluation
                                      ↓
                                 Quality Assessment
                                      ↓
                                 Evaluation Snapshot
                                      ↓
                                 Strategy Evaluation Result
    """

    def __init__(
        self,
        market_data_service: Optional[MarketDataService] = None,
        analysis_service: Optional[MarketAnalysisService] = None,
        feature_service: Optional[TechnicalFeatureService] = None,
        settings: Optional[StrategyEngineSettings] = None,
    ) -> None:
        self._market_data = market_data_service or MarketDataService()
        self._analysis_service = analysis_service or MarketAnalysisService(
            market_data_service=self._market_data,
        )
        self._feature_service = feature_service or TechnicalFeatureService(
            market_data_service=self._market_data,
        )
        self._settings = settings or get_strategy_engine_settings()

    async def evaluate_strategy(
        self,
        strategy_id: str,
        instrument: str = "XAU/USD",
        timeframes: Optional[list[str]] = None,
        candle_limit: int = 300,
    ) -> StrategyEvaluationResult:
        """
        Evaluate a single strategy against current market data.

        Args:
            strategy_id: Strategy to evaluate.
            instrument: Canonical instrument.
            timeframes: Timeframes to use for evaluation.
            candle_limit: Number of candles per timeframe.

        Returns:
            StrategyEvaluationResult with full evaluation snapshot.
        """
        # Look up strategy definition
        strategy = get_strategy_definition(strategy_id)
        if strategy is None:
            return StrategyEvaluationResult(
                strategy_id=strategy_id,
                strategy_version="unknown",
                strategy_name="Unknown",
                instrument=instrument,
                status=StrategyEvaluationStatus.UNAVAILABLE,
                reason=f"Strategy '{strategy_id}' not found",
            )

        if not strategy.enabled:
            return StrategyEvaluationResult(
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                strategy_name=strategy.strategy_name,
                instrument=instrument,
                status=StrategyEvaluationStatus.UNAVAILABLE,
                reason=f"Strategy '{strategy.strategy_name}' is disabled",
            )

        # Use default timeframes if not provided
        if timeframes is None:
            timeframes = self._settings.default_evaluation_timeframes

        # --- Phase 3: Get Market Analysis (for primary timeframe) ---
        primary_tf = timeframes[0] if timeframes else "1h"
        try:
            analysis_result = await self._analysis_service.analyze(
                instrument=Instrument(instrument),
                timeframe=Timeframe(primary_tf),
                limit=candle_limit,
            )
        except Exception as e:
            logger.error("Market analysis failed: %s", e)
            analysis_result = None

        # --- Phase 4: Get Multi-Timeframe Features ---
        feature_results: dict[str, FeatureResult] = {}
        for tf in timeframes:
            try:
                feat_result = await self._feature_service.get_features(
                    timeframe=tf,
                    limit=candle_limit,
                )
                feature_results[tf] = feat_result
            except Exception as e:
                logger.error("Feature calculation failed for %s: %s", tf, e)
                feature_results[tf] = FeatureResult(
                    status=FeatureSetStatus.UNAVAILABLE,
                    reason=f"Calculation failed: {e}",
                )

        # Build timeframe contexts
        tf_contexts: list[TimeframeContext] = []
        for tf in timeframes:
            feat = feature_results.get(tf)
            if feat and feat.metadata:
                tf_contexts.append(TimeframeContext(
                    timeframe=tf,
                    source_type=feat.metadata.source_type,
                    provider=feat.metadata.provider,
                    provider_instrument=feat.metadata.provider_instrument,
                    candle_count=feat.metadata.candle_count,
                ))

        # Determine direction
        primary_features = feature_results.get(primary_tf)
        direction = _determine_direction(analysis_result, primary_features)

        # Get regime state
        regime_state = _get_regime_state(analysis_result)

        # Determine required timeframes from strategy definition
        required_tfs = [tr.timeframe for tr in strategy.required_timeframes]

        # Aggregate source types
        source_types_used = list({ctx.source_type for ctx in tf_contexts})

        # Determine overall feature set status
        feature_set_statuses = [f.feature_set_status for f in feature_results.values()]
        if all(s == FeatureSetStatus.READY for s in feature_set_statuses):
            overall_fs_status = FeatureSetStatus.READY
        elif any(s in (FeatureSetStatus.READY, FeatureSetStatus.WARMING_UP) for s in feature_set_statuses):
            overall_fs_status = FeatureSetStatus.WARMING_UP
        else:
            overall_fs_status = FeatureSetStatus.UNAVAILABLE

        # --- Eligibility Gate ---
        eligibility = run_eligibility_gate(
            strategy=strategy,
            required_timeframes=required_tfs,
            timeframe_contexts=tf_contexts,
            source_types_used=source_types_used,
            market_regime=regime_state,
            feature_set_status=overall_fs_status,
            analysis_status=analysis_result.status if analysis_result else None,
        )

        # If not eligible, return early
        if not eligibility.eligible:
            # Determine if NOT_APPLICABLE or INSUFFICIENT_DATA
            if eligibility.blocked_by == "regime_compatible":
                status = StrategyEvaluationStatus.NOT_APPLICABLE
            elif eligibility.blocked_by in ("feature_set_usable", "required_timeframes_available"):
                status = StrategyEvaluationStatus.INSUFFICIENT_DATA
            else:
                status = StrategyEvaluationStatus.UNAVAILABLE

            return StrategyEvaluationResult(
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                strategy_name=strategy.strategy_name,
                instrument=instrument,
                timeframe_contexts=tf_contexts,
                source_types_used=source_types_used,
                market_regime=regime_state,
                eligibility=eligibility,
                status=status,
                direction=direction,
                reason=eligibility.checks[-1].reason if eligibility.checks else "Not eligible",
            )

        # --- Condition Evaluation ---
        condition_results = evaluate_conditions(
            strategy=strategy,
            analysis=analysis_result,
            features=primary_features,
            direction=direction,
            regime_state=regime_state,
        )

        # --- Invalidation Evaluation ---
        invalidation_results = evaluate_invalidation_rules(
            strategy=strategy,
            analysis=analysis_result,
            direction=direction,
            regime_state=regime_state,
        )

        # Check if any invalidation triggered
        any_invalidated = any(r.triggered for r in invalidation_results)

        # --- Determine Status ---
        required_conditions = [
            r for r in condition_results
            if r.criticality.value in ("critical", "required")
        ]
        all_required_passed = all(
            r.status == ConditionStatus.PASSED for r in required_conditions
        )
        any_required_failed = any(
            r.status == ConditionStatus.FAILED for r in required_conditions
        )

        if any_invalidated:
            status = StrategyEvaluationStatus.INVALIDATED
            reason_parts = [r.reason for r in invalidation_results if r.triggered]
            reason = "Invalidated: " + "; ".join(reason_parts)
        elif all_required_passed:
            status = StrategyEvaluationStatus.QUALIFIED
            reason = "All required conditions passed, no invalidation triggered"
        elif any_required_failed:
            status = StrategyEvaluationStatus.NOT_QUALIFIED
            failed_conditions = [r for r in required_conditions if r.status == ConditionStatus.FAILED]
            reason = "Required conditions failed: " + "; ".join(r.reason for r in failed_conditions)
        else:
            status = StrategyEvaluationStatus.NOT_QUALIFIED
            reason = "Evaluation complete — not all required conditions met"

        # --- Quality Score ---
        quality_score = calculate_quality_score(
            strategy=strategy,
            condition_results=condition_results,
            direction=direction,
        )

        # --- Build Market Structure Summary ---
        structure_summary = None
        if analysis_result and analysis_result.structure:
            labels = analysis_result.structure.latest_labels
            if labels:
                structure_summary = f"Recent structure: {[l.value for l in labels[-5:]]}"

        return StrategyEvaluationResult(
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            strategy_name=strategy.strategy_name,
            instrument=instrument,
            timeframe_contexts=tf_contexts,
            source_types_used=source_types_used,
            market_regime=regime_state,
            market_structure_summary=structure_summary,
            eligibility=eligibility,
            condition_results=condition_results,
            invalidation_results=invalidation_results,
            quality_score=quality_score,
            status=status,
            direction=direction,
            reason=reason,
        )

    async def evaluate_all_strategies(
        self,
        instrument: str = "XAU/USD",
        timeframes: Optional[list[str]] = None,
        candle_limit: int = 300,
    ) -> list[StrategyEvaluationResult]:
        """
        Evaluate all enabled strategies.

        Returns a list of evaluation results, one per enabled strategy.
        """
        strategies = get_all_strategy_definitions()
        enabled = [s for s in strategies if s.enabled]

        results: list[StrategyEvaluationResult] = []
        for strategy in enabled:
            result = await self.evaluate_strategy(
                strategy_id=strategy.strategy_id,
                instrument=instrument,
                timeframes=timeframes,
                candle_limit=candle_limit,
            )
            results.append(result)

        return results

    async def health_check(self) -> dict:
        """Check if the strategy engine is operational."""
        try:
            settings = self._settings
            strategies = get_all_strategy_definitions()
            return {
                "status": "healthy",
                "module": "strategies",
                "configuration": {
                    "enabled": settings.is_enabled,
                    "max_strategies_per_evaluation": settings.max_strategies_per_evaluation,
                    "default_timeframes": settings.default_evaluation_timeframes,
                    "quality_scoring_enabled": settings.quality_score_enabled,
                },
                "strategies_registered": len(strategies),
                "strategies_enabled": sum(1 for s in strategies if s.enabled),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "module": "strategies",
                "error": str(e),
            }

    async def get_capabilities(self) -> dict:
        """Return strategy engine capabilities."""
        strategies = get_all_strategy_definitions()
        return {
            "module": "strategies",
            "status": "active" if self._settings.is_enabled else "disabled",
            "strategies": [
                StrategyCapability(
                    strategy_id=s.strategy_id,
                    strategy_version=s.strategy_version,
                    strategy_name=s.strategy_name,
                    enabled=s.enabled,
                    applicable_market_regimes=s.applicable_market_regimes,
                    required_timeframes=[tr.timeframe for tr in s.required_timeframes],
                    source_compatibility_policy=s.source_compatibility_policy.value,
                    description=s.description,
                ).model_dump()
                for s in strategies
            ],
        }

    async def get_strategies(self) -> list[dict]:
        """Return list of strategy definitions."""
        strategies = get_all_strategy_definitions()
        return [
            {
                "strategy_id": s.strategy_id,
                "strategy_version": s.strategy_version,
                "strategy_name": s.strategy_name,
                "description": s.description,
                "enabled": s.enabled,
                "applicable_market_regimes": s.applicable_market_regimes,
                "required_timeframes": [
                    {"timeframe": tr.timeframe, "role": tr.role.value}
                    for tr in s.required_timeframes
                ],
                "source_compatibility_policy": s.source_compatibility_policy.value,
                "scoring_model_version": s.scoring_model_version,
            }
            for s in strategies
        ]
