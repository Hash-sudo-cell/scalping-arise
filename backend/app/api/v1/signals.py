"""
Scalping Arise — Signal Engine API Endpoints

Minimal API surface for Phase 6 signal evaluation.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.core.errors import ValidationError
from app.modules.signal_engine.config import get_signal_engine_settings
from app.modules.signal_engine.service import SignalEngineService
from app.modules.market_data.service import MarketDataService
from app.modules.market_analysis.service import MarketAnalysisService
from app.modules.technical_features.service import TechnicalFeatureService
from app.modules.strategies.service import StrategyEvaluationService

router = APIRouter(tags=["signals"])

# Module-level service instances (created lazily on first request)
_signal_service: Optional[SignalEngineService] = None
_market_data_service: Optional[MarketDataService] = None
_analysis_service: Optional[MarketAnalysisService] = None
_feature_service: Optional[TechnicalFeatureService] = None
_strategy_service: Optional[StrategyEvaluationService] = None


def _get_signal_service() -> SignalEngineService:
    """Get or create the signal engine service singleton."""
    global _signal_service, _market_data_service, _analysis_service, _feature_service, _strategy_service
    if _signal_service is None:
        _market_data_service = MarketDataService()
        _analysis_service = MarketAnalysisService(market_data_service=_market_data_service)
        _feature_service = TechnicalFeatureService(market_data_service=_market_data_service)
        _strategy_service = StrategyEvaluationService(
            market_data_service=_market_data_service,
            analysis_service=_analysis_service,
            feature_service=_feature_service,
        )
        _signal_service = SignalEngineService(
            market_data_service=_market_data_service,
            analysis_service=_analysis_service,
            feature_service=_feature_service,
            strategy_service=_strategy_service,
        )
    return _signal_service


# ---------------------------------------------------------------------------
# GET /api/v1/signals/health
# ---------------------------------------------------------------------------

@router.get("/signals/health")
async def signals_health() -> dict:
    """
    Signal engine subsystem health check.

    Reports whether the signal engine is operational and its configuration.
    """
    service = _get_signal_service()
    return await service.health_check()


# ---------------------------------------------------------------------------
# GET /api/v1/signals/capabilities
# ---------------------------------------------------------------------------

@router.get("/signals/capabilities")
async def signals_capabilities() -> dict:
    """
    Expose current signal engine capabilities.

    Reports available features, thresholds, and configuration.
    """
    service = _get_signal_service()
    return await service.get_capabilities()


# ---------------------------------------------------------------------------
# GET /api/v1/signals/evaluate
# ---------------------------------------------------------------------------

@router.get("/signals/evaluate")
async def signals_evaluate(
    instrument: str = Query(
        default="XAU/USD",
        description="Canonical instrument name",
    ),
    timeframes: str = Query(
        default="1m,5m,15m",
        description="Comma-separated timeframes for evaluation",
    ),
    limit: int = Query(
        default=300,
        ge=50,
        le=5000,
        description="Number of candles per timeframe (50-5000)",
    ),
    strategy_ids: Optional[str] = Query(
        default=None,
        description="Comma-separated strategy IDs to evaluate (default: all enabled)",
    ),
) -> dict:
    """
    Run a complete signal evaluation.

    Consumes Phase 3 (Market Analysis), Phase 4 (Technical Features),
    and Phase 5 (Strategy Evaluation) to produce a structured signal
    evaluation result with confidence scoring and conflict resolution.
    """
    from app.modules.market_data.models import Instrument

    # Validate instrument
    try:
        inst = Instrument(instrument)
    except ValueError:
        raise ValidationError(
            message=f"Unsupported instrument: {instrument}",
            details={"allowed": [i.value for i in Instrument]},
        )

    # Parse timeframes
    tf_list = [tf.strip() for tf in timeframes.split(",") if tf.strip()]
    if not tf_list:
        raise ValidationError(
            message="No timeframes provided",
            details={"example": "1m,5m,15m"},
        )

    # Parse optional strategy IDs
    sid_list = None
    if strategy_ids:
        sid_list = [s.strip() for s in strategy_ids.split(",") if s.strip()]

    service = _get_signal_service()
    result = await service.evaluate_signal(
        instrument=inst.value,
        timeframes=tf_list,
        candle_limit=limit,
        strategy_ids=sid_list,
    )

    return _serialize_signal_result(result)


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _serialize_signal_result(result) -> dict:
    """Serialize a SignalEvaluationResult to a JSON-compatible dict."""
    response = {
        "evaluation_id": result.evaluation_id,
        "evaluation_timestamp": result.evaluation_timestamp.isoformat(),
        "instrument": result.instrument,
        "status": result.status.value,
        "direction": result.direction.value,
        "reason": result.reason,
    }

    if result.confidence:
        response["confidence"] = {
            "overall": result.confidence.overall,
            "strategy_alignment": result.confidence.strategy_alignment,
            "mtf_confirmation": result.confidence.mtf_confirmation,
            "evidence_strength": result.confidence.evidence_strength,
            "regime_consistency": result.confidence.regime_consistency,
            "breakdown": [
                {
                    "factor": b.factor,
                    "score": b.score,
                    "weight": b.weight,
                    "contribution": b.contribution,
                    "description": b.description,
                }
                for b in result.confidence.breakdown
            ],
        }

    if result.candidates:
        response["candidates"] = [
            {
                "strategy_id": c.strategy_id,
                "strategy_version": c.strategy_version,
                "strategy_name": c.strategy_name,
                "direction": c.direction.value,
                "quality_score_normalized": c.quality_score_normalized,
                "quality_score_raw": c.quality_score_raw,
                "quality_score_max": c.quality_score_max,
                "condition_pass_rate": c.condition_pass_rate,
                "invalidation_triggered": c.invalidation_triggered,
                "market_regime": c.market_regime,
            }
            for c in result.candidates
        ]

    if result.mtf_confirmation:
        response["mtf_confirmation"] = {
            "confirmed": result.mtf_confirmation.confirmed,
            "confirmation_level": result.mtf_confirmation.confirmation_level.value,
            "aligned_count": result.mtf_confirmation.aligned_count,
            "total_count": result.mtf_confirmation.total_count,
            "confirmations": [
                {
                    "timeframe": c.timeframe,
                    "aligned": c.aligned,
                    "confirmation_level": c.confirmation_level.value,
                    "ema_alignment": c.ema_alignment,
                    "trend_state": c.trend_state,
                }
                for c in result.mtf_confirmation.confirmations
            ],
        }

    if result.conflicts:
        response["conflicts"] = [
            {
                "conflict_type": c.conflict_type.value,
                "description": c.description,
                "involved_strategies": c.involved_strategies,
                "severity": c.severity,
            }
            for c in result.conflicts
        ]

    if result.resolution:
        response["resolution"] = {
            "final_direction": result.resolution.final_direction.value,
            "confidence": result.resolution.confidence,
            "resolution_method": result.resolution.resolution_method,
            "dropped_candidates": result.resolution.dropped_candidates,
        }

    if result.source_types_used:
        response["source_types_used"] = result.source_types_used

    if result.timeframes_evaluated:
        response["timeframes_evaluated"] = result.timeframes_evaluated

    return response
