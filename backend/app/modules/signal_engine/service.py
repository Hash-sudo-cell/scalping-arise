"""
Scalping Arise — Signal Engine Service

Central orchestration layer for signal evaluation.
Consumes outputs from Phase 3 (Market Analysis), Phase 4 (Technical Features),
and Phase 5 (Strategy Evaluation) to determine whether market context produces
a sufficiently qualified directional signal candidate.

Flow:
    Phase 3 Market Analysis ─────┐
                                  │
    Phase 4 Technical Features ──┤
                                  │
    Phase 5 Strategy Evaluation ─┤
                                  ├──→ Signal Engine Service
                                  │
    Signal Config ───────────────┘
                                      ↓
                              Candidate Generation
                                      ↓
                              MTF Confirmation
                                      ↓
                              Conflict Detection
                                      ↓
                              Conflict Resolution
                                      ↓
                              Evidence Aggregation
                                      ↓
                              Confidence Scoring
                                      ↓
                              Signal Qualification
                                      ↓
                              Signal Evaluation Result
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_analysis.models import AnalysisResult, AnalysisStatus
from app.modules.market_analysis.service import MarketAnalysisService
from app.modules.market_data.models import Instrument, Timeframe
from app.modules.market_data.service import MarketDataService
from app.modules.signal_engine.candidate_generation import generate_candidates
from app.modules.signal_engine.confidence import calculate_confidence
from app.modules.signal_engine.conflict_resolver import resolve_conflicts
from app.modules.signal_engine.conflicts import detect_all_conflicts
from app.modules.signal_engine.config import SignalEngineSettings, get_signal_engine_settings
from app.modules.signal_engine.evidence import aggregate_evidence
from app.modules.signal_engine.models import (
    ConfidenceScore,
    EvidenceItem,
    SignalCandidate,
    SignalDirection,
    SignalEvaluationResult,
    SignalStatus,
)
from app.modules.signal_engine.multi_timeframe import evaluate_mtf_confirmation
from app.modules.signal_engine.qualification import qualify_signal
from app.modules.strategies.config import get_strategy_engine_settings
from app.modules.strategies.models import (
    StrategyEvaluationResult,
    StrategyEvaluationStatus,
)
from app.modules.strategies.service import StrategyEvaluationService
from app.modules.technical_features.models import FeatureResult, FeatureSetStatus
from app.modules.technical_features.service import TechnicalFeatureService

logger = logging.getLogger(__name__)


class SignalEngineService:
    """
    Central signal evaluation orchestration service.

    Consumes all upstream pipeline outputs and produces a structured
    signal evaluation result with confidence scoring and conflict resolution.
    """

    def __init__(
        self,
        market_data_service: Optional[MarketDataService] = None,
        analysis_service: Optional[MarketAnalysisService] = None,
        feature_service: Optional[TechnicalFeatureService] = None,
        strategy_service: Optional[StrategyEvaluationService] = None,
        settings: Optional[SignalEngineSettings] = None,
    ) -> None:
        self._market_data = market_data_service or MarketDataService()
        self._analysis_service = analysis_service or MarketAnalysisService(
            market_data_service=self._market_data,
        )
        self._feature_service = feature_service or TechnicalFeatureService(
            market_data_service=self._market_data,
        )
        self._strategy_service = strategy_service or StrategyEvaluationService(
            market_data_service=self._market_data,
            analysis_service=self._analysis_service,
            feature_service=self._feature_service,
        )
        self._settings = settings or get_signal_engine_settings()

    async def evaluate_signal(
        self,
        instrument: str = "XAU/USD",
        timeframes: Optional[list[str]] = None,
        candle_limit: int = 300,
        strategy_ids: Optional[list[str]] = None,
    ) -> SignalEvaluationResult:
        """
        Run a complete signal evaluation.

        1. Collect Phase 3 analysis, Phase 4 features, Phase 5 strategy evaluations
        2. Generate candidates from qualified strategies
        3. Check multi-timeframe confirmation
        4. Detect and resolve conflicts
        5. Aggregate evidence
        6. Score confidence
        7. Qualify the final signal
        """
        from app.modules.signal_engine.validation import (
            validate_candle_limit,
            validate_instrument,
            validate_timeframes,
        )

        # Validate inputs
        inst = validate_instrument(instrument)
        if timeframes is None:
            timeframes = self._settings.default_evaluation_timeframes
        else:
            validate_timeframes(timeframes)
        validate_candle_limit(candle_limit)

        # --- Phase 3: Market Analysis (primary timeframe) ---
        primary_tf = timeframes[0] if timeframes else "1h"
        analysis_result: Optional[AnalysisResult] = None
        try:
            analysis_result = await self._analysis_service.analyze(
                instrument=inst,
                timeframe=Timeframe(primary_tf),
                limit=candle_limit,
            )
        except Exception as e:
            logger.error("Market analysis failed: %s", e)

        # --- Phase 4: Multi-Timeframe Features ---
        feature_results: dict[str, FeatureResult] = {}
        for tf in timeframes:
            try:
                feat = await self._feature_service.get_features(
                    timeframe=tf,
                    limit=candle_limit,
                )
                feature_results[tf] = feat
            except Exception as e:
                logger.error("Feature calculation failed for %s: %s", tf, e)
                feature_results[tf] = FeatureResult(
                    status=FeatureSetStatus.UNAVAILABLE,
                    reason=f"Calculation failed: {e}",
                )

        # --- Phase 5: Strategy Evaluations ---
        strategy_settings = get_strategy_engine_settings()
        strategy_evals: list[StrategyEvaluationResult] = []

        if strategy_ids:
            # Evaluate specific strategies
            for sid in strategy_ids:
                try:
                    result = await self._strategy_service.evaluate_strategy(
                        strategy_id=sid,
                        instrument=inst.value,
                        timeframes=timeframes,
                        candle_limit=candle_limit,
                    )
                    strategy_evals.append(result)
                except Exception as e:
                    logger.error("Strategy %s evaluation failed: %s", sid, e)
        else:
            # Evaluate all enabled strategies
            try:
                strategy_evals = await self._strategy_service.evaluate_all_strategies(
                    instrument=inst.value,
                    timeframes=timeframes,
                    candle_limit=candle_limit,
                )
            except Exception as e:
                logger.error("Strategy evaluation failed: %s", e)

        # --- Signal Engine Pipeline ---

        # 1. Generate candidates from qualified strategies
        candidates, candidate_evidence = generate_candidates(strategy_evals)

        # If no candidates, return early
        if not candidates:
            return SignalEvaluationResult(
                instrument=inst.value,
                status=SignalStatus.INSUFFICIENT_CONTEXT,
                direction=SignalDirection.NONE,
                candidates=[],
                reason="No qualified strategy candidates produced a directional signal",
                source_types_used=list({
                    ctx.source_type
                    for ev in strategy_evals
                    for ctx in ev.timeframe_contexts
                }),
                timeframes_evaluated=timeframes,
            )

        # 2. Determine dominant direction (majority by quality weight)
        direction_weights: dict[SignalDirection, float] = {}
        for c in candidates:
            direction_weights[c.direction] = (
                direction_weights.get(c.direction, 0) + c.quality_score_normalized
            )
        dominant_direction = max(direction_weights, key=direction_weights.get)  # type: ignore[arg-type]

        # 3. Multi-timeframe confirmation
        # Build per-timeframe analyses (re-use the primary analysis for all TFs for now)
        tf_analyses: dict[str, Optional[AnalysisResult]] = {
            tf: analysis_result for tf in timeframes
        }

        mtf_result, mtf_evidence = evaluate_mtf_confirmation(
            candidate=candidates[0] if candidates else SignalCandidate(
                strategy_id="unknown",
                strategy_version="unknown",
                strategy_name="Unknown",
                direction=dominant_direction,
                quality_score_normalized=0.0,
                quality_score_raw=0,
                quality_score_max=0,
                condition_pass_rate=0.0,
            ),
            timeframe_features=feature_results,
            timeframe_analyses=tf_analyses,
            min_aligned=self._settings.mtf_min_aligned_timeframes,
        )

        # 4. Detect conflicts
        conflicts = detect_all_conflicts(candidates, mtf_result, dominant_direction)

        # 5. Resolve conflicts
        resolution = None
        if conflicts and self._settings.enable_conflict_resolution:
            resolution = resolve_conflicts(candidates, conflicts)
            final_direction = resolution.final_direction
        else:
            final_direction = dominant_direction

        # 6. Aggregate evidence
        all_evidence = aggregate_evidence(
            candidates=candidates,
            candidate_evidence=candidate_evidence,
            mtf_evidence=mtf_evidence,
            analysis=analysis_result,
            direction=final_direction,
        )

        # 7. Score confidence
        confidence = calculate_confidence(
            candidates=candidates,
            direction=final_direction,
            mtf_result=mtf_result,
            evidence=all_evidence,
            analysis=analysis_result,
        )

        # 8. Qualify the signal
        status, reason = qualify_signal(
            candidates=candidates,
            direction=final_direction,
            confidence=confidence,
            mtf_result=mtf_result,
            conflicts=conflicts,
            resolution=resolution,
            settings=self._settings,
        )

        # Source types
        source_types = list({
            ctx.source_type
            for ev in strategy_evals
            for ctx in ev.timeframe_contexts
        })

        result = SignalEvaluationResult(
            instrument=inst.value,
            status=status,
            direction=final_direction,
            confidence=confidence,
            candidates=candidates,
            mtf_confirmation=mtf_result,
            conflicts=conflicts,
            resolution=resolution,
            evidence=all_evidence,
            reason=reason,
            source_types_used=source_types,
            timeframes_evaluated=timeframes,
        )

        logger.info(
            "Signal evaluation: status=%s direction=%s confidence=%.2f candidates=%d",
            status.value,
            final_direction.value,
            confidence.overall,
            len(candidates),
        )
        return result

    async def health_check(self) -> dict:
        """Check if the signal engine is operational."""
        try:
            settings = self._settings
            strategy_settings = get_strategy_engine_settings()
            return {
                "status": "healthy",
                "module": "signal_engine",
                "configuration": {
                    "enabled": settings.is_enabled,
                    "minimum_confidence_threshold": settings.minimum_confidence_threshold,
                    "strong_confidence_threshold": settings.strong_confidence_threshold,
                    "require_mtf_confirmation": settings.require_mtf_confirmation,
                    "enable_conflict_resolution": settings.enable_conflict_resolution,
                    "default_timeframes": settings.default_evaluation_timeframes,
                },
                "strategies_available": len(strategy_settings.enabled_strategies),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "module": "signal_engine",
                "error": str(e),
            }

    async def get_capabilities(self) -> dict:
        """Return signal engine capabilities."""
        settings = self._settings
        return {
            "module": "signal_engine",
            "status": "active" if settings.is_enabled else "disabled",
            "features": {
                "candidate_generation": True,
                "mtf_confirmation": settings.require_mtf_confirmation,
                "conflict_detection": True,
                "conflict_resolution": settings.enable_conflict_resolution,
                "confidence_scoring": True,
                "signal_qualification": True,
            },
            "thresholds": {
                "minimum_confidence": settings.minimum_confidence_threshold,
                "strong_confidence": settings.strong_confidence_threshold,
                "mtf_min_aligned": settings.mtf_min_aligned_timeframes,
            },
        }
