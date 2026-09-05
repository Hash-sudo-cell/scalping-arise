"""
Scalping Arise — Trade Planning & Risk Engine Models

Strongly typed models for trade plan lifecycle, instrument specifications,
entry planning, stop-loss, take-profit, position sizing, risk calculation,
cost estimation, and plan validation.

Phase 7 receives Phase 6 BUY/SELL/NO_TRADE signals and determines whether
they can be safely converted into mathematically valid trade plans.
Phase 7 plans trades only — it never executes them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ===========================================================================
# Enums — type-safe trade planning states
# ===========================================================================

class PlanState(str, Enum):
    """
    Full lifecycle state machine for a trade plan.

    Transitions:
        NO_PLAN → DRAFT
        DRAFT → CALCULATED | REJECTED
        CALCULATED → VALIDATED | REJECTED
        VALIDATED → APPROVED | REJECTED | EXPIRED | INVALIDATED
        APPROVED → EXPIRED | INVALIDATED
        Any → EXPIRED (TTL elapsed)
        Any → INVALIDATED (market condition change)
    """

    NO_PLAN = "no_plan"
    DRAFT = "draft"
    CALCULATED = "calculated"
    VALIDATED = "validated"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class PlanSide(str, Enum):
    """Directional side of a trade plan."""

    LONG = "long"
    SHORT = "short"


class EntryType(str, Enum):
    """How the trade entry is structured."""

    MARKET = "market"
    LIMIT = "limit"


class EntryState(str, Enum):
    """Whether entry conditions are met."""

    ENTRY_READY = "entry_ready"
    WAIT_FOR_ENTRY = "wait_for_entry"
    ENTRY_UNAVAILABLE = "entry_unavailable"


class SLType(str, Enum):
    """Method used to determine stop-loss placement."""

    INVALIDATION = "invalidation"
    ATR = "atr"
    STRUCTURE = "structure"
    FIXED = "fixed"


class TPTarget(str, Enum):
    """Which take-profit target this is."""

    TP1 = "tp1"
    TP2 = "tp2"


class RiskUnit(str, Enum):
    """Unit of risk measurement."""

    ABSOLUTE = "absolute"
    PERCENTAGE = "percentage"
    ATR_MULTIPLE = "atr_multiple"


class PlanRejectionReason(str, Enum):
    """Typed reason codes for plan rejection."""

    SIGNAL_NOT_ELIGIBLE = "signal_not_eligible"
    INSUFFICIENT_DATA = "insufficient_data"
    DATA_STALE = "data_stale"
    PRICE_INVALID = "price_invalid"
    SL_INVALID = "sl_invalid"
    TP_INVALID = "tp_invalid"
    RISK_EXCEEDED = "risk_exceeded"
    RR_BELOW_MINIMUM = "rr_below_minimum"
    SPREAD_TOO_WIDE = "spread_too_wide"
    VOLATILITY_EXTREME = "volatility_extreme"
    LOT_SIZE_INVALID = "lot_size_invalid"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_DRAWDOWN = "max_drawdown"
    INSTRUMENT_UNAVAILABLE = "instrument_unavailable"
    MARKET_CLOSED = "market_closed"
    PLAN_EXPIRED = "plan_expired"
    MARKET_SHIFT = "market_shift"


class VolatilityAdjustment(str, Enum):
    """How volatility affects plan parameters."""

    EXPAND = "expand"
    NORMAL = "normal"
    CONTRACT = "contract"


# ===========================================================================
# Instrument Specification
# ===========================================================================

class InstrumentSpecification(BaseModel):
    """
    Instrument-specific trading parameters.

    Defines tick size, contract size, lot constraints, and price precision
    for a specific instrument. Used throughout trade planning for
    mathematically valid calculations.
    """

    instrument: str
    tick_size: float = Field(gt=0, description="Minimum price movement (e.g. 0.01 for XAU/USD)")
    contract_size: float = Field(gt=0, description="Units per 1.0 lot (e.g. 100 for XAU/USD)")
    lot_step: float = Field(gt=0, description="Minimum lot increment (e.g. 0.01)")
    min_lot: float = Field(gt=0, description="Minimum tradeable lot size")
    max_lot: float = Field(gt=0, description="Maximum tradeable lot size")
    price_precision: int = Field(ge=0, le=10, description="Decimal places for price display")
    pip_value_per_lot: float = Field(
        gt=0,
        description="Value of 1 pip per 1.0 lot in account currency",
    )
    typical_spread_pips: float = Field(
        ge=0,
        description="Typical spread in pips for this instrument",
    )
    margin_rate: float = Field(
        gt=0, le=1.0,
        description="Margin requirement as fraction (e.g. 0.01 for 1% margin)",
    )
    trading_hours: Optional[str] = Field(
        default=None,
        description="Typical trading hours (e.g. '24/5', '09:00-17:00 CET')",
    )

    def round_price(self, price: float) -> float:
        """Round a price to the instrument's tick size."""
        if self.tick_size <= 0:
            return price
        precision = max(0, -int(__import__("math").log10(self.tick_size)))
        return round(round(price / self.tick_size) * self.tick_size, precision)

    def round_lots(self, lots: float) -> float:
        """Round lots to the instrument's lot step, clamped to min/max."""
        if self.lot_step <= 0:
            return lots
        steps = round(lots / self.lot_step)
        raw = steps * self.lot_step
        return max(self.min_lot, min(self.max_lot, round(raw, 10)))

    def ticks_between(self, price_a: float, price_b: float) -> float:
        """Count the number of ticks between two prices."""
        return abs(price_a - price_b) / self.tick_size

    def pip_distance(self, price_a: float, price_b: float) -> float:
        """Distance in pips between two prices."""
        return abs(price_a - price_b) / (self.tick_size * 10)

    def is_tick_aligned(self, price: float) -> bool:
        """Check if a price is aligned to the tick grid."""
        if self.tick_size <= 0:
            return True
        remainder = price % self.tick_size
        return remainder < self.tick_size * 1e-9 or (self.tick_size - remainder) < self.tick_size * 1e-9


