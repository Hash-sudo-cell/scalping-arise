"""
Scalping Arise — System Readiness Aggregator

Checks health of all upstream modules and aggregates into
a single system readiness status.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.modules.decision.config import DecisionEngineSettings
from app.modules.decision.models import (
    ModuleReadiness,
    ProvenanceSource,
    SystemReadiness,
)

logger = logging.getLogger(__name__)


async def _check_market_data_health(timeout: float) -> ModuleReadiness:
    """Check Phase 2 market data health."""
    t0 = time.monotonic()
    try:
        from app.modules.market_data.service import MarketDataService
        service = MarketDataService()
        health = await asyncio.wait_for(service.health_check(), timeout=timeout)
        latency = (time.monotonic() - t0) * 1000
        healthy = getattr(health, "status", "unknown") == "healthy" if hasattr(health, "status") else True
        return ModuleReadiness(
            module=ProvenanceSource.MARKET_DATA,
            healthy=healthy,
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        return ModuleReadiness(
            module=ProvenanceSource.MARKET_DATA,
            healthy=False,
            latency_ms=round(latency, 2),
            error=str(e)[:200],
        )


async def _check_signal_engine_health(timeout: float) -> ModuleReadiness:
    """Check Phase 6 signal engine health."""
    t0 = time.monotonic()
    try:
        from app.modules.signal_engine.service import SignalEngineService
        from app.modules.market_data.service import MarketDataService
        from app.modules.market_analysis.service import MarketAnalysisService
        from app.modules.technical_features.service import TechnicalFeatureService
        from app.modules.strategies.service import StrategyEvaluationService

        md = MarketDataService()
        analysis = MarketAnalysisService(market_data_service=md)
        features = TechnicalFeatureService(market_data_service=md)
        strategies = StrategyEvaluationService(
            market_data_service=md, analysis_service=analysis, feature_service=features,
        )
        signal = SignalEngineService(
            market_data_service=md, analysis_service=analysis,
            feature_service=features, strategy_service=strategies,
        )
        health = await asyncio.wait_for(signal.health_check(), timeout=timeout)
        latency = (time.monotonic() - t0) * 1000
        healthy = health.get("status") == "healthy" if isinstance(health, dict) else True
        return ModuleReadiness(
            module=ProvenanceSource.SIGNAL_ENGINE,
            healthy=healthy,
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        return ModuleReadiness(
            module=ProvenanceSource.SIGNAL_ENGINE,
            healthy=False,
            latency_ms=round(latency, 2),
            error=str(e)[:200],
        )


async def _check_trade_planning_health(timeout: float) -> ModuleReadiness:
    """Check Phase 7 trade planning health."""
    t0 = time.monotonic()
    try:
        from app.modules.trade_planning.service import TradePlanningService
        service = TradePlanningService()
        health = await asyncio.wait_for(service.health_check(), timeout=timeout)
        latency = (time.monotonic() - t0) * 1000
        healthy = health.get("status") == "healthy" if isinstance(health, dict) else True
        return ModuleReadiness(
            module=ProvenanceSource.TRADE_PLANNING,
            healthy=healthy,
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        return ModuleReadiness(
            module=ProvenanceSource.TRADE_PLANNING,
            healthy=False,
            latency_ms=round(latency, 2),
            error=str(e)[:200],
        )


async def _check_intelligence_health(timeout: float) -> ModuleReadiness:
    """Check Phase 8 news intelligence health."""
    t0 = time.monotonic()
    try:
        from app.modules.news_intelligence.service import NewsIntelligenceService
        service = NewsIntelligenceService()
        health = await asyncio.wait_for(service.health_check(), timeout=timeout)
        latency = (time.monotonic() - t0) * 1000
        healthy = health.get("status") == "healthy" if isinstance(health, dict) else True
        return ModuleReadiness(
            module=ProvenanceSource.NEWS_INTELLIGENCE,
            healthy=healthy,
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        return ModuleReadiness(
            module=ProvenanceSource.NEWS_INTELLIGENCE,
            healthy=False,
            latency_ms=round(latency, 2),
            error=str(e)[:200],
        )


# Health check registry
_HEALTH_CHECKERS: dict[ProvenanceSource, any] = {
    ProvenanceSource.MARKET_DATA: _check_market_data_health,
    ProvenanceSource.SIGNAL_ENGINE: _check_signal_engine_health,
    ProvenanceSource.TRADE_PLANNING: _check_trade_planning_health,
    ProvenanceSource.NEWS_INTELLIGENCE: _check_intelligence_health,
}


async def check_system_readiness(
    settings: Optional[DecisionEngineSettings] = None,
) -> SystemReadiness:
    """
    Check health of all critical modules and aggregate into readiness.

    A system is "ready" if at minimum the market data module is healthy.
    Other modules degrade gracefully.

    Returns:
        SystemReadiness with per-module status and overall readiness.
    """
    from app.modules.decision.config import get_decision_engine_settings

    cfg = settings or get_decision_engine_settings()
    timeout = cfg.readiness_check_timeout_seconds

    t0 = time.monotonic()
    modules: list[ModuleReadiness] = []

    # Run all health checks concurrently
    tasks = {
        source: asyncio.create_task(checker(timeout))
        for source, checker in _HEALTH_CHECKERS.items()
    }

    for source, task in tasks.items():
        try:
            result = await task
            modules.append(result)
        except Exception as e:
            modules.append(ModuleReadiness(
                module=source,
                healthy=False,
                error=str(e)[:200],
            ))

    total_latency = (time.monotonic() - t0) * 1000
    healthy_count = sum(1 for m in modules if m.healthy)
    total_count = len(modules)

    # System is ready if market data is healthy (minimum viable)
    market_data_healthy = any(
        m.module == ProvenanceSource.MARKET_DATA and m.healthy
        for m in modules
    )
    # Also require at least 50% of modules to be healthy
    ready = market_data_healthy and (healthy_count / total_count >= 0.5) if total_count > 0 else False

    return SystemReadiness(
        ready=ready,
        healthy_count=healthy_count,
        total_count=total_count,
        modules=modules,
        checked_at=datetime.now(timezone.utc),
        overall_latency_ms=round(total_latency, 2),
    )


def check_system_readiness_sync(
    settings: Optional[DecisionEngineSettings] = None,
) -> SystemReadiness:
    """
    Synchronous wrapper for system readiness check.

    Runs the async check in a new event loop if needed.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context — use a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, check_system_readiness(settings))
                return future.result(timeout=10.0)
        else:
            return loop.run_until_complete(check_system_readiness(settings))
    except RuntimeError:
        return asyncio.run(check_system_readiness(settings))
