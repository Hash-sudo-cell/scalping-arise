"""
Scalping Arise — Trade Planning Configuration

Centralized, validated configuration for the trade planning & risk engine.
All values are configurable via environment variables with the
SCALPING_ARISE_ prefix.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradePlanningSettings(BaseSettings):
    """Trade planning & risk engine configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Trade planning engine ---
    trade_planning_enabled: bool = Field(
        default=True,
        description="Enable the trade planning & risk engine",
    )

    # --- Signal eligibility ---
    min_signal_confidence_0_100: int = Field(
        default=55,
        ge=0, le=100,
        description="Minimum signal confidence (0-100) for trade plan eligibility",
    )
    min_signal_quality_0_100: int = Field(
        default=60,
        ge=0, le=100,
        description="Minimum signal quality (0-100) for trade plan eligibility",
    )
    require_signal_active: bool = Field(
        default=True,
        description="Require signal state to be ACTIVE for plan eligibility",
    )

    # --- Entry planning ---
    entry_ready_max_spread_pips: float = Field(
        default=5.0,
        ge=0,
        description="Maximum spread in pips for ENTRY_READY status",
    )
    entry_limit_distance_max_pips: float = Field(
        default=20.0,
        ge=0,
        description="Maximum distance in pips for limit entry",
    )
    entry_timeout_seconds: int = Field(
        default=120,
        ge=0,
        description="Seconds to wait for entry conditions before EXPIRED",
    )

    # --- Stop-loss ---
    sl_atr_multiplier: float = Field(
        default=1.5,
        gt=0,
        description="ATR multiplier for ATR-based stop-loss placement",
    )
    sl_min_distance_pips: float = Field(
        default=5.0,
        ge=0,
        description="Minimum SL distance in pips (enforced for all SL types)",
    )
    sl_max_distance_pips: float = Field(
        default=200.0,
        ge=0,
        description="Maximum SL distance in pips",
    )
    sl_invalidation_buffer_ticks: int = Field(
        default=3,
        ge=0,
        description="Buffer ticks beyond invalidation level for SL placement",
    )

    # --- Take-profit ---
    tp1_risk_reward_ratio: float = Field(
        default=1.5,
        gt=0,
        description="Minimum R:R ratio for TP1 target",
    )
    tp2_risk_reward_ratio: float = Field(
        default=2.5,
        gt=0,
        description="Minimum R:R ratio for TP2 target",
    )
    tp1_partial_close_pct: float = Field(
        default=0.5,
        ge=0, le=1.0,
        description="Fraction of position to close at TP1",
    )
    tp_min_distance_pips: float = Field(
        default=5.0,
        ge=0,
        description="Minimum TP distance in pips",
    )
    tp_max_distance_pips: float = Field(
        default=500.0,
        ge=0,
        description="Maximum TP distance in pips",
    )

    # --- Position sizing & risk ---
    account_balance: float = Field(
        default=10000.0,
        gt=0,
        description="Default account balance for position sizing",
    )
    risk_per_trade_pct: float = Field(
        default=1.0,
        gt=0, le=100,
        description="Maximum risk per trade as % of account balance",
    )
    max_open_positions: int = Field(
        default=3,
        ge=1, le=50,
        description="Maximum concurrent open positions",
    )
    max_portfolio_risk_pct: float = Field(
        default=5.0,
        gt=0, le=100,
        description="Maximum total portfolio risk as % of balance",
    )

    # --- Risk guardrails ---
    max_daily_loss_pct: float = Field(
        default=3.0,
        gt=0, le=100,
        description="Maximum daily loss as % of balance",
    )
    max_drawdown_pct: float = Field(
        default=10.0,
        gt=0, le=100,
        description="Maximum drawdown as % of balance from peak",
    )
    daily_loss_reset_hour_utc: int = Field(
        default=0,
        ge=0, le=23,
        description="UTC hour at which daily loss counter resets",
    )

    # --- Risk-Reward ---
    min_risk_reward_ratio: float = Field(
        default=1.0,
        gt=0,
        description="Minimum R:R ratio for any plan to be VALIDATED",
    )

    # --- Cost validation ---
    max_spread_cost_pct_of_risk: float = Field(
        default=25.0,
        ge=0,
        description="Maximum spread cost as % of risk amount",
    )
    typical_commission_per_lot: float = Field(
        default=0.0,
        ge=0,
        description="Typical commission per lot in account currency",
    )

    # --- Freshness ---
    freshness_max_age_seconds: int = Field(
        default=60,
        ge=0,
        description="Maximum age in seconds for market data to be considered fresh",
    )
    price_max_age_seconds: int = Field(
        default=30,
        ge=0,
        description="Maximum age in seconds for price data",
    )

    # --- Volatility ---
    volatility_extreme_threshold_pct: float = Field(
        default=2.0,
        gt=0,
        description="ATR percentage above which volatility is EXTREME",
    )
    volatility_high_threshold_pct: float = Field(
        default=1.0,
        gt=0,
        description="ATR percentage above which volatility is HIGH",
    )
    volatility_expand_sl_multiplier: float = Field(
        default=2.0,
        gt=0,
        description="ATR multiplier for SL when volatility is HIGH",
    )
    volatility_contract_sl_multiplier: float = Field(
        default=1.0,
        gt=0,
        description="ATR multiplier for SL when volatility is LOW",
    )

    # --- Plan lifecycle ---
    plan_ttl_seconds: int = Field(
        default=300,
        ge=0, le=3600,
        description="Plan time-to-live in seconds before auto-expiration",
    )
    plan_history_max_size: int = Field(
        default=100,
        ge=10, le=1000,
        description="Maximum number of plan records retained in history",
    )

    @property
    def is_enabled(self) -> bool:
        return self.trade_planning_enabled


def get_trade_planning_settings() -> TradePlanningSettings:
    """Get validated trade planning settings (uncached for test isolation)."""
    return TradePlanningSettings()
