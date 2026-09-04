"""
Scalping Arise — Market Analysis Models

Strongly typed models for all analysis components.
Every model is provider-independent and carries source metadata
for traceability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums — type-safe analysis states
# ---------------------------------------------------------------------------

class SwingType(str, Enum):
    """Classification of a detected swing point."""

    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"


class StructureLabel(str, Enum):
    """Market structure label for a swing point relative to the prior swing."""

    HH = "HH"  # Higher High
    HL = "HL"  # Higher Low
    LH = "LH"  # Lower High
    LL = "LL"  # Lower Low
    INITIAL = "initial"  # First swing — no comparison possible


class TrendState(str, Enum):
    """Deterministic trend classification."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"
    UNCLEAR = "unclear"


class BOSDirection(str, Enum):
    """Break of Structure direction."""

    BULLISH_BOS = "bullish_bos"
    BEARISH_BOS = "bearish_bos"


class CHOCHDirection(str, Enum):
    """Change of Character direction."""

    BULLISH_CHOCH = "bullish_choch"
    BEARISH_CHOCH = "bearish_choch"


class ZoneType(str, Enum):
    """Support or Resistance zone classification."""

    SUPPORT = "support"
    RESISTANCE = "resistance"


class MarketSession(str, Enum):
    """Major FX market sessions."""

    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"  # London + New York overlap
    OFF_SESSION = "off_session"


class MarketRegime(str, Enum):
    """Deterministic market regime classification."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNCLEAR = "unclear"


class AnalysisStatus(str, Enum):
    """Whether analysis could be completed."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Liquidity Enums
# ---------------------------------------------------------------------------

class LiquiditySide(str, Enum):
    """Side of the liquidity pool relative to price."""

    BUY_SIDE = "buy_side"    # Liquidity resting above highs
    SELL_SIDE = "sell_side"  # Liquidity resting below lows


class LiquidityPoolType(str, Enum):
    """Classification of liquidity pool origin."""

    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"


class LiquidityPoolStatus(str, Enum):
    """Lifecycle state of a liquidity pool."""

    ACTIVE = "active"
    SWEPT = "swept"
    INVALIDATED = "invalidated"


