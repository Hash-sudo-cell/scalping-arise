"""
Scalping Arise — Error Handling Tests
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import (
    InternalError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
    _CatchUnhandledExceptionsMiddleware,
    register_error_handlers,
)


def _create_test_app() -> FastAPI:
    """Create a minimal test app with error handlers registered."""
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(_CatchUnhandledExceptionsMiddleware)

    @app.get("/test/not-found")
    async def raise_not_found():
        raise NotFoundError(message="Widget not found")

    @app.get("/test/validation")
    async def raise_validation():
        raise ValidationError(message="Invalid input", details={"field": "price"})

    @app.get("/test/internal")
    async def raise_internal():
        raise InternalError()

    @app.get("/test/service-unavailable")
    async def raise_service_unavailable():
        raise ServiceUnavailableError(message="Feed offline")

    @app.get("/test/unhandled")
    async def raise_unhandled():
        raise RuntimeError("Something broke")

    return app


def test_not_found_returns_404() -> None:
    app = _create_test_app()
    with TestClient(app) as client:
        response = client.get("/test/not-found")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"
        assert data["error"]["message"] == "Widget not found"


def test_validation_returns_422() -> None:
    app = _create_test_app()
    with TestClient(app) as client:
        response = client.get("/test/validation")
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert data["error"]["details"]["field"] == "price"


def test_internal_returns_500() -> None:
    app = _create_test_app()
    with TestClient(app) as client:
        response = client.get("/test/internal")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_ERROR"


def test_service_unavailable_returns_503() -> None:
    app = _create_test_app()
    with TestClient(app) as client:
        response = client.get("/test/service-unavailable")
        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_unhandled_exception_returns_500() -> None:
    app = _create_test_app()
    with TestClient(app) as client:
        response = client.get("/test/unhandled")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_ERROR"
        # Internal stack trace must not be exposed
        assert "RuntimeError" not in str(data)


def test_error_response_structure() -> None:
    """All error responses should have consistent structure."""
    app = _create_test_app()
    with TestClient(app) as client:
        for path in ["/test/not-found", "/test/validation", "/test/internal"]:
            response = client.get(path)
            data = response.json()
            assert "error" in data
            assert "code" in data["error"]
            assert "message" in data["error"]
