"""
Scalping Arise — Market Analysis Configuration

Centralized, validated configuration for the analysis engine.
All values are configurable via environment variables with the
SCALPING_ARISE_ prefix.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MarketAnalysisSettings(BaseSettings):
    """Market analysis engine configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Analysis validation ---
    min_candles_for_analysis: int = Field(
        default=20,
        description="Minimum closed candles required before analysis can proceed",
    )

    # --- Swing detection ---
    swing_lookback: int = Field(
        default=3,
        description="Number of candles on each side to confirm a swing point",
    )

    # --- BOS / CHOCH ---
    bos_confirmation_mode: str = Field(
        default="close",
        description="How BOS break is confirmed: 'close' for close-based, 'wick' for wick-based",
    )
    bos_min_break_pct: float = Field(
        default=0.0,
        description="Minimum break distance as a percentage of the broken level (0 = any close beyond)",
    )

    # --- Support / Resistance ---
    sr_zone_tolerance_pct: float = Field(
        default=0.1,
        description="Zone merge tolerance as percentage: swings within this % are grouped into one zone",
    )
    sr_min_swings: int = Field(
        default=2,
        description="Minimum number of swings to define a zone",
    )

    # --- Sessions (UTC hours) ---
    session_asian_start: int = Field(default=0, description="Asian session start hour (UTC)")
    session_asian_end: int = Field(default=8, description="Asian session end hour (UTC)")
    session_london_start: int = Field(default=7, description="London session start hour (UTC)")
    session_london_end: int = Field(default=16, description="London session end hour (UTC)")
    session_newyork_start: int = Field(default=12, description="New York session start hour (UTC)")
    session_newyork_end: int = Field(default=21, description="New York session end hour (UTC)")

    # --- Regime ---
    regime_trend_min_consecutive: int = Field(
        default=3,
        description="Minimum consecutive HH/HL or LH/LL to classify as trending",
    )
    regime_range_max_swing_pct: float = Field(
        default=0.5,
        description="Maximum swing range as % of price to classify as ranging",
    )

    # --- Liquidity Analysis ---
    liquidity_equal_level_tolerance_pct: float = Field(
        default=0.05,
        description="Tolerance (%) for clustering swing highs/lows into equal highs/lows. "
                    "Swings within this percentage of each other are grouped.",
    )
    liquidity_min_touches: int = Field(
        default=2,
        ge=1,
        description="Minimum number of swings required to form an equal highs/lows pool",
    )
    liquidity_sweep_mode: str = Field(
        default="wick",
        description="Sweep detection mode: 'wick' for wick-based, 'close' for close-based",
    )
    liquidity_min_sweep_distance_pct: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum distance beyond pool level (%) for a valid sweep (0 = any cross)",
    )
    liquidity_max_active_pools: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of active liquidity pools to retain",
    )
    liquidity_max_history_depth: int = Field(
        default=50,
        ge=5,
        le=500,
        description="Maximum number of candles to look back for sweep reaction classification",
    )


def get_market_analysis_settings() -> MarketAnalysisSettings:
    """Get validated market analysis settings (uncached for test isolation)."""
    return MarketAnalysisSettings()
