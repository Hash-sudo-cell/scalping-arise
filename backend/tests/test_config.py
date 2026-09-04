"""
Scalping Arise — Configuration Tests
"""

from __future__ import annotations

import os

from app.config.settings import AppSettings, Environment


def test_settings_default_values() -> None:
    """Settings should have sensible defaults."""
    os.environ.pop("SCALPING_ARISE_APP_NAME", None)
    os.environ.pop("SCALPING_ARISE_ENVIRONMENT", None)
    settings = AppSettings()
    assert settings.app_name == "Scalping Arise"
    assert settings.app_version == "1.0.0"
    assert settings.port == 8000


def test_settings_environment_override() -> None:
    """Settings should accept environment variable overrides."""
    os.environ["SCALPING_ARISE_APP_NAME"] = "Test App"
    settings = AppSettings()
    assert settings.app_name == "Test App"
    # Cleanup
    del os.environ["SCALPING_ARISE_APP_NAME"]


def test_settings_environment_enum() -> None:
    """Settings should normalize environment values."""
    settings = AppSettings(environment="development")
    assert settings.environment == Environment.DEVELOPMENT

    settings = AppSettings(environment="testing")
    assert settings.environment == Environment.TESTING

    settings = AppSettings(environment="production")
    assert settings.environment == Environment.PRODUCTION


def test_settings_is_development() -> None:
    """is_development should return True for development environment."""
    settings = AppSettings(environment="development")
    assert settings.is_development is True
    assert settings.is_production is False
    assert settings.is_testing is False


def test_settings_is_production() -> None:
    """is_production should return True for production environment."""
    settings = AppSettings(environment="production")
    assert settings.is_production is True
    assert settings.is_development is False


def test_settings_cors_origins() -> None:
    """CORS origins should be configurable."""
    settings = AppSettings()
    assert isinstance(settings.cors_origins, list)
    assert len(settings.cors_origins) > 0