# ===========================================================================
# Entry Planning
# ===========================================================================

class EntryPlan(BaseModel):
    """
    Entry planning result.

    Determines whether the signal can be acted on immediately (ENTRY_READY),
    requires waiting for a specific condition (WAIT_FOR_ENTRY), or cannot
    be acted on at all (ENTRY_UNAVAILABLE).
    """

    state: EntryState
    entry_type: EntryType = EntryType.MARKET
    entry_price: Optional[float] = Field(default=None, gt=0)
    limit_price: Optional[float] = Field(default=None, gt=0, description="Limit order price if WAIT_FOR_ENTRY")
    limit_distance_pips: Optional[float] = Field(default=None, ge=0)
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)


# ===========================================================================
# Stop-Loss Planning
# ===========================================================================

class StopLossPlan(BaseModel):
    """
    Stop-loss placement result.

    Uses invalidation-based SL as primary method, with ATR-based
    and structure-based fallbacks.
    """

    sl_type: SLType
    sl_price: float = Field(gt=0, description="Stop-loss price level")
    sl_distance_pips: float = Field(gt=0, description="Distance from entry in pips")
    sl_distance_price: float = Field(gt=0, description="Distance from entry in price units")
    risk_per_lot: float = Field(gt=0, description="Loss per 1.0 lot if SL is hit")
    invalidation_level: Optional[float] = Field(
        default=None, gt=0,
        description="Raw invalidation level from analysis (if SL type is invalidation)",
    )
    atr_multiple: Optional[float] = Field(
        default=None, ge=0,
        description="ATR multiplier used (if SL type is ATR)",
    )
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)


# ===========================================================================
# Take-Profit Planning
# ===========================================================================

