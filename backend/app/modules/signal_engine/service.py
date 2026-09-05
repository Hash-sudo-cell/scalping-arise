"""
Scalping Arise — Signal Engine Service

Central orchestration layer for signal evaluation.
Consumes outputs from Phase 3 (Market Analysis), Phase 4 (Technical Features),
and Phase 5 (Strategy Evaluation) to determine whether market context produces
a sufficiently qualified directional signal candidate.

Phase 6 additions:
- Full signal lifecycle state machine (NO_SIGNAL → CANDIDATE → QUALIFIED → CONFIRMED → ACTIVE)
- Deduplication (prevents duplicate signals within configurable window)
- Expiration (TTL-based auto-expiration of active signals)
- Invalidation pipeline (market condition changes invalidate active signals)
- Quality scoring (independent 0–100 quality measure)
- Priority ranking (composite score for active signal ordering)
- Structured decisions (BUY/SELL/NO_TRADE with typed reason codes)
- Signal history (bounded ring buffer of past evaluations)

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
                              Deduplication Check
                                      ↓
                              Expiration Check
                                      ↓
                              Invalidation Check
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
                              Quality Scoring
                                      ↓
                              Signal Qualification
                                      ↓
                              State Machine Transition
                                      ↓
                              Priority Ranking
                                      ↓
                              Signal Evaluation Result
"""

from __future__ import annotations

