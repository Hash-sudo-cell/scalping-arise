"""
Scalping Arise — Structured Error Handling

Provides consistent API error responses and exception handling.
All errors return a predictable JSON structure without exposing
internal stack traces.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)


class APIError(Exception):
    """
    Structured API error.

    Inherits from Exception so FastAPI/Starlette exception handlers
    can register it. Carries a code, message, HTTP status, and optional
    details dict for consistent JSON error responses.
    """

    def __init__(
        self,
        code: str = "INTERNAL_ERROR",
        message: str = "An error occurred",
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details

    def to_response(self) -> JSONResponse:
        body: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            body["error"]["details"] = self.details
        return JSONResponse(status_code=self.status_code, content=body)


# Pre-defined error types for common cases
class NotFoundError(APIError):
    def __init__(
        self,
        message: str = "Resource not found",
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(code="NOT_FOUND", message=message, status_code=404, details=details)


class ValidationError(APIError):
    def __init__(
        self,
        message: str = "Validation failed",
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=422, details=details)


class InternalError(APIError):
    def __init__(
        self,
        message: str = "Internal server error",
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(code="INTERNAL_ERROR", message=message, status_code=500, details=details)


class ServiceUnavailableError(APIError):
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            message=message,
            status_code=503,
            details=details,
        )


class _CatchUnhandledExceptionsMiddleware(BaseHTTPMiddleware):
    """
    Safety-net middleware that catches any exception not handled by
    the application's exception handlers and returns a structured
    500 response instead of propagating a raw stack trace.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                    }
                },
            )


def register_error_handlers(app: FastAPI) -> None:
    """
    Register global error handling on the FastAPI application.

    Structured error types (APIError subclasses) are registered via
    FastAPI's exception_handler mechanism. A catch-all middleware
    handles any unexpected exception that escapes the handler chain.
    """

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return exc.to_response()

    # Catch-all middleware is added in main.py after app creation
    # to ensure it wraps the entire request lifecycle.