class TakeProfitTarget(BaseModel):
    """A single take-profit target."""

    target: TPTarget
    tp_price: float = Field(gt=0, description="Take-profit price level")
    tp_distance_pips: float = Field(gt=0, description="Distance from entry in pips")
    tp_distance_price: float = Field(gt=0, description="Distance from entry in price units")
    reward_per_lot: float = Field(gt=0, description="Profit per 1.0 lot if TP is hit")
    risk_reward_ratio: float = Field(ge=0, description="Reward-to-risk ratio for this target")
    partial_close_pct: Optional[float] = Field(
        default=None, ge=0, le=1.0,
        description="Fraction of position to close at this target",
    )
    reason: str = ""


class TakeProfitPlan(BaseModel):
    """
    Take-profit planning result.

    Provides TP1 (conservative) and TP2 (extended) targets.
    Each target has its own R:R ratio and optional partial close percentage.
    """

    targets: list[TakeProfitTarget] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


# ===========================================================================
# Position Sizing & Risk Calculation
# ===========================================================================

class RiskParameters(BaseModel):
    """Input parameters for position sizing calculation."""

    account_balance: float = Field(gt=0, description="Current account balance")
    risk_per_trade_pct: float = Field(gt=0, le=100, description="Max risk per trade as % of balance")
    max_positions: int = Field(default=1, ge=1, le=50, description="Maximum concurrent positions")
    current_open_positions: int = Field(default=0, ge=0, description="Current number of open positions")


class PositionSizeResult(BaseModel):
    """Result of position sizing calculation."""

    lots: float = Field(ge=0, description="Calculated lot size")
    risk_amount: float = Field(ge=0, description="Risk amount in account currency")
    risk_pct_actual: float = Field(ge=0, description="Actual risk as % of balance")
    margin_required: float = Field(ge=0, description="Margin required for this position")
    margin_pct: float = Field(ge=0, description="Margin as % of balance")
    exposure: float = Field(ge=0, description="Total notional exposure")
    exposure_pct: float = Field(ge=0, description="Exposure as % of balance")


class RiskCalculation(BaseModel):
    """
    Complete risk calculation for a trade plan.

    Combines position sizing, risk parameters, and guardrail checks.
    """

    position_size: PositionSizeResult
    risk_parameters: RiskParameters
    within_risk_limits: bool = True
    within_drawdown_limit: bool = True
    within_daily_loss_limit: bool = True
    daily_loss_remaining: float = Field(ge=0, description="Remaining daily loss allowance")
    max_drawdown_remaining: float = Field(ge=0, description="Remaining drawdown allowance")
    warnings: list[str] = Field(default_factory=list)
    rejections: list[str] = Field(default_factory=list)


# ===========================================================================
# Cost Estimation
# ===========================================================================

class CostEstimate(BaseModel):
    """Estimated trading costs for a plan."""

    spread_cost: float = Field(ge=0, description="Estimated spread cost in account currency")
    spread_pips: float = Field(ge=0, description="Current spread in pips")
    commission: float = Field(ge=0, default=0, description="Estimated commission")
    total_cost: float = Field(ge=0, description="Total estimated cost")
    cost_pct_of_risk: float = Field(ge=0, description="Cost as % of risk amount")
    within_tolerance: bool = True
    reason: str = ""


# ===========================================================================
# Freshness & Data Quality
# ===========================================================================

class FreshnessCheck(BaseModel):
    """Result of market data freshness validation."""

    is_fresh: bool
    age_seconds: int = Field(ge=0, description="Seconds since last data update")
    max_age_seconds: int = Field(ge=0, description="Maximum acceptable age")
    source: str = ""
    reason: str = ""


class PriceTickCheck(BaseModel):
    """Result of price tick validation."""

    is_valid: bool
    current_price: float = Field(ge=0, description="Current price (0 if invalid)")
    bid: Optional[float] = Field(default=None, gt=0)
    ask: Optional[float] = Field(default=None, gt=0)
    spread_pips: Optional[float] = Field(default=None, ge=0)
    tick_aligned: bool = True
    price_age_seconds: Optional[int] = Field(default=None, ge=0)
    reason: str = ""


