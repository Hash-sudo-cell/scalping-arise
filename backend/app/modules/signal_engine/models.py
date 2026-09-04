"""
Scalping Arise — Signal Engine Models

Strongly typed models for signal candidates, multi-timeframe confirmation,
evidence aggregation, conflict detection, confidence scoring, and
signal qualification. Consumes outputs from Phases 3–5.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums — type-safe signal states
# ---------------------------------------------------------------------------

class SignalDirection(str, Enum):
    """Directional bias of a signal candidate."""

    LONG = "long"
    SHORT = "short"
    NONE = "none"


class SignalStatus(str, Enum):
    """Final status of a signal evaluation."""

    QUALIFIED = "qualified"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class ConflictType(str, Enum):
    """Type of directional conflict between candidates."""

    STRATEGY_DIVERGENCE = "strategy_divergence"
    TIMEFRAME_MISALIGNMENT = "timeframe_misalignment"
    REGIME_CONTRADICTION = "regime_contradiction"
    MOMENTUM_DIVERGENCE = "momentum_divergence"


class ConfirmationLevel(str, Enum):
    """Strength of multi-timeframe confirmation."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


# ---------------------------------------------------------------------------
# Signal Candidate
# ---------------------------------------------------------------------------

class SignalCandidate(BaseModel):
    """A directional signal candidate produced from a qualified strategy."""

    strategy_id: str
    strategy_version: str
    strategy_name: str
    direction: SignalDirection
    quality_score_normalized: float = Field(
        ge=0.0, le=1.0,
        description="Normalized quality score from strategy evaluation (0.0–1.0)",
    )
    quality_score_raw: int = Field(ge=0, description="Raw quality score points")
    quality_score_max: int = Field(ge=0, description="Maximum possible quality points")
    condition_pass_rate: float = Field(
        ge=0.0, le=1.0,
        description="Fraction of required conditions that passed (0.0–1.0)",
    )
    invalidation_triggered: bool = Field(
        default=False,
        description="Whether any invalidation rule was triggered",
    )
    market_regime: Optional[str] = None
    evidence: list[str] = Field(
        default_factory=list,
        description="Supporting evidence strings from the strategy evaluation",
    )


# ---------------------------------------------------------------------------
# Multi-Timeframe Confirmation
# ---------------------------------------------------------------------------

class TimeframeConfirmation(BaseModel):
    """Confirmation result for a single timeframe."""

    timeframe: str
    aligned: bool = Field(
        description="Whether this timeframe's features align with the candidate direction",
    )
    confirmation_level: ConfirmationLevel
    supporting_evidence: list[str] = Field(default_factory=list)
    ema_alignment: Optional[str] = Field(
        default=None,
        description="EMA alignment state on this timeframe",
    )
    trend_state: Optional[str] = Field(
        default=None,
        description="Trend state on this timeframe (from analysis)",
    )


class MTFConfirmationResult(BaseModel):
    """Aggregated multi-timeframe confirmation across all timeframes."""

    confirmed: bool = Field(
        description="Whether sufficient timeframes confirm the candidate direction",
    )
    confirmation_level: ConfirmationLevel
    aligned_count: int = Field(ge=0, description="Number of aligned timeframes")
    total_count: int = Field(ge=0, description="Total timeframes evaluated")
    confirmations: list[TimeframeConfirmation] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class EvidenceItem(BaseModel):
    """A single piece of supporting or opposing evidence."""

    source: str = Field(
        description="Origin of this evidence (e.g. 'strategy:trend_continuation', 'mtf:15m')",
    )
    component: str = Field(
        description="Evidence category (e.g. 'trend', 'momentum', 'structure', 'liquidity')",
    )
    direction: SignalDirection
    strength: float = Field(
        ge=0.0, le=1.0,
        description="Relative strength of this evidence (0.0 = weak, 1.0 = strong)",
    )
    description: str = Field(default="", description="Human-readable evidence description")


# ---------------------------------------------------------------------------
# Conflict Detection & Resolution
# ---------------------------------------------------------------------------

class DirectionalConflict(BaseModel):
    """A detected conflict between strategy candidates or timeframes."""

    conflict_type: ConflictType
    description: str
    involved_strategies: list[str] = Field(default_factory=list)
    severity: float = Field(
        ge=0.0, le=1.0,
        description="Conflict severity (0.0 = minor, 1.0 = critical)",
    )


class ConflictResolution(BaseModel):
    """Result of resolving directional conflicts."""

    final_direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    conflicts: list[DirectionalConflict] = Field(default_factory=list)
    resolution_method: str = Field(
        default="",
        description="How the conflict was resolved (e.g. 'majority_vote', 'quality_weighted', 'no_conflict')",
    )
    dropped_candidates: list[str] = Field(
        default_factory=list,
        description="Strategy IDs dropped due to conflict resolution",
    )


# ---------------------------------------------------------------------------
# Confidence Scoring
# ---------------------------------------------------------------------------

class ConfidenceBreakdown(BaseModel):
    """Breakdown of a confidence score by factor."""

    factor: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    contribution: float = Field(
        ge=0.0, le=1.0,
        description="score * weight",
    )
    description: str = Field(default="")


class ConfidenceScore(BaseModel):
    """Composite confidence score for a signal evaluation."""

    overall: float = Field(ge=0.0, le=1.0, description="Overall confidence (0.0–1.0)")
    strategy_alignment: float = Field(
        ge=0.0, le=1.0,
        description="How aligned the strategies are on the direction",
    )
    mtf_confirmation: float = Field(
        ge=0.0, le=1.0,
        description="Multi-timeframe confirmation strength",
    )
    evidence_strength: float = Field(
        ge=0.0, le=1.0,
        description="Aggregate strength of supporting evidence",
    )
    regime_consistency: float = Field(
        ge=0.0, le=1.0,
        description="Whether regime context supports the signal",
    )
    breakdown: list[ConfidenceBreakdown] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Signal Evaluation Result (top-level output)
# ---------------------------------------------------------------------------

class SignalEvaluationResult(BaseModel):
    """
    Complete output of a signal evaluation.

    The signal engine consumes outputs from Phases 3–5 and produces
    a structured result indicating whether a qualified directional
    signal candidate exists.
    """

    # Identification
    evaluation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique evaluation identifier",
    )
    evaluation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    # Instrument
    instrument: str

    # Final status
    status: SignalStatus
    direction: SignalDirection = SignalDirection.NONE

    # Confidence
    confidence: Optional[ConfidenceScore] = None

    # Candidates that were evaluated
    candidates: list[SignalCandidate] = Field(default_factory=list)

    # Multi-timeframe confirmation
    mtf_confirmation: Optional[MTFConfirmationResult] = None

    # Conflicts detected
    conflicts: list[DirectionalConflict] = Field(default_factory=list)

    # Conflict resolution
    resolution: Optional[ConflictResolution] = None

    # All evidence collected
    evidence: list[EvidenceItem] = Field(default_factory=list)

    # Human-readable summary
    reason: str = ""

    # Source types used
    source_types_used: list[str] = Field(default_factory=list)

    # Timeframes evaluated
    timeframes_evaluated: list[str] = Field(default_factory=list)
