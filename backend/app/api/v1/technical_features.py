"""
Scalping Arise — Technical Features API Endpoints

Minimal API surface for Phase 4 verification.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.modules.market_data.models import Instrument, Timeframe
from app.modules.market_data.service import MarketDataService
from app.modules.technical_features.config import get_technical_features_settings
from app.modules.technical_features.service import TechnicalFeatureService

router = APIRouter(tags=["technical-features"])

# Module-level service instances (created lazily on first request)
_feature_service: Optional[TechnicalFeatureService] = None
_market_data_service: Optional[MarketDataService] = None


def _get_feature_service() -> TechnicalFeatureService:
    """Get or create the technical feature service singleton."""
    global _feature_service, _market_data_service
    if _feature_service is None:
        _market_data_service = MarketDataService()
        _feature_service = TechnicalFeatureService(
            market_data_service=_market_data_service,
        )
    return _feature_service


# ---------------------------------------------------------------------------
# GET /api/v1/technical-features/health
# ---------------------------------------------------------------------------

@router.get("/technical-features/health")
async def technical_features_health() -> dict:
    """
    Technical features subsystem health check.

    Reports whether the feature engine is operational, its configuration,
    and indicator parameters.
    """
    service = _get_feature_service()
    return await service.health_check()


# ---------------------------------------------------------------------------
# GET /api/v1/technical-features/capabilities
# ---------------------------------------------------------------------------

@router.get("/technical-features/capabilities")
async def technical_features_capabilities() -> dict:
    """
    Expose current technical feature capabilities.

    Reports supported features, indicator parameters, and minimum
    data requirements.
    """
    service = _get_feature_service()
    return await service.get_capabilities()


# ---------------------------------------------------------------------------
# GET /api/v1/technical-features
# ---------------------------------------------------------------------------

@router.get("/technical-features")
async def technical_features(
    timeframe: str = Query(
        default="1h",
        description="Candle timeframe (e.g. 1m, 5m, 15m, 1h, 4h, 1d)",
    ),
    limit: int = Query(
        default=300,
        ge=50,
        le=5000,
        description="Number of candles to fetch for feature calculation (50-5000)",
    ),
) -> dict:
    """
    Calculate all technical features for the given timeframe.

    Returns comprehensive feature data including trend (EMA), momentum
    (RSI, MACD), volatility (ATR, Bollinger), volume, and price context.
    """
    service = _get_feature_service()
    result = await service.get_features(timeframe=timeframe, limit=limit)

    # Build response
    response = {
        "status": result.status.value,
        "reason": result.reason,
        "feature_set_status": result.feature_set_status.value,
        "feature_set_reason": result.feature_set_reason,
        "feature_timestamp": result.feature_timestamp.isoformat(),
    }

    if result.volatility_classification:
        response["volatility_classification"] = result.volatility_classification.value
    response["volatility_classification_reason"] = result.volatility_classification_reason

    if result.metadata:
        response["metadata"] = result.metadata.model_dump(mode="json")

    if result.trend:
        response["trend"] = result.trend.model_dump(mode="json")

    if result.momentum:
        response["momentum"] = {
            k: v.model_dump(mode="json") for k, v in result.momentum.items()
        }

    if result.volatility:
        response["volatility"] = {
            k: v.model_dump(mode="json") for k, v in result.volatility.items()
        }

    if result.volume:
        response["volume"] = result.volume.model_dump(mode="json")

    if result.price:
        response["price"] = result.price.model_dump(mode="json")

    if result.availability:
        response["availability"] = [a.model_dump(mode="json") for a in result.availability]

    if result.warnings:
        response["warnings"] = result.warnings

    return response


# ---------------------------------------------------------------------------
# GET /api/v1/technical-features/multi-timeframe
# ---------------------------------------------------------------------------

@router.get("/technical-features/multi-timeframe")
async def technical_features_multi_timeframe(
    timeframes: str = Query(
        default="1m,5m,15m",
        description="Comma-separated list of timeframes (e.g. 1m,5m,15m)",
    ),
    limit: int = Query(
        default=300,
        ge=50,
        le=5000,
        description="Number of candles per timeframe (50-5000)",
    ),
) -> dict:
    """
    Calculate technical features for multiple timeframes independently.

    Each timeframe is calculated from its own candle series.
    A single timeframe failing does not affect other timeframes.

    Returns a response with per-timeframe FeatureResult objects and
    aggregate feature-set status.
    """
    service = _get_feature_service()

    # Parse comma-separated timeframes
    tf_list = [tf.strip() for tf in timeframes.split(",") if tf.strip()]

    if not tf_list:
        return {
            "error": "No timeframes provided",
            "feature_set_status": "unavailable",
        }

    result = await service.get_features_multi_timeframe(
        timeframes=tf_list,
        limit=limit,
    )

    # Build response
    response = {
        "feature_set_status": result.feature_set_status.value,
        "feature_set_reason": result.feature_set_reason,
        "feature_timestamp": result.feature_timestamp.isoformat(),
        "timeframes": [],
    }

    for tf_result in result.timeframes:
        tf_data = {
            "timeframe": tf_result.timeframe,
            "status": tf_result.result.status.value,
            "reason": tf_result.result.reason,
            "feature_set_status": tf_result.result.feature_set_status.value,
            "feature_set_reason": tf_result.result.feature_set_reason,
        }

        if tf_result.result.volatility_classification:
            tf_data["volatility_classification"] = tf_result.result.volatility_classification.value
        tf_data["volatility_classification_reason"] = tf_result.result.volatility_classification_reason

        if tf_result.result.metadata:
            tf_data["metadata"] = tf_result.result.metadata.model_dump(mode="json")

        if tf_result.result.trend:
            tf_data["trend"] = tf_result.result.trend.model_dump(mode="json")

        if tf_result.result.momentum:
            tf_data["momentum"] = {
                k: v.model_dump(mode="json") for k, v in tf_result.result.momentum.items()
            }

        if tf_result.result.volatility:
            tf_data["volatility"] = {
                k: v.model_dump(mode="json") for k, v in tf_result.result.volatility.items()
            }

        if tf_result.result.volume:
            tf_data["volume"] = tf_result.result.volume.model_dump(mode="json")

        if tf_result.result.price:
            tf_data["price"] = tf_result.result.price.model_dump(mode="json")

        if tf_result.result.availability:
            tf_data["availability"] = [a.model_dump(mode="json") for a in tf_result.result.availability]

        if tf_result.result.warnings:
            tf_data["warnings"] = tf_result.result.warnings

        response["timeframes"].append(tf_data)

    if result.warnings:
        response["warnings"] = result.warnings

    return response