# ===========================================================================
# Eligibility Check
# ===========================================================================

class EligibilityCheck(BaseModel):
    """Result of a single eligibility gate check."""

    check_name: str
    passed: bool
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)


class EligibilityResult(BaseModel):
    """Aggregated signal eligibility gate result."""

    eligible: bool
    checks: list[EligibilityCheck] = Field(default_factory=list)
    blocked_by: Optional[str] = Field(default=None)


# ===========================================================================
# Plan Lifecycle Record
# ===========================================================================

class PlanTransition(BaseModel):
    """A single state transition in the plan lifecycle."""

    from_state: PlanState
    to_state: PlanState
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""


class TradePlan(BaseModel):
    """
    Full lifecycle record for a single trade plan.

    Tracks the plan from NO_PLAN through APPROVED/REJECTED/EXPIRED/INVALIDATED,
    with all risk parameters, entry/exit levels, and validation results.

    Phase 7 plans trades only — it never executes them.
    """

    plan_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique plan identifier",
    )
    instrument: str
    side: PlanSide
    state: PlanState = PlanState.NO_PLAN

    # Signal reference
    signal_id: Optional[str] = Field(default=None, description="Source signal ID from Phase 6")
    signal_confidence: Optional[int] = Field(default=None, ge=0, le=100)
    signal_quality: Optional[int] = Field(default=None, ge=0, le=100)

    # Entry
    entry: Optional[EntryPlan] = None

    # Stop-loss
    stop_loss: Optional[StopLossPlan] = None

    # Take-profit
    take_profit: Optional[TakeProfitPlan] = None

    # Position sizing & risk
    risk: Optional[RiskCalculation] = None

    # Cost
    cost: Optional[CostEstimate] = None

    # Freshness
    freshness: Optional[FreshnessCheck] = None

    # Price validation
    price_check: Optional[PriceTickCheck] = None

    # Eligibility
    eligibility: Optional[EligibilityResult] = None

    # Rejection
    rejection_reason: Optional[PlanRejectionReason] = None
    rejection_detail: str = ""

    # Volatility context
    volatility_adjustment: VolatilityAdjustment = VolatilityAdjustment.NORMAL
    atr_value: Optional[float] = Field(default=None, ge=0)
    volatility_state: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    calculated_at: Optional[datetime] = None
    validated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    invalidated_at: Optional[datetime] = None
    ttl_seconds: int = Field(default=300, ge=0, description="Plan time-to-live in seconds")

    # State history
    state_history: list[PlanTransition] = Field(default_factory=list)

    # Human-readable
    reason: str = ""

    @property
    def is_actionable(self) -> bool:
        """Whether this plan is in an actionable state."""
        return self.state in (PlanState.APPROVED, PlanState.VALIDATED)

    @property
    def is_terminal(self) -> bool:
        """Whether this plan has reached a terminal state."""
        return self.state in (
            PlanState.REJECTED,
            PlanState.EXPIRED,
            PlanState.INVALIDATED,
        )

    @property
    def age_seconds(self) -> float:
        """Seconds since plan was created."""
        now = datetime.now(timezone.utc)
        return (now - self.created_at).total_seconds()

    @property
    def remaining_ttl(self) -> float:
        """Seconds remaining before plan expires."""
        return max(0.0, self.ttl_seconds - self.age_seconds)


# ===========================================================================
# Convenience: side ↔ direction mapping (bridges to Phase 6)
# ===========================================================================

def side_from_decision(decision: str) -> Optional[PlanSide]:
    """Map a Phase 6 DecisionType string to a PlanSide."""
    _map = {
        "buy": PlanSide.LONG,
        "sell": PlanSide.SHORT,
    }
    return _map.get(decision)


def rr_ratio(reward: float, risk: float) -> float:
    """Calculate reward-to-risk ratio safely."""
    if risk <= 0:
        return 0.0
    return reward / risk
