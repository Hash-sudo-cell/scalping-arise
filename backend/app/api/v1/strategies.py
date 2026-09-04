"""
Scalping Arise — Strategy Engine API Endpoints

Minimal API surface for Phase 5 strategy evaluation.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.core.errors import NotFoundError, ValidationError
from app.modules.strategies.config import get_strategy_engine_settings
from app.modules.strategies.service import StrategyEvaluationService
from app.modules.market_data.service import MarketDataService
from app.modules.market_analysis.service import MarketAnalysisService
from app.modules.technical_features.service import TechnicalFeatureService

router = APIRouter(tags=["strategies"])

# Module-level service instances (created lazily on first request)
_strategy_service: Optional[StrategyEvaluationService] = None
_market_data_service: Optional[MarketDataService] = None
_analysis_service: Optional[MarketAnalysisService] = None
_feature_service: Optional[TechnicalFeatureService] = None


def _get_strategy_service() -> StrategyEvaluationService:
    """Get or create the strategy evaluation service singleton."""
    global _strategy_service, _market_data_service, _analysis_service, _feature_service
    if _strategy_service is None:
        _market_data_service = MarketDataService()
        _analysis_service = MarketAnalysisService(market_data_service=_market_data_service)
        _feature_service = TechnicalFeatureService(market_data_service=_market_data_service)
        _strategy_service = StrategyEvaluationService(
            market_data_service=_market_data_service,
            analysis_service=_analysis_service,
            feature_service=_feature_service,
        )
    return _strategy_service


# ---------------------------------------------------------------------------
# GET /api/v1/strategies/health
# ---------------------------------------------------------------------------

@router.get("/strategies/health")
async def strategies_health() -> dict:
    """
    Strategy engine subsystem health check.

    Reports whether the strategy engine is operational, its configuration,
    and registered strategies.
    """
    service = _get_strategy_service()
    return await service.health_check()


# ---------------------------------------------------------------------------
# GET /api/v1/strategies/capabilities
# ---------------------------------------------------------------------------

@router.get("/strategies/capabilities")
async def strategies_capabilities() -> dict:
    """
    Expose current strategy engine capabilities.

    Reports available strategies, versions, regimes, and source policies.
    """
    service = _get_strategy_service()
    return await service.get_capabilities()


# ---------------------------------------------------------------------------
# GET /api/v1/strategies
# ---------------------------------------------------------------------------

@router.get("/strategies")
async def strategies_list() -> dict:
    """
    List all registered strategy definitions.

    Returns strategy metadata including version, regimes, and timeframes.
    """
    service = _get_strategy_service()
    strategies = await service.get_strategies()
    return {
        "strategies": strategies,
        "count": len(strategies),
    }


# ---------------------------------------------------------------------------
# GET /api/v1/strategies/evaluate
# ---------------------------------------------------------------------------

@router.get("/strategies/evaluate")
async def strategies_evaluate(
    strategy_id: str = Query(
        description="Strategy ID to evaluate (e.g. trend_continuation)",
    ),
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
) -> dict:
    """
    Evaluate a single strategy against current market data.

    Returns a structured evaluation result with eligibility, conditions,
    invalidation, quality score, and final status.
    """
    # Validate instrument
    from app.modules.market_data.models import Instrument
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

    service = _get_strategy_service()
    result = await service.evaluate_strategy(
        strategy_id=strategy_id,
        instrument=inst.value,
        timeframes=tf_list,
        candle_limit=limit,
    )

    return _serialize_evaluation_result(result)


# ---------------------------------------------------------------------------
# GET /api/v1/strategies/evaluate-all
# ---------------------------------------------------------------------------

@router.get("/strategies/evaluate-all")
async def strategies_evaluate_all(
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
) -> dict:
    """
    Evaluate all enabled strategies against current market data.

    Returns a list of structured evaluation results.
    """
    from app.modules.market_data.models import Instrument
    try:
        inst = Instrument(instrument)
    except ValueError:
        raise ValidationError(
            message=f"Unsupported instrument: {instrument}",
            details={"allowed": [i.value for i in Instrument]},
        )

    tf_list = [tf.strip() for tf in timeframes.split(",") if tf.strip()]
    if not tf_list:
        raise ValidationError(
            message="No timeframes provided",
            details={"example": "1m,5m,15m"},
        )

    service = _get_strategy_service()
    results = await service.evaluate_all_strategies(
        instrument=inst.value,
        timeframes=tf_list,
        candle_limit=limit,
    )

    return {
        "evaluations": [_serialize_evaluation_result(r) for r in results],
        "count": len(results),
    }


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_evaluation_result(result) -> dict:
    """Serialize a StrategyEvaluationResult to a JSON-compatible dict."""
    response = {
        "evaluation_id": result.evaluation_id,
        "evaluation_timestamp": result.evaluation_timestamp.isoformat(),
        "strategy_id": result.strategy_id,
        "strategy_version": result.strategy_version,
        "strategy_name": result.strategy_name,
        "instrument": result.instrument,
        "status": result.status.value,
        "direction": result.direction.value,
        "reason": result.reason,
    }

    if result.timeframe_contexts:
        response["timeframe_contexts"] = [tc.model_dump() for tc in result.timeframe_contexts]

    if result.source_types_used:
        response["source_types_used"] = result.source_types_used

    if result.market_regime:
        response["market_regime"] = result.market_regime

    if result.market_structure_summary:
        response["market_structure_summary"] = result.market_structure_summary

    if result.eligibility:
        response["eligibility"] = {
            "eligible": result.eligibility.eligible,
            "blocked_by": result.eligibility.blocked_by,
            "checks": [c.model_dump() for c in result.eligibility.checks],
        }

    if result.condition_results:
        response["condition_results"] = [cr.model_dump() for cr in result.condition_results]

    if result.invalidation_results:
        response["invalidation_results"] = [ir.model_dump() for ir in result.invalidation_results]

    if result.quality_score:
        response["quality_score"] = result.quality_score.model_dump()

    # Liquidity context
    response["liquidity_context_used"] = result.liquidity_context_used
    if result.liquidity_summary:
        response["liquidity_summary"] = result.liquidity_summary.model_dump()

    return response
