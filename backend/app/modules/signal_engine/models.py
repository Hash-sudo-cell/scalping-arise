"""
Scalping Arise — Signal Engine Models

Strongly typed models for signal candidates, multi-timeframe confirmation,
evidence aggregation, conflict detection, confidence scoring, signal
qualification, state machine lifecycle, deduplication, expiration,
invalidation, priority ranking, and structured decisions.

Consumes outputs from Phases 3–5. Produces BUY/SELL/NO_TRADE decisions
with independent confidence (0–100) and quality (0–100) scores.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ===========================================================================
# Enums — type-safe signal states (backward-compatible + new Phase 6)
# ===========================================================================

class SignalDirection(str, Enum):
    """Directional bias of a signal candidate."""

    LONG = "long"
    SHORT = "short"
    NONE = "none"


class SignalStatus(str, Enum):
    """Final status of a signal evaluation (legacy — maps to state machine)."""

    QUALIFIED = "qualified"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class SignalState(str, Enum):
    """
    Full lifecycle state machine for a signal.

    Transitions:
        NO_SIGNAL → CANDIDATE
        CANDIDATE → QUALIFIED | REJECTED | NO_SIGNAL
        QUALIFIED → CONFIRMED | REJECTED
        CONFIRMED → ACTIVE | INVALIDATED
        ACTIVE → EXPIRED | INVALIDATED
        Any → EXPIRED (TTL elapsed)
        Any → INVALIDATED (market condition change)
    """

    NO_SIGNAL = "no_signal"
    CANDIDATE = "candidate"
    QUALIFIED = "qualified"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class DecisionType(str, Enum):
    """Final trading decision output."""

    BUY = "buy"
    SELL = "sell"
    NO_TRADE = "no_trade"


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


class DecisionReasonCode(str, Enum):
    """Typed reason codes for structured decision explanations."""

    STRONG_CONSENSUS = "strong_consensus"
    QUALITY_WEIGHTED_WINNER = "quality_weighted_winner"
    MTF_CONFIRMED = "mtf_confirmed"
    EVIDENCE_SUPPORTED = "evidence_supported"
    REGIME_ALIGNED = "regime_aligned"
    LOW_CONFIDENCE = "low_confidence"
    CONFLICT_UNRESOLVED = "conflict_unresolved"
    NO_CANDIDATES = "no_candidates"
    DIRECTION_NONE = "direction_none"
    MTF_NOT_CONFIRMED = "mtf_not_confirmed"
    QUALITY_BELOW_THRESHOLD = "quality_below_threshold"
    DEDUPLICATE_BLOCKED = "duplicate_blocked"
    TTL_EXPIRED = "ttl_expired"
    INVALIDATED_BY_MARKET = "invalidated_by_market"
    INSUFFICIENT_DATA = "insufficient_data"
    STRATEGY_INCOMPATIBLE = "strategy_incompatible"
    REGIME_INCOMPATIBLE = "regime_incompatible"


# ===========================================================================
# Signal Candidate
# ===========================================================================

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


# ===========================================================================
# Multi-Timeframe Confirmation
# ===========================================================================

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


# ===========================================================================
# Evidence
# ===========================================================================

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


# ===========================================================================
# Conflict Detection & Resolution
# ===========================================================================

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


# ===========================================================================
# Confidence Scoring
# ===========================================================================

class ConfidenceBreakdown(BaseModel):
    """Breakdown of a confidence score by factor."""

    factor: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    contribution: float = Field(
        ge=0.0,
        description="score * weight (scaled to component max — may exceed 1.0 for quality breakdowns)",
    )
    description: str = Field(default="")


class ConfidenceScore(BaseModel):
    """
    Composite confidence score for a signal evaluation.

    Provides both legacy 0.0–1.0 float scale and Phase 6 0–100 integer scale.
    The integer scale is the primary output; float fields remain for backward
    compatibility with existing consumers.
    """

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

    # Phase 6: 0–100 integer scale (derived from overall)
    confidence_0_100: int = Field(
        ge=0, le=100,
        description="Confidence score on 0–100 integer scale (primary Phase 6 output)",
        default=0,
    )

    @field_validator("confidence_0_100", mode="before")
    @classmethod
    def compute_confidence_0_100(cls, v: int, info) -> int:  # noqa: ANN001
        """Auto-compute from overall if not explicitly set."""
        if v == 0 and "overall" in info.data:
            return round(info.data["overall"] * 100)
        return v


# ===========================================================================
# Signal Quality Score (Phase 6 — independent from confidence)
# ===========================================================================

class SignalQuality(BaseModel):
    """
    Independent quality score for a signal (0–100 integer scale).

    Quality measures the structural strength of the signal setup:
    condition pass rates, evidence depth, strategy alignment quality.
    Confidence measures the certainty of the directional bias.
    """

    score: int = Field(
        ge=0, le=100,
        description="Quality score (0–100)",
    )
    condition_pass_rate: float = Field(
        ge=0.0, le=1.0,
        description="Weighted condition pass rate across contributing strategies",
    )
    evidence_depth: int = Field(
        ge=0,
        description="Number of independent evidence sources supporting the signal",
    )
    strategy_alignment: float = Field(
        ge=0.0, le=1.0,
        description="Fraction of contributing strategies aligned on direction",
    )
    breakdown: list[ConfidenceBreakdown] = Field(default_factory=list)

    @property
    def normalized(self) -> float:
        """Return quality as 0.0–1.0 float."""
        return self.score / 100.0


# ===========================================================================
# Structured Decision Reasons (Phase 6)
# ===========================================================================

class DecisionReason(BaseModel):
    """
    Structured reason for a trading decision.

    Replaces the free-text `reason` string with typed reason codes
    plus optional human-readable detail.
    """

    code: DecisionReasonCode
    detail: str = ""
    contributing_factors: list[str] = Field(default_factory=list)


# ===========================================================================
# Signal Priority / Ranking (Phase 6)
# ===========================================================================

class SignalPriority(BaseModel):
    """
    Composite priority score for ranking active signals.

    Higher priority = more actionable signal. Combines confidence,
    quality, evidence strength, and recency into a single score.
    """

    priority_score: float = Field(
        ge=0.0, le=100.0,
        description="Composite priority score (0–100)",
    )
    confidence_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    quality_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    evidence_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    recency_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    rank: int = Field(default=0, ge=0, description="1-based rank among active signals")


# ===========================================================================
# Signal State Machine Record (Phase 6)
# ===========================================================================

class StateTransition(BaseModel):
    """A single state transition in the signal lifecycle."""

    from_state: SignalState
    to_state: SignalState
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""


class SignalRecord(BaseModel):
    """
    Full lifecycle record for a single signal instance.

    Tracks the signal from NO_SIGNAL through ACTIVE/EXPIRED/INVALIDATED,
    with timestamps for each transition, dedup key, TTL, and priority.
    """

    signal_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique signal identifier",
    )
    instrument: str
    decision: DecisionType = DecisionType.NO_TRADE
    state: SignalState = SignalState.NO_SIGNAL
    direction: SignalDirection = SignalDirection.NONE

    # Scores
    confidence: Optional[ConfidenceScore] = None
    quality: Optional[SignalQuality] = None
    priority: Optional[SignalPriority] = None

    # Decision reasons
    reasons: list[DecisionReason] = Field(default_factory=list)

    # Candidates and context
    candidates: list[SignalCandidate] = Field(default_factory=list)
    mtf_confirmation: Optional[MTFConfirmationResult] = None
    conflicts: list[DirectionalConflict] = Field(default_factory=list)
    resolution: Optional[ConflictResolution] = None
    evidence: list[EvidenceItem] = Field(default_factory=list)

    # Dedup
    dedup_key: str = Field(
        default="",
        description="Hash key for deduplication (instrument+direction+strategy_ids+window)",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    qualified_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    invalidated_at: Optional[datetime] = None
    ttl_seconds: int = Field(default=300, ge=0, description="Signal time-to-live in seconds")

    # State history
    state_history: list[StateTransition] = Field(default_factory=list)

    # Source metadata
    source_types_used: list[str] = Field(default_factory=list)
    timeframes_evaluated: list[str] = Field(default_factory=list)

    # Human-readable
    reason: str = ""

    @property
    def is_active(self) -> bool:
        """Whether this signal is in an actionable state."""
        return self.state in (SignalState.ACTIVE, SignalState.CONFIRMED)

    @property
    def is_terminal(self) -> bool:
        """Whether this signal has reached a terminal state."""
        return self.state in (SignalState.EXPIRED, SignalState.INVALIDATED, SignalState.NO_SIGNAL)

    @property
    def age_seconds(self) -> float:
        """Seconds since signal was created."""
        now = datetime.now(timezone.utc)
        return (now - self.created_at).total_seconds()

    @property
    def remaining_ttl(self) -> float:
        """Seconds remaining before signal expires."""
        return max(0.0, self.ttl_seconds - self.age_seconds)


# ===========================================================================
# Deduplication Key (Phase 6)
# ===========================================================================

class DeduplicationEntry(BaseModel):
    """A deduplication record for preventing duplicate signals."""

    dedup_key: str
    signal_id: str
    instrument: str
    direction: SignalDirection
    decision: DecisionType
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ===========================================================================
# Signal Evaluation Result (top-level output — backward-compatible)
# ===========================================================================

class SignalEvaluationResult(BaseModel):
    """
    Complete output of a signal evaluation.

    The signal engine consumes outputs from Phases 3–5 and produces
    a structured result indicating whether a qualified directional
    signal candidate exists. Includes Phase 6 decision, confidence,
    quality, priority, and state information.
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

    # Final status (legacy)
    status: SignalStatus
    direction: SignalDirection = SignalDirection.NONE

    # Phase 6: Structured decision
    decision: DecisionType = DecisionType.NO_TRADE
    decision_reasons: list[DecisionReason] = Field(default_factory=list)

    # Phase 6: Signal record (full lifecycle)
    signal_record: Optional[SignalRecord] = None

    # Confidence
    confidence: Optional[ConfidenceScore] = None

    # Phase 6: Independent quality score
    quality: Optional[SignalQuality] = None

    # Phase 6: Priority ranking
    priority: Optional[SignalPriority] = None

    # Phase 6: Signal state
    signal_state: SignalState = SignalState.NO_SIGNAL

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


