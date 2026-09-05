"""
Scalping Arise — Market Data API Endpoints

Minimal API surface for Phase 2 verification.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.core.errors import NotFoundError, ValidationError
from app.modules.market_data.config import get_market_data_settings
from app.modules.market_data.models import Instrument, Timeframe
from app.modules.market_data.service import MarketDataService

router = APIRouter(tags=["market-data"])

# Module-level service instance (created lazily on first request)
_service: Optional[MarketDataService] = None


def _get_service() -> MarketDataService:
    """Get or create the market data service singleton."""
    global _service
    if _service is None:
        _service = MarketDataService()
    return _service


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/health
# ---------------------------------------------------------------------------

@router.get("/market-data/health")
async def market_data_health() -> dict:
    """
    Market data subsystem health check.

    Reports provider status, active source, and overall health
    without exposing secrets.
    """
    service = _get_service()
    health = await service.health_check()
    return health.model_dump(mode="json")


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/candles
# ---------------------------------------------------------------------------

@router.get("/market-data/candles")
async def market_data_candles(
    instrument: str = Query(
        default="XAU/USD",
        description="Canonical instrument name (e.g. XAU/USD)",
    ),
    timeframe: str = Query(
        default="1h",
        description="Candle timeframe (e.g. 1m, 5m, 15m, 1h, 4h, 1d)",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=5000,
        description="Number of candles to return (1-5000)",
    ),
) -> dict:
    """
    Fetch validated historical candles.

    Returns normalized OHLCV candles with validation metadata.
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

    service = _get_service()
    response = await service.fetch_candles(inst, tf, limit)

    return {
        "instrument": response.instrument.value,
        "timeframe": response.timeframe.value,
        "source": response.source,
        "source_type": response.source_type.value,
        "count": response.count,
        "has_gaps": response.has_gaps,
        "candles": [c.model_dump(mode="json") for c in response.candles],
    }


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/latest
# ---------------------------------------------------------------------------

@router.get("/market-data/latest")
async def market_data_latest(
    instrument: str = Query(
        default="XAU/USD",
        description="Canonical instrument name",
    ),
) -> dict:
    """
    Fetch latest market price for an instrument.

    Clearly indicates whether data is from a forming candle.
    """
    try:
        inst = Instrument(instrument)
    except ValueError:
        raise ValidationError(
            message=f"Unsupported instrument: {instrument}",
            details={"allowed": [i.value for i in Instrument]},
        )

    service = _get_service()
    price = await service.fetch_latest_price(inst)

    if price is None:
        raise NotFoundError(
            message=f"Latest price unavailable for {instrument}",
            details={"instrument": instrument},
        )

    return price.model_dump(mode="json")


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/capabilities
# ---------------------------------------------------------------------------

@router.get("/market-data/capabilities")
async def market_data_capabilities() -> dict:
    """
    Expose current market data capabilities.

    Reports supported instruments, timeframe capabilities (native/derived/unsupported),
    and provider details.
    """
    service = _get_service()
    return service.get_capabilities()


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/live/status
# ---------------------------------------------------------------------------

@router.get("/market-data/live/status")
async def market_data_live_status() -> dict:
    """
    Get live streaming status.

    Reports connection state, active timeframes, price verification,
    and reconnection status. Returns 503 if live streaming is disabled.
    """
    service = _get_service()
    status = service.get_live_status()

    if status is None:
        return {
            "enabled": False,
            "connection_state": "disconnected",
            "message": "Live streaming not enabled or not started",
        }

    return status


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/live/price
# ---------------------------------------------------------------------------

@router.get("/market-data/live/price")
async def market_data_live_price() -> dict:
    """
    Get the current live price from OANDA with TradingView verification.

    Returns bid/ask/spread, TV divergence, and verification status.
    """
    service = _get_service()
    price = service.get_live_price()

    if price is None:
        raise NotFoundError(
            message="Live price unavailable",
            details={"reason": "Live streaming not active"},
        )

    return price.model_dump(mode="json")


# ---------------------------------------------------------------------------
# GET /api/v1/market-data/live/candle
# ---------------------------------------------------------------------------

@router.get("/market-data/live/candle")
async def market_data_live_candle(
    timeframe: str = Query(
        default="1m",
        description="Timeframe for the forming candle",
    ),
) -> dict:
    """
    Get the current forming candle for a timeframe.

    Returns the live forming candle with its current OHLCV state.
    """
    try:
        tf = Timeframe(timeframe)
    except ValueError:
        allowed = [t.value for t in Timeframe]
        raise ValidationError(
            message=f"Unsupported timeframe: {timeframe}",
            details={"allowed": allowed},
        )

    service = _get_service()
    candle = service.get_live_forming_candle(tf)

    if candle is None:
        return {
            "timeframe": tf.value,
            "candle": None,
            "message": "No forming candle available",
        }

    return {
        "timeframe": tf.value,
        "candle": candle.model_dump(mode="json"),
    }
