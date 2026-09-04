"""
Scalping Arise — Market Data Configuration

Centralized configuration for market data providers, validation,
and caching. All values are configurable via environment variables
with the SCALPING_ARISE_ prefix.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.modules.market_data.models import Instrument, Timeframe


class MarketDataSettings(BaseSettings):
    """Market data subsystem configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Provider selection ---
    primary_provider: str = Field(
        default="twelve_data",
        description="Primary market data provider identifier",
    )
    fallback_provider: str = Field(
        default="yfinance",
        description="Fallback market data provider identifier",
    )

    # --- Twelve Data ---
    twelve_data_api_key: str = Field(
        default="",
        description="Twelve Data API key (free tier: 800 req/day)",
    )
    twelve_data_base_url: str = Field(
        default="https://api.twelvedata.com",
        description="Twelve Data REST API base URL",
    )

    # --- Request behavior ---
    request_timeout_seconds: float = Field(
        default=10.0,
        description="HTTP request timeout for provider calls",
    )
    max_retries: int = Field(
        default=2,
        description="Maximum retry attempts for transient provider failures",
    )
    retry_delay_seconds: float = Field(
        default=1.0,
        description="Base delay between retries (exponential backoff)",
    )

    # --- Data freshness ---
    freshness_tolerance_seconds: dict[str, int] = Field(
        default={
            "1m": 120,
            "3m": 300,
            "5m": 600,
            "15m": 1800,
            "30m": 3600,
            "1h": 7200,
            "4h": 28800,
            "1d": 172800,
            "1w": 604800,
            "1mo": 2_592_000,
        },
        description="Maximum allowed data age per timeframe (seconds)",
    )

    # --- Price consistency ---
    price_consistency_tolerance_pct: float = Field(
        default=0.5,
        description="Max allowed price difference (%) between providers for fallback validation",
    )

    # --- Cache ---
    cache_enabled: bool = Field(
        default=True,
        description="Enable in-memory candle caching",
    )
    cache_ttl_seconds: int = Field(
        default=60,
        description="Time-to-live for cached candles (seconds)",
    )
    cache_max_candles: int = Field(
        default=10_000,
        description="Maximum number of candles to hold in cache",
    )

    # --- Allowed instruments ---
    allowed_instruments: list[str] = Field(
        default=["XAU/USD"],
        description="List of allowed canonical instrument names",
    )

    # --- Symbol mapping (provider-specific overrides) ---
    twelve_data_symbol_xau_usd: str = Field(
        default="XAU/USD",
        description="Twelve Data symbol for XAU/USD",
    )
    yfinance_symbol_xau_usd: str = Field(
        default="GC=F",
        description="yfinance ticker for XAU/USD (Gold Futures)",
    )

    @property
    def freshness_map(self) -> dict[str, int]:
        return self.freshness_tolerance_seconds


def get_market_data_settings() -> MarketDataSettings:
    """Get validated market data settings (uncached for test isolation)."""
    return MarketDataSettings()
