"""
Scalping Arise — Signal Engine Configuration

Centralized, validated configuration for the signal and confirmation engine.
All values are configurable via environment variables with the
SCALPING_ARISE_ prefix.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SignalEngineSettings(BaseSettings):
    """Signal engine configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Signal engine ---
    signal_engine_enabled: bool = Field(
        default=True,
        description="Enable the signal and confirmation engine",
    )

    # --- Confidence thresholds ---
    minimum_confidence_threshold: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="Minimum overall confidence score for a signal to be QUALIFIED",
    )

    strong_confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence score above which a signal is considered STRONG",
    )

    # --- Multi-timeframe confirmation ---
    require_mtf_confirmation: bool = Field(
        default=True,
        description="Require at least one higher timeframe to confirm the signal direction",
    )

    mtf_min_aligned_timeframes: int = Field(
        default=1,
        ge=0,
        le=10,
        description="Minimum number of timeframes that must align for MTF confirmation",
    )

    # --- Conflict resolution ---
    enable_conflict_resolution: bool = Field(
        default=True,
        description="Enable automatic conflict resolution when strategies disagree",
    )

    min_candidates_for_signal: int = Field(
        default=1,
        ge=1,
        le=50,
        description="Minimum number of qualified candidates needed to produce a signal",
    )

    # --- Default timeframes ---
    default_evaluation_timeframes: list[str] = Field(
        default=["1m", "5m", "15m"],
        description="Default timeframes used for signal evaluation",
    )

    # --- Default candle limits per timeframe ---
    default_candle_limit: int = Field(
        default=300,
        ge=50,
        le=5000,
        description="Default number of candles per timeframe for evaluation",
    )

    @property
    def is_enabled(self) -> bool:
        return self.signal_engine_enabled


def get_signal_engine_settings() -> SignalEngineSettings:
    """Get validated signal engine settings (uncached for test isolation)."""
    return SignalEngineSettings()
