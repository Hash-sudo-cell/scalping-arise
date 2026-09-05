"""
Scalping Arise — News Intelligence Configuration

Centralized, validated configuration for the news, event &
performance intelligence engine. All values are configurable
via environment variables with the SCALPING_ARISE_ prefix.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.modules.news_intelligence.models import FailPolicy


class NewsIntelligenceSettings(BaseSettings):
    """News, event & performance intelligence configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Module toggle ---
    intelligence_enabled: bool = Field(
        default=True,
        description="Enable the news intelligence module",
    )

    # --- Event data freshness ---
    event_data_max_age_seconds: int = Field(
        default=300,
        ge=0,
        description="Maximum age in seconds for event data to be considered fresh",
    )

    # --- Event protection windows ---
    event_pre_window_seconds: int = Field(
        default=1800,
        ge=0,
        description="Seconds before a HIGH impact event to begin protection",
    )
    event_post_window_seconds: int = Field(
        default=1800,
        ge=0,
        description="Seconds after a HIGH impact event to continue protection",
    )
    event_medium_pre_window_seconds: int = Field(
        default=600,
        ge=0,
        description="Seconds before a MEDIUM impact event to begin protection",
    )
    event_medium_post_window_seconds: int = Field(
        default=600,
        ge=0,
        description="Seconds after a MEDIUM impact event to continue protection",
    )

    # --- Fail policy ---
    event_fail_policy: FailPolicy = Field(
        default=FailPolicy.FAIL_CLOSED,
        description="Behavior when event data is unavailable: fail_open or fail_closed",
    )

    # --- XAU/USD relevance rules ---
    relevant_currencies: list[str] = Field(
        default=["USD", "XAU", "GOLD"],
        description="Currencies/keywords that make an event relevant to XAU/USD",
    )
    high_impact_categories: list[str] = Field(
        default=["central_bank", "interest_rate", "employment", "inflation", "geopolitical"],
        description="Event categories considered high-impact by default",
    )

    # --- Strategy performance ---
    min_performance_sample: int = Field(
        default=20,
        ge=1,
        description="Minimum trades before performance thresholds apply",
    )
    min_win_rate: float = Field(
        default=0.40,
        ge=0.0, le=1.0,
        description="Minimum acceptable win rate",
    )
    max_drawdown_pct: float = Field(
        default=15.0,
        gt=0, le=100,
        description="Maximum acceptable drawdown as % of peak",
    )
    max_consecutive_losses: int = Field(
        default=5,
        ge=1,
        description="Maximum consecutive losses before restriction",
    )
    min_profit_factor: float = Field(
        default=1.0,
        ge=0.0,
        description="Minimum acceptable profit factor",
    )
    recent_trades_window: int = Field(
        default=10,
        ge=1,
        description="Number of recent trades for recent performance window",
    )

    # --- Strategy recovery ---
    recovery_min_sample: int = Field(
        default=10,
        ge=1,
        description="Minimum trades in recovery before re-evaluation",
    )
    recovery_min_win_rate: float = Field(
        default=0.50,
        ge=0.0, le=1.0,
        description="Minimum win rate required during recovery",
    )
    recovery_max_drawdown_pct: float = Field(
        default=10.0,
        gt=0, le=100,
        description="Maximum drawdown allowed during recovery",
    )
    recovery_min_profit_factor: float = Field(
        default=1.2,
        ge=0.0,
        description="Minimum profit factor required during recovery",
    )

    @property
    def is_enabled(self) -> bool:
        return self.intelligence_enabled


def get_news_intelligence_settings() -> NewsIntelligenceSettings:
    """Get validated news intelligence settings (uncached for test isolation)."""
    return NewsIntelligenceSettings()
