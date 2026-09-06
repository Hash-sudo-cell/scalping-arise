"""
Scalping Arise — Decision Engine Configuration

Centralized settings for the Phase 10 decision engine.
All settings use the SCALPING_ARISE_ environment prefix.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FailPolicy(str, Enum):
    """Behavior when upstream modules are unavailable."""

    FAIL_OPEN = "fail_open"
    FAIL_CLOSED = "fail_closed"


class DecisionEngineSettings(BaseSettings):
    """Configuration for the Phase 10 decision engine."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCALPING_ARISE_DECISION_",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    enabled: bool = Field(
        default=True,
        description="Master switch for the decision engine",
    )

    decision_ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Time-to-live for a decision before it expires (seconds)",
    )

    # ------------------------------------------------------------------
    # Gate thresholds
    # ------------------------------------------------------------------

    min_signal_confidence: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Minimum signal confidence (0-100) to pass the signal quality gate",
    )

    min_signal_quality: int = Field(
        default=40,
        ge=0,
        le=100,
        description="Minimum signal quality score (0-100) to pass the quality gate",
    )

    min_risk_reward: float = Field(
        default=1.5,
        ge=0.5,
        le=10.0,
        description="Minimum risk:reward ratio for plan validity gate",
    )

    max_plan_age_seconds: int = Field(
        default=120,
        ge=10,
        le=600,
        description="Maximum age of a trade plan before it's considered stale (seconds)",
    )

    # ------------------------------------------------------------------
    # Fail-safe
    # ------------------------------------------------------------------

    fail_policy: FailPolicy = Field(
        default=FailPolicy.FAIL_CLOSED,
        description="Default behavior when upstream data is unavailable: fail_open or fail_closed",
    )

    # Per-gate fail policies (override global)
    event_risk_fail_policy: FailPolicy = Field(
        default=FailPolicy.FAIL_CLOSED,
        description="Fail policy for the event risk gate specifically",
    )

    strategy_state_fail_policy: FailPolicy = Field(
        default=FailPolicy.FAIL_CLOSED,
        description="Fail policy for the strategy performance state gate",
    )

    # ------------------------------------------------------------------
    # Emergency
    # ------------------------------------------------------------------

    emergency_disable: bool = Field(
        default=False,
        description="Emergency kill switch — when True, all decisions are BLOCKED",
    )

    # ------------------------------------------------------------------
    # Audit & Retention
    # ------------------------------------------------------------------

    audit_max_entries: int = Field(
        default=10000,
        ge=100,
        le=1000000,
        description="Maximum audit trail entries (ring buffer)",
    )

    retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Number of days to retain decision history",
    )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    idempotency_cache_size: int = Field(
        default=5000,
        ge=100,
        le=100000,
        description="Maximum entries in the idempotency cache",
    )

    idempotency_ttl_seconds: int = Field(
        default=600,
        ge=60,
        le=3600,
        description="Time-to-live for idempotency cache entries (seconds)",
    )

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    monitoring_enabled: bool = Field(
        default=True,
        description="Enable monitoring counters",
    )

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    readiness_check_timeout_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=30.0,
        description="Timeout for individual module health checks during readiness aggregation",
    )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    decision_history_max_size: int = Field(
        default=1000,
        ge=10,
        le=50000,
        description="Maximum decisions kept in memory",
    )

    active_decisions_max_size: int = Field(
        default=100,
        ge=5,
        le=5000,
        description="Maximum active (non-terminal) decisions tracked",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("fail_policy", "event_risk_fail_policy", "strategy_state_fail_policy", mode="before")
    @classmethod
    def normalize_fail_policy(cls, v: Any) -> FailPolicy:
        if isinstance(v, str):
            v = v.lower().strip()
        try:
            return FailPolicy(v)
        except ValueError:
            return FailPolicy.FAIL_CLOSED


@lru_cache(maxsize=1)
def get_decision_engine_settings() -> DecisionEngineSettings:
    """Cached factory for decision engine settings."""
    return DecisionEngineSettings()