import logging
from collections import deque
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
from app.modules.signal_engine.deduplication import SignalDeduplicator
from app.modules.signal_engine.evidence import aggregate_evidence
from app.modules.signal_engine.expiration import SignalExpirationManager
from app.modules.signal_engine.models import (
    ConfidenceScore,
    DecisionReason,
    DecisionReasonCode,
    DecisionType,
    EvidenceItem,
    SignalCandidate,
    SignalDirection,
    SignalEvaluationResult,
    SignalRecord,
    SignalQuality,
    SignalState,
    SignalStatus,
    direction_to_decision,
    status_to_state,
)
from app.modules.signal_engine.multi_timeframe import evaluate_mtf_confirmation
from app.modules.signal_engine.qualification import compute_signal_quality, qualify_signal
from app.modules.signal_engine.ranking import rank_signals, calculate_priority
from app.modules.signal_engine.signal_invalidation import SignalInvalidator
from app.modules.signal_engine.state_machine import SignalStateMachine
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
    signal evaluation result with confidence scoring, quality scoring,
    conflict resolution, deduplication, expiration, invalidation,
    and priority ranking.
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

        # Phase 6 components
        self._state_machine = SignalStateMachine()
        self._deduplicator = SignalDeduplicator(
            window_seconds=self._settings.dedup_window_seconds,
        )
        self._expiration_manager = SignalExpirationManager(
            state_machine=self._state_machine,
            default_ttl_seconds=self._settings.signal_ttl_seconds,
        )
        self._invalidator = SignalInvalidator(
            state_machine=self._state_machine,
        )

        # Signal history (bounded ring buffer)
        self._history: deque[SignalRecord] = deque(
            maxlen=self._settings.signal_history_max_size,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate_signal(
        self,
        instrument: str = "XAU/USD",
        timeframes: Optional[list[str]] = None,
        candle_limit: int = 300,
        strategy_ids: Optional[list[str]] = None,
    ) -> SignalEvaluationResult:
        """
        Run a complete signal evaluation.

        Phase 6 pipeline:
        1. Run lifecycle checks (dedup, expiration, invalidation)
        2. Collect Phase 3 analysis, Phase 4 features, Phase 5 strategy evaluations
        3. Generate candidates from qualified strategies
        4. Check multi-timeframe confirmation
        5. Detect and resolve conflicts
        6. Aggregate evidence
        7. Score confidence
        8. Score quality
        9. Qualify the final signal
        10. Transition state machine
        11. Check dedup and emit
        12. Rank priority
        13. Build result
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

        # --- Lifecycle: expire stale signals ---
        self._expiration_manager.check_all()

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
        strategy_evals: list[StrategyEvaluationResult] = []

        if strategy_ids:
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
            try:
                strategy_evals = await self._strategy_service.evaluate_all_strategies(
                    instrument=inst.value,
                    timeframes=timeframes,
                    candle_limit=candle_limit,
                )
            except Exception as e:
                logger.error("Strategy evaluation failed: %s", e)

        # --- Lifecycle: invalidation check ---
        aligned_count = self._count_aligned_tfs(feature_results)
        self._invalidator.check_all(
            current_analysis=analysis_result,
            current_aligned_count=aligned_count,
            min_aligned=self._settings.mtf_min_aligned_timeframes,
        )

        # --- Signal Engine Pipeline ---

        # 1. Generate candidates from qualified strategies
        candidates, candidate_evidence = generate_candidates(strategy_evals)

        # If no candidates, return early
        if not candidates:
            result = self._build_no_signal_result(
                inst.value, strategy_evals, timeframes,
            )
            return result

        # 2. Determine dominant direction
        direction_weights: dict[SignalDirection, float] = {}
        for c in candidates:
            direction_weights[c.direction] = (
                direction_weights.get(c.direction, 0) + c.quality_score_normalized
            )
        dominant_direction = max(direction_weights, key=direction_weights.get)  # type: ignore[arg-type]

        # 3. Multi-timeframe confirmation
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

        # 8. Score quality (Phase 6 — independent)
        quality = compute_signal_quality(
            candidates=candidates,
            direction=final_direction,
            evidence_count=len(all_evidence),
            confidence=confidence,
        )

        # 9. Qualify the signal
        status, reason, decision_reasons = qualify_signal(
            candidates=candidates,
            direction=final_direction,
            confidence=confidence,
            mtf_result=mtf_result,
            conflicts=conflicts,
            resolution=resolution,
            settings=self._settings,
        )

        # 10. Build signal record and transition state machine
        decision = direction_to_decision(final_direction)
        record = SignalRecord(
            instrument=inst.value,
            decision=decision,
            state=SignalState.CANDIDATE,
            direction=final_direction,
            confidence=confidence,
            quality=quality,
            reasons=decision_reasons,
            candidates=candidates,
            mtf_confirmation=mtf_result,
            conflicts=conflicts,
            resolution=resolution,
            evidence=all_evidence,
            ttl_seconds=self._settings.signal_ttl_seconds,
            source_types_used=list({
                ctx.source_type
                for ev in strategy_evals
                for ctx in ev.timeframe_contexts
            }),
            timeframes_evaluated=timeframes,
            reason=reason,
        )
        self._state_machine.register(record)

        # Transition through state machine based on qualification
        if status == SignalStatus.QUALIFIED:
            self._state_machine.transition(record, SignalState.QUALIFIED, reason)
            self._state_machine.transition(record, SignalState.CONFIRMED, "MTF + confidence validated")
        elif status == SignalStatus.REJECTED:
            self._state_machine.transition(record, SignalState.NO_SIGNAL, reason)
        elif status == SignalStatus.CONFLICT:
            # Keep as CANDIDATE — may resolve on next evaluation
            pass
        elif status == SignalStatus.INSUFFICIENT_CONTEXT:
            self._state_machine.transition(record, SignalState.NO_SIGNAL, reason)

        # 11. Dedup check
        if record.state in (SignalState.QUALIFIED, SignalState.CONFIRMED):
            strategy_ids_list = [c.strategy_id for c in candidates]
            if self._deduplicator.is_duplicate(
                inst.value, final_direction, decision, strategy_ids_list,
            ):
                record.reasons.append(
                    DecisionReason(
                        code=DecisionReasonCode.DEDUPLICATE_BLOCKED,
                        detail="Signal blocked by deduplication window",
                    )
                )
                self._state_machine.transition(record, SignalState.NO_SIGNAL, "Dedup blocked")
                status = SignalStatus.REJECTED
                reason = "Signal blocked: duplicate within deduplication window"
            else:
                # Activate the signal
                if self._state_machine.can_activate(self._settings.max_active_signals):
                    self._state_machine.transition(record, SignalState.ACTIVE, "Activated")
                    self._deduplicator.register(record)
                else:
                    self._state_machine.transition(record, SignalState.NO_SIGNAL, "Max active signals reached")
                    status = SignalStatus.REJECTED
                    reason = f"Max active signals ({self._settings.max_active_signals}) reached"

        # 12. Compute priority if active
        if record.state == SignalState.ACTIVE:
            record.priority = calculate_priority(record, self._settings)

        # 13. Add to history
        self._history.append(record)

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
            decision=decision,
            decision_reasons=decision_reasons,
            signal_record=record,
            confidence=confidence,
            quality=quality,
            priority=record.priority,
            signal_state=record.state,
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
            "Signal evaluation: status=%s decision=%s state=%s confidence=%.2f quality=%d candidates=%d",
            status.value,
            decision.value,
            record.state.value,
            confidence.overall,
            quality.score,
            len(candidates),
        )
        return result

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_active_signals(self) -> list[SignalRecord]:
        """Get all currently active signals, ranked by priority."""
        ranked = rank_signals(self._state_machine.get_active(), self._settings)
        return ranked

    def get_signal_history(self, limit: int = 20) -> list[SignalRecord]:
        """Get recent signal history (most recent first)."""
        return list(reversed(list(self._history)[-limit:]))

    def get_signal_by_id(self, signal_id: str) -> Optional[SignalRecord]:
        """Get a specific signal record by ID."""
        return self._state_machine.get(signal_id)

    def invalidate_signal(self, signal_id: str, reason: str = "Manual invalidation") -> bool:
        """Manually invalidate a signal by ID."""
        record = self._state_machine.get(signal_id)
        if record is None:
            return False
        self._deduplicator.unregister(signal_id)
        return self._state_machine.invalidate(record, reason)

    # ------------------------------------------------------------------
    # Health & Capabilities
    # ------------------------------------------------------------------

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
                    "signal_ttl_seconds": settings.signal_ttl_seconds,
                    "dedup_window_seconds": settings.dedup_window_seconds,
                    "max_active_signals": settings.max_active_signals,
                },
                "strategies_available": len(strategy_settings.enabled_strategies),
                "active_signals": self._state_machine.count_active(),
                "history_size": len(self._history),
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
                # Phase 6 features
                "state_machine": True,
                "deduplication": True,
                "expiration": True,
                "invalidation": True,
                "quality_scoring": True,
                "priority_ranking": True,
                "structured_decisions": True,
                "signal_history": True,
            },
            "thresholds": {
                "minimum_confidence": settings.minimum_confidence_threshold,
                "strong_confidence": settings.strong_confidence_threshold,
                "confidence_threshold_0_100": settings.confidence_threshold_0_100,
                "quality_threshold_0_100": settings.quality_threshold_0_100,
                "mtf_min_aligned": settings.mtf_min_aligned_timeframes,
            },
            "lifecycle": {
                "signal_ttl_seconds": settings.signal_ttl_seconds,
                "dedup_window_seconds": settings.dedup_window_seconds,
                "max_active_signals": settings.max_active_signals,
                "signal_history_max_size": settings.signal_history_max_size,
            },
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_no_signal_result(
        self,
        instrument: str,
        strategy_evals: list[StrategyEvaluationResult],
        timeframes: list[str],
    ) -> SignalEvaluationResult:
        """Build a result for when no candidates are produced."""
        source_types = list({
            ctx.source_type
            for ev in strategy_evals
            for ctx in ev.timeframe_contexts
        })
        from app.modules.signal_engine.models import DecisionReason, DecisionReasonCode
        return SignalEvaluationResult(
            instrument=instrument,
            status=SignalStatus.INSUFFICIENT_CONTEXT,
            direction=SignalDirection.NONE,
            decision=DecisionType.NO_TRADE,
            decision_reasons=[DecisionReason(
                code=DecisionReasonCode.NO_CANDIDATES,
                detail="No qualified strategy candidates produced a directional signal",
            )],
            signal_state=SignalState.NO_SIGNAL,
            candidates=[],
            reason="No qualified strategy candidates produced a directional signal",
            source_types_used=source_types,
            timeframes_evaluated=timeframes,
        )

    def _count_aligned_tfs(self, feature_results: dict[str, FeatureResult]) -> int:
        """Count how many timeframes have READY feature sets."""
        return sum(
            1 for f in feature_results.values()
            if f.feature_set_status == FeatureSetStatus.READY
        )
