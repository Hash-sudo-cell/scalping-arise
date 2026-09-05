"""
Scalping Arise — API v1 Router

Central router for all v1 API endpoints.
New endpoint modules are imported and included here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.market_analysis import router as market_analysis_router
from app.api.v1.market_data import router as market_data_router
from app.api.v1.technical_features import router as technical_features_router
from app.api.v1.strategies import router as strategies_router
from app.api.v1.signals import router as signals_router
from app.api.v1.trade_planning import router as trade_planning_router
from app.api.v1.intelligence import router as intelligence_router
from app.api.v1.backtesting import router as backtesting_router

router = APIRouter()

# Include endpoint routers
router.include_router(health_router)
router.include_router(market_data_router)
router.include_router(market_analysis_router)
router.include_router(technical_features_router)
router.include_router(strategies_router)
router.include_router(signals_router)
router.include_router(trade_planning_router)
router.include_router(intelligence_router)
router.include_router(backtesting_router)
