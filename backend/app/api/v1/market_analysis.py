"""
Scalping Arise — Market Analysis API Endpoints

Minimal API surface for Phase 3 verification.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.core.errors import NotFoundError, ValidationError
from app.modules.market_analysis.config import get_market_analysis_settings
from app.modules.market_analysis.models import AnalysisStatus
from app.modules.market_analysis.service import MarketAnalysisService
from app.modules.market_data.models import Instrument, Timeframe
from app.modules.market_data.service import MarketDataService

router = APIRouter(tags=["market-analysis"])

# Module-level service instances (created lazily on first request)
_analysis_service: Optional[MarketAnalysisService] = None
_market_data_service: Optional[MarketDataService] = None


def _get_analysis_service() -> MarketAnalysisService:
    """Get or create the market analysis service singleton."""
    global _analysis_service, _market_data_service
    if _analysis_service is None:
        _market_data_service = MarketDataService()
        _analysis_service = MarketAnalysisService(
            market_data_service=_market_data_service,
        )
    return _analysis_service


# ---------------------------------------------------------------------------
# GET /api/v1/market-analysis/health
# ---------------------------------------------------------------------------

@router.get("/market-analysis/health")
async def market_analysis_health() -> dict:
    """
    Market analysis subsystem health check.

    Reports whether the analysis engine is operational and its dependencies.
    """
    return {
        "status": "healthy",
        "module": "market_analysis",
        "version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# GET /api/v1/market-analysis/capabilities
# ---------------------------------------------------------------------------

@router.get("/market-analysis/capabilities")
async def market_analysis_capabilities() -> dict:
    """
    Expose current market analysis capabilities.

    Reports supported analyses, configuration, and analysis limits.
    """
    settings = get_market_analysis_settings()
    return {
        "supported_analyses": [
            "swing_detection",
            "market_structure",
            "trend_classification",
            "bos_detection",
            "choch_detection",
            "support_resistance",
            "session_classification",
            "market_regime",
        ],
        "configuration": {
            "min_candles_for_analysis": settings.min_candles_for_analysis,
            "swing_lookback": settings.swing_lookback,
            "bos_confirmation_mode": settings.bos_confirmation_mode,
            "bos_min_break_pct": settings.bos_min_break_pct,
            "sr_zone_tolerance_pct": settings.sr_zone_tolerance_pct,
            "sr_min_swings": settings.sr_min_swings,
            "regime_trend_min_consecutive": settings.regime_trend_min_consecutive,
        },
        "supported_instruments": [i.value for i in Instrument],
        "supported_timeframes": [t.value for t in Timeframe],
    }


# ---------------------------------------------------------------------------
# GET /api/v1/market-analysis
# ---------------------------------------------------------------------------

@router.get("/market-analysis")
async def market_analysis(
    instrument: str = Query(
        default="XAU/USD",
        description="Canonical instrument name (e.g. XAU/USD)",
    ),
    timeframe: str = Query(
        default="1h",
        description="Candle timeframe (e.g. 1m, 5m, 15m, 1h, 4h, 1d)",
    ),
    limit: int = Query(
        default=200,
        ge=20,
        le=5000,
        description="Number of candles to fetch for analysis (20-5000)",
    ),
) -> dict:
    """
    Run the full market analysis pipeline.

    Returns structured analysis including trend, structure, BOS/CHOCH,
    support/resistance, session, and market regime.
    """
    # Validate instrument
    try:
        inst = Instrument(instrument)
    except ValueError:
        raise ValidationError(
            message=f"Unsupported instrument: {instrument}",
            details={"allowed": [i.value for i in Instrument]},
        )

    # Validate timeframe
    try:
        tf = Timeframe(timeframe)
    except ValueError:
        allowed = [t.value for t in Timeframe]
        raise ValidationError(
            message=f"Unsupported timeframe: {timeframe}",
            details={"allowed": allowed},
        )

    service = _get_analysis_service()
    result = await service.analyze(
        instrument=inst,
        timeframe=tf,
        limit=limit,
    )

    response = {
        "status": result.status.value,
        "reason": result.reason,
        "analysis_timestamp": result.analysis_timestamp.isoformat(),
    }

    if result.context:
        response["context"] = result.context.model_dump(mode="json")

    if result.trend:
        response["trend"] = result.trend.model_dump(mode="json")

    if result.structure:
        response["structure"] = {
            "latest_labels": [l.value for l in result.structure.latest_labels],
            "point_count": len(result.structure.points),
        }

    if result.events:
        response["events"] = {
            "bos": [e.model_dump(mode="json") for e in result.events.bos],
            "choch": [e.model_dump(mode="json") for e in result.events.choch],
        }

    if result.zones:
        response["zones"] = {
            "support": [z.model_dump(mode="json") for z in result.zones.support],
            "resistance": [z.model_dump(mode="json") for z in result.zones.resistance],
        }

    if result.session:
        response["session"] = result.session.value

    if result.regime:
        response["regime"] = result.regime.model_dump(mode="json")

    return response
