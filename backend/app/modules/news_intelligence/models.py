"""
Scalping Arise — News, Event & Performance Intelligence Models

Strongly typed models for event normalization, impact classification,
relevance scoring, event risk filtering, strategy performance tracking,
strategy state management, and unified intelligence decisions.

Phase 8 consumes Phase 6 signals and produces an intelligence decision
(ALLOW / RESTRICT / BLOCK) that Phase 7 consumes before trade planning.

Phase 8 plans nothing — it only provides intelligence context.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ===========================================================================
# Enums — type-safe intelligence states
# ===========================================================================

class EventImpact(str, Enum):
    """Impact level of an external event."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class EventRelevance(str, Enum):
    """Whether an event is relevant to the traded instrument."""

    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    UNKNOWN = "unknown"


class EventDecision(str, Enum):
    """Decision produced by the event risk filter."""

    ALLOW = "allow"
    RESTRICT = "restrict"
    BLOCK = "block"


class StrategyPerformanceState(str, Enum):
    """Operational state of a strategy based on performance."""

    ACTIVE = "active"
    MONITORED = "monitored"
    RESTRICTED = "restricted"
    DISABLED = "disabled"


class OverallDecision(str, Enum):
    """Unified intelligence decision output."""

    ALLOW = "allow"
    RESTRICT = "restrict"
    BLOCK = "block"


class EventDataStatus(str, Enum):
    """Availability state of event/news data."""

    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class FailPolicy(str, Enum):
    """Behavior when event data is unavailable."""

    FAIL_OPEN = "fail_open"
    FAIL_CLOSED = "fail_closed"


class RecoveryState(str, Enum):
    """Recovery lifecycle for disabled strategies."""

    DISABLED = "disabled"
    RECOVERY_EVALUATION = "recovery_evaluation"
    RESTRICTED = "restricted"
    ACTIVE = "active"


# ===========================================================================
# Event Models
# ===========================================================================

class NormalizedEvent(BaseModel):
    """
    Normalized external event.

    Providers return raw data; the normalizer produces this canonical form.
    All fields are explicit — no silent assumptions.
    """

    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event identifier",
    )
    timestamp: datetime = Field(
        description="When the event occurs/occurred",
    )
    title: str = Field(description="Event title or name")
    description: str = Field(default="", description="Event description if available")
    source: str = Field(description="Origin provider name")
    category: str = Field(description="Event category (e.g. 'economic', 'geopolitical', 'central_bank')")
    impact: EventImpact = Field(default=EventImpact.UNKNOWN, description="Classified impact level")
    affected_instruments: list[str] = Field(
        default_factory=list,
        description="Instruments directly affected by this event",
    )
    affected_currencies: list[str] = Field(
        default_factory=list,
        description="Currencies/regions affected (e.g. ['USD', 'EUR'])",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this event record was created",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="When this event record was last updated",
    )


class EventFreshness(BaseModel):
    """Result of event data freshness validation."""

    status: EventDataStatus
    data_age_seconds: int = Field(ge=0, description="Seconds since event data was last updated")
    max_age_seconds: int = Field(ge=0, description="Configured maximum acceptable age")
    reason: str = ""


class EventRiskResult(BaseModel):
    """Result of the event risk filter for a single event."""

    event: NormalizedEvent
    relevance: EventRelevance
    decision: EventDecision
    within_pre_window: bool = False
    within_post_window: bool = False
    minutes_until_event: Optional[float] = None
    minutes_since_event: Optional[float] = None
    reasons: list[str] = Field(default_factory=list)


class EventIntelligenceSummaryAgg(BaseModel):
    """Aggregated event intelligence across all relevant events."""

    total_events: int = Field(ge=0)
    relevant_events: int = Field(ge=0)
    high_impact_events: int = Field(ge=0)
    event_decision: EventDecision
    freshness: EventFreshness
    risk_results: list[EventRiskResult] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


# ===========================================================================
# Strategy Performance Models
# ===========================================================================

class TradeOutcome(BaseModel):
    """A single realized trade outcome for performance tracking."""

    trade_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str
    instrument: str
    direction: str = Field(description="long or short")
    entry_price: float = Field(gt=0)
    exit_price: Optional[float] = Field(default=None, gt=0)
    pnl: float = Field(default=0.0, description="Realized profit/loss in account currency")
    is_winner: bool = Field(default=False)
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None


class StrategyPerformanceMetrics(BaseModel):
    """Computed performance metrics for a strategy."""

    strategy_id: str
    total_trades: int = Field(ge=0)
    winning_trades: int = Field(ge=0)
    losing_trades: int = Field(ge=0)
    win_rate: float = Field(ge=0.0, le=1.0, description="Win rate as fraction")
    net_pnl: float = Field(description="Net profit/loss")
    average_win: float = Field(ge=0.0)
    average_loss: float = Field(le=0.0)
    profit_factor: float = Field(ge=0.0, description="Gross wins / gross losses")
    max_drawdown: float = Field(ge=0.0, description="Maximum peak-to-trough decline")
    consecutive_losses: int = Field(ge=0, description="Current consecutive loss streak")
    recent_win_rate: float = Field(ge=0.0, le=1.0, description="Win rate over recent window")
    recent_trades: int = Field(ge=0, description="Number of trades in recent window")


class StrategyStateRecord(BaseModel):
    """Current state of a strategy with full context."""

    strategy_id: str
    state: StrategyPerformanceState = StrategyPerformanceState.ACTIVE
    recovery_state: Optional[RecoveryState] = None
    metrics: Optional[StrategyPerformanceMetrics] = None
    sample_size: int = Field(ge=0, description="Total trade count for this strategy")
    state_reasons: list[str] = Field(default_factory=list)
    last_state_change: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_evaluation: Optional[datetime] = None


# ===========================================================================
# Unified Intelligence Decision
# ===========================================================================

class IntelligenceContext(BaseModel):
    """Full context for the unified intelligence decision."""

    event_summary: Optional[EventIntelligenceSummaryAgg] = None
    strategy_state: Optional[StrategyStateRecord] = None
    event_data_status: EventDataStatus = EventDataStatus.UNAVAILABLE
    fallback_policy: FailPolicy = FailPolicy.FAIL_CLOSED
    fallback_reason: str = ""


class IntelligenceDecision(BaseModel):
    """
    Unified Phase 8 intelligence decision.

    Combines event risk and strategy performance into a single
    ALLOW / RESTRICT / BLOCK decision with explicit reasons.
    """

    decision_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique decision identifier",
    )
    instrument: str
    signal_id: Optional[str] = None
    strategy_id: Optional[str] = None

    # Core decision
    overall_decision: OverallDecision
    event_decision: EventDecision = EventDecision.ALLOW
    strategy_state: StrategyPerformanceState = StrategyPerformanceState.ACTIVE

    # Context
    event_context: Optional[EventIntelligenceSummaryAgg] = None
    strategy_performance_context: Optional[StrategyPerformanceMetrics] = None

    # Restrictions & reasons
    restrictions: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    # Data status
    event_data_status: EventDataStatus = EventDataStatus.UNAVAILABLE
    event_data_age_seconds: Optional[int] = Field(default=None, ge=0)

    # Metadata
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decision_version: str = Field(default="1.0", description="Decision logic version")
