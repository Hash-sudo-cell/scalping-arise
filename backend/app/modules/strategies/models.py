"""
Scalping Arise — Strategy Engine Models

Strongly typed models for strategy definitions, evaluation results,
conditions, eligibility, quality scoring, and evaluation snapshots.

Every model is deterministic, version-aware, and carries full
traceability for explainability.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums — type-safe strategy evaluation states
# ---------------------------------------------------------------------------

class StrategyDirection(str, Enum):
    """Directional context of a strategy evaluation."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    NONE = "none"


class StrategyEvaluationStatus(str, Enum):
    """Final status of a strategy evaluation."""

    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_QUALIFIED = "not_qualified"
    QUALIFIED = "qualified"
    INVALIDATED = "invalidated"
    UNAVAILABLE = "unavailable"


class ConditionCriticality(str, Enum):
    """How important a condition is for strategy qualification."""

    CRITICAL = "critical"
    REQUIRED = "required"
    OPTIONAL = "optional"


class ConditionStatus(str, Enum):
    """Result status of a single condition evaluation."""

    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class SourceCompatibilityPolicy(str, Enum):
    """Strategy policy for source data compatibility."""

    SPOT_ONLY = "spot_only"
    SPOT_PREFERRED = "spot_preferred"
    FUTURES_PROXY_ALLOWED = "futures_proxy_allowed"


class EligibilityCheckStatus(str, Enum):
    """Status of a single eligibility check."""

    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class TimeframeRole(str, Enum):
    """Role a timeframe plays in a strategy."""

    REQUIRED_CONTEXT = "required_context"
    REQUIRED_SETUP = "required_setup"
    OPTIONAL_CONFIRMATION = "optional_confirmation"


# ---------------------------------------------------------------------------
# Strategy Definition — explicit, structured strategy config
# ---------------------------------------------------------------------------

class TimeframeRequirement(BaseModel):
    """Defines how a timeframe is used by a strategy."""

    timeframe: str
    role: TimeframeRole


class ConditionDefinition(BaseModel):
    """A single condition within a strategy."""

    condition_id: str
    condition_name: str
    description: str
    criticality: ConditionCriticality


class InvalidationRule(BaseModel):
    """A rule that can invalidate a strategy setup."""

    rule_id: str
    rule_name: str
    description: str


class QualityWeight(BaseModel):
    """Weight for a quality scoring category."""

    category: str
    max_points: int = Field(ge=0, description="Maximum points for this category")
    weight: float = Field(ge=0.0, le=1.0, description="Normalized weight")


class StrategyDefinition(BaseModel):
    """
    Explicit, structured strategy definition.

    Each strategy is self-contained with its own version, requirements,
    conditions, invalidation rules, and quality scoring configuration.
    """

    strategy_id: str
    strategy_version: str
    strategy_name: str
    description: str
    enabled: bool = True

    # Regime compatibility
    applicable_market_regimes: list[str] = Field(
        default_factory=list,
        description="Market regimes where this strategy can apply",
    )

    # Timeframe requirements
    required_timeframes: list[TimeframeRequirement] = Field(
        default_factory=list,
        description="Timeframes required and their roles",
    )

    # Source compatibility
    source_compatibility_policy: SourceCompatibilityPolicy = Field(
        default=SourceCompatibilityPolicy.FUTURES_PROXY_ALLOWED,
        description="Policy for source data compatibility",
    )

    # Condition definitions (describes expected conditions, not the logic)
    required_conditions: list[ConditionDefinition] = Field(
        default_factory=list,
        description="Conditions that must pass for qualification",
    )

    optional_conditions: list[ConditionDefinition] = Field(
        default_factory=list,
        description="Conditions that contribute to quality but don't block qualification",
    )

    # Invalidation rules
    invalidation_rules: list[InvalidationRule] = Field(
        default_factory=list,
        description="Rules that can invalidate a strategy setup",
    )

    # Quality scoring
    quality_weights: list[QualityWeight] = Field(
        default_factory=list,
        description="Scoring weights for quality assessment",
    )
    scoring_model_version: str = Field(
        default="1.0",
        description="Version of the scoring model",
    )


