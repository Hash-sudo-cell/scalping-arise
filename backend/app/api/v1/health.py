"""
Scalping Arise — Health Check Endpoint

Provides a simple health check for monitoring application status.
In future phases, this will expand to check data feeds, database,
and pipeline health.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """
    Application health check endpoint.

    Returns basic application status including version, environment,
    and current timestamp. This endpoint does not require authentication
    and should always be accessible for monitoring.
    """
    settings = get_settings()
    return {
        "status": "healthy",
        "service": settings.app_name.lower().replace(" ", "-"),
        "version": settings.app_version,
        "environment": settings.environment.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
