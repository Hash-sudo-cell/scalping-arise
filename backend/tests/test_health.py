"""
Scalping Arise — Health Endpoint Tests
"""

from __future__ import annotations


def test_health_returns_200(client) -> None:
    """Health endpoint should return 200 OK."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_returns_correct_structure(client) -> None:
    """Health endpoint should return expected JSON structure."""
    response = client.get("/api/v1/health")
    data = response.json()

    assert "status" in data
    assert "service" in data
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data


def test_health_status_is_healthy(client) -> None:
    """Health endpoint should report healthy status."""
    response = client.get("/api/v1/health")
    data = response.json()
    assert data["status"] == "healthy"


def test_health_service_name(client) -> None:
    """Health endpoint should return correct service name."""
    response = client.get("/api/v1/health")
    data = response.json()
    assert data["service"] == "scalping-arise"


def test_health_version(client) -> None:
    """Health endpoint should return a version string."""
    response = client.get("/api/v1/health")
    data = response.json()
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


def test_health_environment(client) -> None:
    """Health endpoint should return the current environment."""
    response = client.get("/api/v1/health")
    data = response.json()
    assert data["environment"] in ("development", "testing", "production")


def test_health_timestamp_is_iso(client) -> None:
    """Health endpoint should return an ISO-formatted timestamp."""
    response = client.get("/api/v1/health")
    data = response.json()
    assert "T" in data["timestamp"]  # Basic ISO format check
