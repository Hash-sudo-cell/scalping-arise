"""
Scalping Arise — Backtesting Configuration

Centralized, validated configuration for the backtesting & forward testing engine.
All values are configurable via environment variables with the
SCALPING_ARISE_ prefix.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BacktestingSettings(BaseSettings):
    """Backtesting & forward testing engine configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Engine toggle ---
    backtesting_enabled: bool = Field(
        default=True,
        description="Enable the backtesting engine",
    )

    # --- Data defaults ---
    default_instrument: str = Field(default="XAU/USD")
    default_timeframe: str = Field(default="1h")
    default_candle_limit: int = Field(default=1000, ge=100, le=10000)

    # --- Simulation defaults ---
    default_fill_method: str = Field(default="next_bar_open")
    default_slippage_pips: float = Field(default=1.0, ge=0)
    default_spread_pips: float = Field(default=3.0, ge=0)

    # --- Account defaults ---
    default_initial_balance: float = Field(default=10000.0, gt=0)
    default_max_positions: int = Field(default=3, ge=1, le=50)
    default_max_daily_loss_pct: float = Field(default=3.0, gt=0, le=100)
    default_max_drawdown_pct: float = Field(default=10.0, gt=0, le=100)

    # --- Walk-forward defaults ---
    default_train_window: int = Field(default=1000, ge=100)
    default_test_window: int = Field(default=200, ge=10)
    default_step_size: int = Field(default=200, ge=10)
    max_walk_forward_folds: int = Field(default=20, ge=3, le=100)

    # --- Robustness defaults ---
    monte_carlo_simulations: int = Field(default=1000, ge=100, le=10000)
    bootstrap_samples: int = Field(default=1000, ge=100, le=10000)
    confidence_level: float = Field(default=0.95, ge=0.90, le=0.99)

    # --- Performance ---
    max_concurrent_backtests: int = Field(default=1, ge=1, le=5)
    backtest_timeout_seconds: int = Field(default=300, ge=30, le=3600)

    # --- Determinism ---
    enforce_determinism: bool = Field(
        default=True,
        description="Enforce seeded RNG for reproducible results",
    )
    default_random_seed: int = Field(default=42, ge=0)

    # --- Look-ahead protection ---
    strict_lookahead: bool = Field(default=True)
    max_lookahead_seconds: int = Field(default=0, ge=0)

    # --- Limits ---
    max_trades_per_backtest: int = Field(default=10000, ge=1, le=100000)
    max_results_stored: int = Field(default=100, ge=10, le=1000)
    result_ttl_seconds: int = Field(default=86400, ge=300, description="24h default")

    # --- Paper trading ---
    paper_trading_check_interval: int = Field(default=60, ge=10, le=3600)
    paper_trading_max_duration: int = Field(default=86400, ge=60, le=604800)

    @property
    def is_enabled(self) -> bool:
        return self.backtesting_enabled


def get_backtesting_settings() -> BacktestingSettings:
    """Get validated backtesting settings (uncached for test isolation)."""
    return BacktestingSettings()
