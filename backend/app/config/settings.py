"""
Scalping Arise — Centralized Configuration Management

Configuration priority (lowest to highest):
    1. Default application settings
    2. Environment-specific settings
    3. Environment variables
    4. Final validated runtime configuration
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Supported application environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """Core application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="Scalping Arise", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Current environment",
    )
    debug: bool = Field(default=True, description="Debug mode enabled")

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=1, description="Number of worker processes")

    # API
    api_prefix: str = Field(default="/api/v1", description="API route prefix")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        description="Log format string",
    )

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, v: Any) -> Environment:
        if isinstance(v, str):
            v = v.lower().strip()
        try:
            return Environment(v)
        except ValueError:
            return Environment.DEVELOPMENT

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        return self.environment == Environment.TESTING

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """
    Get validated application settings.

    Settings are cached after first load. Environment variables override
    defaults. The cache ensures consistent configuration throughout the
    application lifecycle.
    """
    return AppSettings()