class LiquidityStrength(str, Enum):
    """Descriptive strength of a liquidity pool."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LiquiditySweepMode(str, Enum):
    """How sweep detection is evaluated against price."""

    WICK = "wick"    # Candle wick crosses level
    CLOSE = "close"  # Candle close crosses level


class PostSweepReaction(str, Enum):
    """Descriptive classification of price behavior after a sweep."""

    REJECTION = "rejection"
    ACCEPTANCE = "acceptance"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Swing Point
# ---------------------------------------------------------------------------

class SwingPoint(BaseModel):
    """A detected swing high or swing low."""

    index: int = Field(description="Index in the candle array")
    timestamp: datetime = Field(description="Candle timestamp in UTC")
    price: float = Field(gt=0, description="Swing price (high for swing_high, low for swing_low)")
    swing_type: SwingType
    confirmed: bool = Field(
        default=True,
        description="True if enough subsequent candles confirmed this swing",
    )
    timeframe: str = Field(description="Timeframe this swing was detected on")

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Structure Point
# ---------------------------------------------------------------------------

class StructurePoint(BaseModel):
    """A swing point annotated with its structural classification."""

    swing: SwingPoint
    label: StructureLabel
    reason: str = Field(
        default="",
        description="Explanation of why this label was assigned",
    )


# ---------------------------------------------------------------------------
# BOS Event
# ---------------------------------------------------------------------------

class BOSEvent(BaseModel):
    """A detected Break of Structure."""

    direction: BOSDirection
    broken_level: float = Field(description="The swing level that was broken")
    break_price: float = Field(description="The price that broke the level")
    break_timestamp: datetime = Field(description="Timestamp of the breaking candle")
    confirmation_basis: str = Field(
        description="How the break was confirmed (e.g. 'close_above', 'close_below')"
    )
    timeframe: str
    evidence: str = Field(default="", description="Supporting evidence for this BOS")


# ---------------------------------------------------------------------------
# CHOCH Event
# ---------------------------------------------------------------------------

class CHOCHEvent(BaseModel):
    """A detected Change of Character."""

    direction: CHOCHDirection
    broken_level: float = Field(description="The swing level that was broken")
    break_price: float = Field(description="The price that broke the level")
    break_timestamp: datetime = Field(description="Timestamp of the breaking candle")
    confirmation_basis: str = Field(description="How the break was confirmed")
    prior_structure: str = Field(description="Description of the structure that was violated")
    timeframe: str
    evidence: str = Field(default="", description="Supporting evidence for this CHOCH")


# ---------------------------------------------------------------------------
# Support / Resistance Zone
# ---------------------------------------------------------------------------

class SupportResistanceZone(BaseModel):
    """A support or resistance zone derived from market structure."""

    zone_type: ZoneType
    lower_bound: float = Field(description="Lower boundary of the zone")
    upper_bound: float = Field(description="Upper boundary of the zone")
    strength: int = Field(
        ge=0,
        description="Number of swings that touched or tested this zone",
    )
    source_swings: list[int] = Field(
        default_factory=list,
        description="Indices of swings that define this zone",
    )
    timeframe: str
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Analysis Context — source metadata preserved from Phase 2
# ---------------------------------------------------------------------------

class AnalysisContext(BaseModel):
    """Source metadata carried through the analysis pipeline."""

    canonical_instrument: str
    provider_instrument: str
    provider: str
    source_type: str  # "spot" or "futures_proxy"
    timeframe: str
    candle_count: int
    analysis_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    data_from_cache: bool = False


# ---------------------------------------------------------------------------
# Analysis Result — the top-level output
# ---------------------------------------------------------------------------

class TrendResult(BaseModel):
    """Trend classification with supporting evidence."""

    state: TrendState
    reason: str = Field(default="", description="Why this trend was classified")
    structure_labels: list[StructureLabel] = Field(
        default_factory=list,
        description="Recent structure labels used for classification",
    )


class StructureResult(BaseModel):
    """Market structure output."""

    points: list[StructurePoint] = Field(
        default_factory=list,
        description="All classified structure points",
    )
    latest_labels: list[StructureLabel] = Field(
        default_factory=list,
        description="The most recent structure labels in sequence",
    )


class EventsResult(BaseModel):
    """BOS and CHOCH events."""

    bos: list[BOSEvent] = Field(default_factory=list)
    choch: list[CHOCHEvent] = Field(default_factory=list)


class ZonesResult(BaseModel):
    """Support and Resistance zones."""

    support: list[SupportResistanceZone] = Field(default_factory=list)
    resistance: list[SupportResistanceZone] = Field(default_factory=list)


class RegimeResult(BaseModel):
    """Market regime classification."""

    state: MarketRegime
    evidence: list[str] = Field(
        default_factory=list,
        description="Supporting evidence for the regime classification",
    )


# ---------------------------------------------------------------------------
# Liquidity Models
# ---------------------------------------------------------------------------

class LiquidityPool(BaseModel):
    """A detected liquidity pool derived from confirmed swing points."""

    pool_id: str = Field(description="Unique stable identifier for this pool")
    side: LiquiditySide
    pool_type: LiquidityPoolType
    price_level: float = Field(description="Center/anchor price level of the pool")
    lower_bound: float = Field(description="Lower boundary of the pool zone")
    upper_bound: float = Field(description="Upper boundary of the pool zone")
    touch_count: int = Field(ge=0, description="Number of swings that contributed to this pool")
    source_swings: list[int] = Field(
        default_factory=list,
        description="Indices of confirmed swings that define this pool",
    )
    source_timestamps: list[datetime] = Field(
        default_factory=list,
        description="Timestamps of source swings",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this pool was created",
    )
    status: LiquidityPoolStatus = Field(default=LiquidityPoolStatus.ACTIVE)
    strength: LiquidityStrength = Field(default=LiquidityStrength.LOW)
    timeframe: str = Field(description="Timeframe this pool was detected on")


class LiquiditySweep(BaseModel):
    """A detected sweep event where price took an existing liquidity pool."""

    sweep_id: str = Field(description="Unique identifier for this sweep event")
    pool_id: str = Field(description="ID of the pool that was swept")
    side: LiquiditySide
    pool_price_level: float = Field(description="The pool's price level that was swept")
    sweep_timestamp: datetime = Field(description="Timestamp of the candle that performed the sweep")
    sweep_mode: LiquiditySweepMode = Field(description="Mode used to detect this sweep")
    sweep_price: float = Field(description="Price that performed the sweep (wick or close)")
    candle_close: float = Field(description="Close price of the sweeping candle")
    reaction: PostSweepReaction = Field(default=PostSweepReaction.UNAVAILABLE)
    reaction_timestamp: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the candle used to classify the reaction",
    )
    timeframe: str = Field(description="Timeframe of the sweep")


class LiquidityAnalysisResult(BaseModel):
    """Complete liquidity analysis output."""

    status: AnalysisStatus = Field(default=AnalysisStatus.UNAVAILABLE)
    reason: str = Field(default="", description="Explanation of liquidity analysis status")

    pools: list[LiquidityPool] = Field(default_factory=list)
    sweeps: list[LiquiditySweep] = Field(default_factory=list)

    active_pool_count: int = Field(default=0, ge=0)
    swept_pool_count: int = Field(default=0, ge=0)

    nearest_buy_side_pool: Optional[LiquidityPool] = Field(default=None)
    nearest_sell_side_pool: Optional[LiquidityPool] = Field(default=None)

    distance_to_buy_side: Optional[float] = Field(
        default=None,
        description="Absolute price distance to nearest active buy-side pool",
    )
    distance_to_sell_side: Optional[float] = Field(
        default=None,
        description="Absolute price distance to nearest active sell-side pool",
    )
    distance_to_buy_side_pct: Optional[float] = Field(
        default=None,
        description="Percentage distance to nearest active buy-side pool",
    )
    distance_to_sell_side_pct: Optional[float] = Field(
        default=None,
        description="Percentage distance to nearest active sell-side pool",
    )


class AnalysisResult(BaseModel):
    """
    Complete analysis output from the Market Analysis Engine.

    This is the top-level response returned by the service.
    All fields are strongly typed and provider-independent.
    """

    status: AnalysisStatus
    reason: str = Field(
        default="",
        description="If unavailable, explains why. If available, general summary.",
    )

    # Source metadata
    context: Optional[AnalysisContext] = None

    # Analysis outputs
    trend: Optional[TrendResult] = None
    structure: Optional[StructureResult] = None
    events: Optional[EventsResult] = None
    zones: Optional[ZonesResult] = None
    session: Optional[MarketSession] = None
    regime: Optional[RegimeResult] = None
    liquidity: Optional[LiquidityAnalysisResult] = None

    # Timestamps
    analysis_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
