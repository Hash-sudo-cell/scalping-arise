"""
Scalping Arise — Technical Feature Models

Strongly typed models for all feature components.
Every model is provider-independent and carries source metadata
for traceability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums — type-safe feature states
# ---------------------------------------------------------------------------

class FeatureAvailability(str, Enum):
    """Whether a feature could be calculated."""

    AVAILABLE = "available"
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"


class EMAAlignment(str, Enum):
    """EMA ordering alignment."""

    BULLISH = "bullish"      # Price > EMA_fast > EMA_medium > EMA_slow
    BEARISH = "bearish"      # Price < EMA_fast < EMA_medium < EMA_slow
    MIXED = "mixed"          # No clean ordering
    UNAVAILABLE = "unavailable"


class EMADirection(str, Enum):
    """EMA slope direction."""

    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"
    UNKNOWN = "unknown"


class RSISessionState(str, Enum):
    """Descriptive RSI state based on configurable thresholds."""

    OVERBOUGHT = "overbought"
    STRONG = "strong"
    NEUTRAL = "neutral"
    WEAK = "weak"
    OVERSOLD = "oversold"


class MACDContext(str, Enum):
    """Descriptive MACD momentum context."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ATRVolatilityState(str, Enum):
    """Descriptive ATR volatility state."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class VolatilityClassification(str, Enum):
    """Extended volatility classification based on ATR percentage."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class FeatureSetStatus(str, Enum):
    """Overall feature-set readiness status."""

    READY = "ready"
    WARMING_UP = "warming_up"
    UNAVAILABLE = "unavailable"


class BollingerPosition(str, Enum):
    """Price position relative to Bollinger Bands."""

    ABOVE_UPPER = "above_upper"
    UPPER_REGION = "upper_region"
    MIDDLE_REGION = "middle_region"
    LOWER_REGION = "lower_region"
    BELOW_LOWER = "below_lower"
    UNAVAILABLE = "unavailable"