# ---------------------------------------------------------------------------
# Eligibility Check
# ---------------------------------------------------------------------------

class EligibilityCheck(BaseModel):
    """Result of a single eligibility gate check."""

    check_name: str
    expected_state: str
    actual_state: str
    status: EligibilityCheckStatus
    reason: str


class EligibilityResult(BaseModel):
    """Aggregated eligibility gate result."""

    eligible: bool
    checks: list[EligibilityCheck] = Field(default_factory=list)
    blocked_by: Optional[str] = Field(
        default=None,
        description="Name of the check that blocked eligibility, if any",
    )


# ---------------------------------------------------------------------------
# Condition Evaluation Result
# ---------------------------------------------------------------------------

class ConditionResult(BaseModel):
    """Result of evaluating a single strategy condition."""

    condition_id: str
    condition_name: str
    description: str
    criticality: ConditionCriticality
    expected_value: str
    actual_value: str
    status: ConditionStatus
    reason: str
    evidence: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Invalidation Result
# ---------------------------------------------------------------------------

class InvalidationResult(BaseModel):
    """Result of evaluating invalidation rules."""

    rule_id: str
    rule_name: str
    description: str
    triggered: bool
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Quality Score
# ---------------------------------------------------------------------------

class QualityScoreBreakdown(BaseModel):
    """Breakdown of a quality score by category."""

    category: str
    points_awarded: int = Field(ge=0)
    max_points: int = Field(ge=0)
    reason: str = ""


class QualityScore(BaseModel):
    """Strategy quality assessment."""

    score: int = Field(ge=0, description="Total quality score")
    max_score: int = Field(ge=0, description="Maximum possible score")
    scoring_model_version: str
    breakdown: list[QualityScoreBreakdown] = Field(default_factory=list)
    normalized_score: float = Field(
        ge=0.0, le=1.0,
        description="Score as percentage of maximum",
    )


# ---------------------------------------------------------------------------
# Timeframe Context for Evaluation
# ---------------------------------------------------------------------------

class TimeframeContext(BaseModel):
    """Source metadata for a single timeframe's data."""

    timeframe: str
    source_type: str
    provider: str
    provider_instrument: str
    candle_count: int


# ---------------------------------------------------------------------------
# Strategy Evaluation Result
# ---------------------------------------------------------------------------

class StrategyEvaluationResult(BaseModel):
    """
    Complete output of a strategy evaluation.

    Preserves full traceability: definitions, eligibility, conditions,
    invalidation, quality, and final status.
    """

    # Identification
    evaluation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique evaluation identifier",
    )
    evaluation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    # Strategy identity
    strategy_id: str
    strategy_version: str
    strategy_name: str

    # Instrument
    instrument: str

    # Timeframes used
    timeframe_contexts: list[TimeframeContext] = Field(default_factory=list)

    # Source metadata (aggregated)
    source_types_used: list[str] = Field(default_factory=list)

    # Market regime at evaluation time
    market_regime: Optional[str] = None

    # Market structure context summary
    market_structure_summary: Optional[str] = None

    # Eligibility
    eligibility: Optional[EligibilityResult] = None

    # Condition results
    condition_results: list[ConditionResult] = Field(default_factory=list)

    # Invalidation results
    invalidation_results: list[InvalidationResult] = Field(default_factory=list)

    # Quality score
    quality_score: Optional[QualityScore] = None

    # Final status
    status: StrategyEvaluationStatus
    direction: StrategyDirection = StrategyDirection.NONE

    # Human-readable summary
    reason: str = ""


# ---------------------------------------------------------------------------
# Strategy Capability (for API responses)
# ---------------------------------------------------------------------------

class StrategyCapability(BaseModel):
    """Strategy capability summary for API responses."""

    strategy_id: str
    strategy_version: str
    strategy_name: str
    enabled: bool
    applicable_market_regimes: list[str]
    required_timeframes: list[str]
    source_compatibility_policy: str
    description: str
