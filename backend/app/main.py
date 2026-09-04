"""
Scalping Arise — Application Entry Point

Creates and configures the FastAPI application instance.
Future phases will register additional routers, middleware,
and startup/shutdown events here.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1_router
from app.config.settings import Environment, get_settings
from app.core.errors import _CatchUnhandledExceptionsMiddleware, register_error_handlers
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    settings = get_settings()
    logger.info(
        "Starting %s v%s | environment=%s | debug=%s",
        settings.app_name,
        settings.app_version,
        settings.environment.value,
        settings.debug,
    )
    logger.info(
        "Server | host=%s | port=%d | workers=%d",
        settings.host,
        settings.port,
        settings.workers,
    )
    logger.info("API prefix: %s", settings.api_prefix)

    yield

    logger.info("Shutting down %s", settings.app_name)


def create_application() -> FastAPI:
    """
    Application factory.

    Creates and configures the FastAPI application with all
    necessary middleware, routes, and error handlers.
    """
    settings = get_settings()

    # Configure logging before anything else
    setup_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        environment=settings.environment.value,
    )

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="XAU/USD Multi-Timeframe, Multi-Strategy Scalping Signal Intelligence System",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_url="/openapi.json" if settings.is_development else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )

    # Safety-net middleware for unhandled exceptions (outermost layer)
    app.add_middleware(_CatchUnhandledExceptionsMiddleware)

    # Register error handlers
    register_error_handlers(app)

    # Register API routes
    app.include_router(api_v1_router, prefix=settings.api_prefix)

    return app


# Module-level application instance for uvicorn/gunicorn
application = create_application()