class VolumeState(str, Enum):
    """Descriptive volume state."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Feature Metadata
# ---------------------------------------------------------------------------

class FeatureMetadata(BaseModel):
    """Source metadata preserved from Phase 2."""

    canonical_instrument: str
    provider_instrument: str
    provider: str
    source_type: str
    timeframe: str
    candle_count: int
    feature_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Individual Feature Results
# ---------------------------------------------------------------------------

class EMAValue(BaseModel):
    """Single EMA calculation result."""

    period: int
    value: Optional[float] = None
    availability: FeatureAvailability
    direction: EMADirection = EMADirection.UNKNOWN
    price_relative: Optional[str] = Field(
        default=None,
        description="'above', 'below', or 'at' the EMA",
    )
    required_history: int = Field(
        description="Minimum candles needed for a fully initialized value",
    )


class EMAResult(BaseModel):
    """Complete EMA feature result."""

    fast: EMAValue
    medium: EMAValue
    slow: EMAValue
    alignment: EMAAlignment = EMAAlignment.UNAVAILABLE
    alignment_evidence: list[str] = Field(default_factory=list)


class RSIResult(BaseModel):
    """RSI feature result."""

    period: int
    value: Optional[float] = None
    availability: FeatureAvailability
    state: RSISessionState = RSISessionState.NEUTRAL
    required_history: int
    evidence: list[str] = Field(default_factory=list)


class MACDResult(BaseModel):
    """MACD feature result.

    Per-component availability follows staged warm-up:
    - macd_line: AVAILABLE once both fast and slow EMAs are available (slow_period candles)
    - signal_line: AVAILABLE once enough MACD values exist for signal EMA (slow_period + signal_period candles)
    - histogram: AVAILABLE once both macd_line and signal_line are available

    The top-level ``availability`` field reflects the overall MACD state:
    - AVAILABLE when all three components are available
    - INSUFFICIENT_DATA when at least one component is still warming up
    - UNAVAILABLE on calculation error or extreme data shortage
    """

    fast_period: int
    slow_period: int
    signal_period: int
    macd_line: Optional[float] = None
    signal_line: Optional[float] = None
    histogram: Optional[float] = None
    availability: FeatureAvailability
    macd_line_availability: FeatureAvailability = FeatureAvailability.UNAVAILABLE
    signal_line_availability: FeatureAvailability = FeatureAvailability.UNAVAILABLE
    histogram_availability: FeatureAvailability = FeatureAvailability.UNAVAILABLE
    context: MACDContext = MACDContext.NEUTRAL
    required_history: int
    evidence: list[str] = Field(default_factory=list)


class ATRResult(BaseModel):
    """ATR feature result."""

    period: int
    value: Optional[float] = None
    percentage: Optional[float] = Field(
        default=None,
        description="ATR as percentage of current price",
    )
    availability: FeatureAvailability
    state: ATRVolatilityState = ATRVolatilityState.NORMAL
    required_history: int
    evidence: list[str] = Field(default_factory=list)


class BollingerBandsResult(BaseModel):
    """Bollinger Bands feature result."""

    period: int
    std_dev: float
    middle_band: Optional[float] = None
    upper_band: Optional[float] = None
    lower_band: Optional[float] = None
    band_width: Optional[float] = Field(
        default=None,
        description="(Upper - Lower) / Middle as percentage",
    )
    price_position: BollingerPosition = BollingerPosition.UNAVAILABLE
    availability: FeatureAvailability
    required_history: int
    evidence: list[str] = Field(default_factory=list)


class VolumeResult(BaseModel):
    """Volume feature result."""

    sma_period: int
    current_volume: Optional[float] = None
    average_volume: Optional[float] = None
    relative_volume: Optional[float] = Field(
        default=None,
        description="Current volume / average volume",
    )
    availability: FeatureAvailability
    state: VolumeState = VolumeState.UNAVAILABLE
    required_history: int
    evidence: list[str] = Field(default_factory=list)


class PriceFeatures(BaseModel):
    """Basic price context features."""

    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    absolute_change: Optional[float] = None
    percentage_change: Optional[float] = None
    recent_high: Optional[float] = None
    recent_low: Optional[float] = None
    recent_range: Optional[float] = None
    position_in_range: Optional[float] = Field(
        default=None,
        description="Current price position in recent range (0.0 = low, 1.0 = high)",
    )
    availability: FeatureAvailability
    lookback: int
    evidence: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Feature Availability Summary
# ---------------------------------------------------------------------------

class FeatureAvailabilityItem(BaseModel):
    """Availability status for a single feature."""

    name: str
    status: FeatureAvailability
    reason: str = ""


# ---------------------------------------------------------------------------
# Top-Level Feature Result
# ---------------------------------------------------------------------------

class FeatureResult(BaseModel):
    """
    Complete feature output from the Technical Feature Engine.

    This is the top-level response returned by the service.
    All fields are strongly typed and provider-independent.
    """

    status: FeatureAvailability
    reason: str = Field(
        default="",
        description="If unavailable, explains why. If available, general summary.",
    )

    # Feature-set status (separate from component-level availability)
    feature_set_status: FeatureSetStatus = Field(
        default=FeatureSetStatus.UNAVAILABLE,
        description="Overall feature-set readiness: READY, WARMING_UP, or UNAVAILABLE.",
    )
    feature_set_reason: str = Field(
        default="",
        description="Human-readable explanation of the feature-set status.",
    )

    # Extended volatility classification (4-level: low/normal/high/extreme)
    volatility_classification: Optional[VolatilityClassification] = Field(
        default=None,
        description="Extended volatility classification based on ATR percentage.",
    )
    volatility_classification_reason: str = Field(
        default="",
        description="Explanation of the volatility classification thresholds.",
    )

    # Source metadata
    metadata: Optional[FeatureMetadata] = None

    # Feature categories
    trend: Optional[EMAResult] = None
    momentum: Optional[dict] = None  # Contains RSIResult and MACDResult
    volatility: Optional[dict] = None  # Contains ATRResult and BollingerBandsResult
    volume: Optional[VolumeResult] = None
    price: Optional[PriceFeatures] = None

    # Availability tracking
    availability: list[FeatureAvailabilityItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Timestamps
    feature_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Multi-Timeframe Response
# ---------------------------------------------------------------------------

class TimeframeFeatureResult(BaseModel):
    """Feature result for a single timeframe in a multi-timeframe response."""

    timeframe: str
    result: FeatureResult


class MultiTimeframeResult(BaseModel):
    """
    Response from multi-timeframe feature calculation.

    Each timeframe is independently calculated from its own candle series.
    A single timeframe failing does not affect other timeframes.
    """

    timeframes: list[TimeframeFeatureResult] = Field(default_factory=list)
    feature_set_status: FeatureSetStatus = Field(
        default=FeatureSetStatus.UNAVAILABLE,
        description="Aggregate feature-set status across all timeframes.",
    )
    feature_set_reason: str = Field(
        default="",
        description="Human-readable explanation of the aggregate status.",
    )
    warnings: list[str] = Field(default_factory=list)
    feature_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