# ===========================================================================
# Convenience: direction ↔ decision mapping
# ===========================================================================

_DIRECTION_TO_DECISION: dict[SignalDirection, DecisionType] = {
    SignalDirection.LONG: DecisionType.BUY,
    SignalDirection.SHORT: DecisionType.SELL,
    SignalDirection.NONE: DecisionType.NO_TRADE,
}

_DECISION_TO_DIRECTION: dict[DecisionType, SignalDirection] = {
    DecisionType.BUY: SignalDirection.LONG,
    DecisionType.SELL: SignalDirection.SHORT,
    DecisionType.NO_TRADE: SignalDirection.NONE,
}


def direction_to_decision(direction: SignalDirection) -> DecisionType:
    """Map a SignalDirection to a DecisionType."""
    return _DIRECTION_TO_DECISION.get(direction, DecisionType.NO_TRADE)


def decision_to_direction(decision: DecisionType) -> SignalDirection:
    """Map a DecisionType to a SignalDirection."""
    return _DECISION_TO_DIRECTION.get(decision, SignalDirection.NONE)


def status_to_state(status: SignalStatus) -> SignalState:
    """Map a legacy SignalStatus to a SignalState."""
    _MAP = {
        SignalStatus.QUALIFIED: SignalState.QUALIFIED,
        SignalStatus.REJECTED: SignalState.NO_SIGNAL,
        SignalStatus.CONFLICT: SignalState.CANDIDATE,
        SignalStatus.INSUFFICIENT_CONTEXT: SignalState.NO_SIGNAL,
    }
    return _MAP.get(status, SignalState.NO_SIGNAL)
