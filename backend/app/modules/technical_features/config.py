"""
Scalping Arise — Technical Features Configuration

Centralized, validated configuration for all indicator parameters.
All values are configurable via environment variables with the
SCALPING_ARISE_ prefix.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TechnicalFeaturesSettings(BaseSettings):
    """Technical features engine configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Data validation ---
    min_candles_for_features: int = Field(
        default=30,
        description="Minimum closed candles required before features can be calculated",
    )

    # --- EMA ---
    ema_fast_period: int = Field(default=20, description="Fast EMA period")
    ema_medium_period: int = Field(default=50, description="Medium EMA period")
    ema_slow_period: int = Field(default=200, description="Slow EMA period")

    # --- RSI ---
    rsi_period: int = Field(default=14, description="RSI lookback period")
    rsi_oversold_threshold: float = Field(default=30.0, description="RSI oversold boundary")
    rsi_weak_threshold: float = Field(default=40.0, description="RSI weak boundary")
    rsi_strong_threshold: float = Field(default=60.0, description="RSI strong boundary")
    rsi_overbought_threshold: float = Field(default=70.0, description="RSI overbought boundary")

    # --- MACD ---
    macd_fast_period: int = Field(default=12, description="MACD fast EMA period")
    macd_slow_period: int = Field(default=26, description="MACD slow EMA period")
    macd_signal_period: int = Field(default=9, description="MACD signal line period")

    # --- ATR ---
    atr_period: int = Field(default=14, description="ATR lookback period")
    atr_high_threshold_pct: float = Field(
        default=1.5,
        description="ATR percentage threshold for HIGH volatility classification",
    )
    atr_extreme_threshold_pct: float = Field(
        default=3.0,
        description="ATR percentage threshold for EXTREME volatility classification",
    )
    atr_low_threshold_pct: float = Field(
        default=0.3,
        description="ATR percentage threshold for LOW volatility classification",
    )

    # --- Bollinger Bands ---
    bb_period: int = Field(default=20, description="Bollinger Bands SMA period")
    bb_std_dev: float = Field(default=2.0, description="Bollinger Bands standard deviation multiplier")

    # --- Volume ---
    volume_sma_period: int = Field(default=20, description="Volume SMA period")
    volume_high_threshold: float = Field(
        default=1.5,
        description="Relative volume threshold for HIGH classification",
    )
    volume_low_threshold: float = Field(
        default=0.5,
        description="Relative volume threshold for LOW classification",
    )

    # --- Price features ---
    price_lookback: int = Field(
        default=20,
        description="Number of candles for recent high/low/range calculation",
    )

    @model_validator(mode="after")
    def validate_periods(self) -> "TechnicalFeaturesSettings":
        """Validate that indicator periods are logically consistent."""
        errors: list[str] = []

        if self.ema_fast_period <= 0:
            errors.append("ema_fast_period must be > 0")
        if self.ema_medium_period <= 0:
            errors.append("ema_medium_period must be > 0")
        if self.ema_slow_period <= 0:
            errors.append("ema_slow_period must be > 0")
        if self.ema_fast_period >= self.ema_medium_period:
            errors.append("ema_fast_period must be < ema_medium_period")
        if self.ema_medium_period >= self.ema_slow_period:
            errors.append("ema_medium_period must be < ema_slow_period")

        if self.rsi_period <= 0:
            errors.append("rsi_period must be > 0")

        if self.macd_fast_period <= 0:
            errors.append("macd_fast_period must be > 0")
        if self.macd_slow_period <= 0:
            errors.append("macd_slow_period must be > 0")
        if self.macd_signal_period <= 0:
            errors.append("macd_signal_period must be > 0")
        if self.macd_fast_period >= self.macd_slow_period:
            errors.append("macd_fast_period must be < macd_slow_period")

        if self.atr_period <= 0:
            errors.append("atr_period must be > 0")
        if self.atr_extreme_threshold_pct <= self.atr_high_threshold_pct:
            errors.append("atr_extreme_threshold_pct must be > atr_high_threshold_pct")

        if self.bb_period <= 0:
            errors.append("bb_period must be > 0")
        if self.bb_std_dev <= 0:
            errors.append("bb_std_dev must be > 0")

        if self.volume_sma_period <= 0:
            errors.append("volume_sma_period must be > 0")

        if self.price_lookback <= 0:
            errors.append("price_lookback must be > 0")

        if errors:
            raise ValueError("; ".join(errors))

        return self


def get_technical_features_settings() -> TechnicalFeaturesSettings:
    """Get validated technical features settings (uncached for test isolation)."""
    return TechnicalFeaturesSettings()
