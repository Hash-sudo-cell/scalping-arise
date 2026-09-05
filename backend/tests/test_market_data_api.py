"""
Scalping Arise — Market Data API Endpoint Tests
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Set test environment
os.environ["SCALPING_ARISE_ENVIRONMENT"] = "testing"
os.environ["SCALPING_ARISE_DEBUG"] = "true"
os.environ["SCALPING_ARISE_LOG_LEVEL"] = "WARNING"
os.environ["SCALPING_ARISE_TWELVE_DATA_API_KEY"] = "test_key"
os.environ["SCALPING_ARISE_PRIMARY_PROVIDER"] = "twelve_data"
os.environ["SCALPING_ARISE_FALLBACK_PROVIDER"] = "yfinance"

from app.main import application


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(application) as c:
        yield c


class TestMarketDataHealth:
    def test_health_endpoint_exists(self, client: TestClient) -> None:
        response = client.get("/api/v1/market-data/health")
        assert response.status_code == 200

    def test_health_returns_expected_fields(self, client: TestClient) -> None:
        response = client.get("/api/v1/market-data/health")
        data = response.json()
        assert "status" in data
        assert "primary" in data
        assert "fallback" in data

    def test_health_status_values(self, client: TestClient) -> None:
        response = client.get("/api/v1/market-data/health")
        data = response.json()
        assert data["status"] in ("healthy", "degraded", "unavailable")


class TestMarketDataCapabilities:
    def test_capabilities_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/v1/market-data/capabilities")
        assert response.status_code == 200

    def test_capabilities_structure(self, client: TestClient) -> None:
        response = client.get("/api/v1/market-data/capabilities")
        data = response.json()
        assert "primary" in data
        assert "fallback" in data
        assert "timeframes" in data
        assert "instruments" in data

    def test_capabilities_has_timeframes(self, client: TestClient) -> None:
        response = client.get("/api/v1/market-data/capabilities")
        data = response.json()
        assert "1h" in data["timeframes"]
        assert "1d" in data["timeframes"]

    def test_capabilities_instruments(self, client: TestClient) -> None:
        response = client.get("/api/v1/market-data/capabilities")
        data = response.json()
        assert "XAU/USD" in data["instruments"]

    def test_capabilities_source_identity(self, client: TestClient) -> None:
        response = client.get("/api/v1/market-data/capabilities")
        data = response.json()
        # Primary should be SPOT
        assert data["primary"]["canonical_instrument"] == "XAU/USD"
        assert data["primary"]["provider_instrument"] == "XAU/USD"
        assert data["primary"]["source_type"] == "spot"
        # Fallback should be FUTURES_PROXY
        assert data["fallback"]["canonical_instrument"] == "XAU/USD"
        assert data["fallback"]["provider_instrument"] == "GC=F"
        assert data["fallback"]["source_type"] == "futures_proxy"


class TestMarketDataCandles:
    def test_invalid_instrument_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/market-data/candles",
            params={"instrument": "INVALID/PAIR", "timeframe": "1h", "limit": 10},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_timeframe_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/market-data/candles",
            params={"instrument": "XAU/USD", "timeframe": "2m", "limit": 10},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_limit_bounds(self, client: TestClient) -> None:
        # Over limit
        response = client.get(
            "/api/v1/market-data/candles",
            params={"instrument": "XAU/USD", "timeframe": "1h", "limit": 10000},
        )
        assert response.status_code == 422

    def test_limit_zero_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/market-data/candles",
            params={"instrument": "XAU/USD", "timeframe": "1h", "limit": 0},
        )
        assert response.status_code == 422


class TestMarketDataLatest:
    def test_unsupported_instrument(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/market-data/latest",
            params={"instrument": "DOGE/USD"},
        )
        assert response.status_code == 422


class TestPhase1HealthStillWorks:
    """Verify Phase 1 functionality is preserved."""

    def test_original_health(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "scalping-arise"
