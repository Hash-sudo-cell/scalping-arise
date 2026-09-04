"""
Scalping Arise — Strategy Engine Configuration

Centralized, validated configuration for the strategy evaluation engine.
All values are configurable via environment variables with the
SCALPING_ARISE_ prefix.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrategyEngineSettings(BaseSettings):
    """Strategy evaluation engine configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Strategy engine ---
    strategy_engine_enabled: bool = Field(
        default=True,
        description="Enable the strategy evaluation engine",
    )

    # --- Evaluation limits ---
    max_strategies_per_evaluation: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of strategies to evaluate per request",
    )

    # --- Default timeframes for evaluation ---
    default_evaluation_timeframes: list[str] = Field(
        default=["1m", "5m", "15m"],
        description="Default timeframes used for multi-timeframe strategy evaluation",
    )

    # --- Default candle limits per timeframe ---
    default_candle_limit: int = Field(
        default=300,
        ge=50,
        le=5000,
        description="Default number of candles per timeframe for evaluation",
    )

    # --- Quality scoring ---
    quality_score_enabled: bool = Field(
        default=True,
        description="Enable quality scoring for strategy evaluations",
    )

    # --- Enabled strategies (list of strategy_ids) ---
    enabled_strategies: list[str] = Field(
        default=["trend_continuation", "pullback_continuation", "range_reversal"],
        description="List of enabled strategy IDs",
    )

    @property
    def is_enabled(self) -> bool:
        return self.strategy_engine_enabled


def get_strategy_engine_settings() -> StrategyEngineSettings:
    """Get validated strategy engine settings (uncached for test isolation)."""
    return StrategyEngineSettings()
