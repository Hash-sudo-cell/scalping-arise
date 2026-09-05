"""
Scalping Arise — Market Analysis API Tests

Tests for the Phase 3 API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import application

client = TestClient(app=application)


class TestMarketAnalysisHealth:
    def test_health_endpoint_exists(self) -> None:
        """GET /api/v1/market-analysis/health should return 200."""
        response = client.get("/api/v1/market-analysis/health")
        assert response.status_code == 200

    def test_health_structure(self) -> None:
        """Health response should have status, module, version."""
        data = response.json() if (response := client.get("/api/v1/market-analysis/health")).status_code == 200 else {}
        assert "status" in data
        assert data["status"] == "healthy"
        assert data["module"] == "market_analysis"


class TestMarketAnalysisCapabilities:
    def test_capabilities_endpoint(self) -> None:
        """GET /api/v1/market-analysis/capabilities should return 200."""
        response = client.get("/api/v1/market-analysis/capabilities")
        assert response.status_code == 200

    def test_capabilities_structure(self) -> None:
        """Capabilities should include supported analyses and configuration."""
        data = client.get("/api/v1/market-analysis/capabilities").json()
        assert "supported_analyses" in data
        assert "configuration" in data
        assert "swing_detection" in data["supported_analyses"]
        assert "market_structure" in data["supported_analyses"]
        assert "trend_classification" in data["supported_analyses"]
        assert "bos_detection" in data["supported_analyses"]
        assert "choch_detection" in data["supported_analyses"]
        assert "support_resistance" in data["supported_analyses"]
        assert "session_classification" in data["supported_analyses"]
        assert "market_regime" in data["supported_analyses"]

    def test_capabilities_has_timeframes(self) -> None:
        """Capabilities should list supported timeframes."""
        data = client.get("/api/v1/market-analysis/capabilities").json()
        assert "supported_timeframes" in data
        assert "1h" in data["supported_timeframes"]

    def test_capabilities_has_instruments(self) -> None:
        """Capabilities should list supported instruments."""
        data = client.get("/api/v1/market-analysis/capabilities").json()
        assert "supported_instruments" in data
        assert "XAU/USD" in data["supported_instruments"]


class TestMarketAnalysisEndpoint:
    def test_invalid_instrument_rejected(self) -> None:
        """Invalid instrument should return 422."""
        response = client.get(
            "/api/v1/market-analysis",
            params={"instrument": "DOGE/USD", "timeframe": "1h", "limit": 200},
        )
        assert response.status_code == 422

    def test_invalid_timeframe_rejected(self) -> None:
        """Invalid timeframe should return 422."""
        response = client.get(
            "/api/v1/market-analysis",
            params={"instrument": "XAU/USD", "timeframe": "2h", "limit": 200},
        )
        assert response.status_code == 422

    def test_limit_bounds(self) -> None:
        """Limit below 20 should return 422."""
        response = client.get(
            "/api/v1/market-analysis",
            params={"instrument": "XAU/USD", "timeframe": "1h", "limit": 5},
        )
        assert response.status_code == 422

    def test_analysis_returns_structure(self) -> None:
        """Valid analysis request should return structured response."""
        response = client.get(
            "/api/v1/market-analysis",
            params={"instrument": "XAU/USD", "timeframe": "1h", "limit": 200},
        )
        # Should return 200 or 200 with analysis result
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ("available", "unavailable")
        assert "analysis_timestamp" in data

    def test_analysis_has_reason(self) -> None:
        """Analysis response should include a reason."""
        response = client.get(
            "/api/v1/market-analysis",
            params={"instrument": "XAU/USD", "timeframe": "1h", "limit": 200},
        )
        data = response.json()
        assert "reason" in data
        assert isinstance(data["reason"], str)


class TestPhase1HealthStillWorks:
    def test_original_health(self) -> None:
        """Phase 1 health endpoint should still work."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
