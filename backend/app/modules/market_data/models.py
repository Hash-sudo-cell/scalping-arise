"""
Scalping Arise — Internal Normalized Market Data Models

All provider-specific data is converted into these models before
entering the application. These models are provider-independent.

Timestamps are stored as UTC datetime internally.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Timeframe
# ---------------------------------------------------------------------------

class Timeframe(str, Enum):
    """Supported candle timeframes."""

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    MO1 = "1mo"

    @property
    def interval_seconds(self) -> int:
        """Approximate interval in seconds for gap detection."""
        _map: dict[Timeframe, int] = {
            Timeframe.M1: 60,
            Timeframe.M3: 180,
            Timeframe.M5: 300,
            Timeframe.M15: 900,
            Timeframe.M30: 1800,
            Timeframe.H1: 3600,
            Timeframe.H4: 14400,
            Timeframe.D1: 86400,
            Timeframe.W1: 604800,
            Timeframe.MO1: 2_592_000,
        }
        return _map[self]

    @property
    def display_name(self) -> str:
        """Human-readable timeframe label."""
        _map: dict[Timeframe, str] = {
            Timeframe.M1: "1 Minute",
            Timeframe.M3: "3 Minute",
            Timeframe.M5: "5 Minute",
            Timeframe.M15: "15 Minute",
            Timeframe.M30: "30 Minute",
            Timeframe.H1: "1 Hour",
            Timeframe.H4: "4 Hour",
            Timeframe.D1: "Daily",
            Timeframe.W1: "Weekly",
            Timeframe.MO1: "Monthly",
        }
        return _map[self]


# ---------------------------------------------------------------------------
# Instrument
# ---------------------------------------------------------------------------

class Instrument(str, Enum):
    """Canonical internal instrument names."""

    XAU_USD = "XAU/USD"
    BTC_USD = "BTC/USD"
    ETH_USD = "ETH/USD"
    EUR_USD = "EUR/USD"
    GBP_USD = "GBP/USD"
    USD_JPY = "USD/JPY"
    US30 = "US30"


# ---------------------------------------------------------------------------
# Provider health status
# ---------------------------------------------------------------------------

class ProviderHealthStatus(str, Enum):
    """Provider health state."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Timeframe capability
# ---------------------------------------------------------------------------

class TimeframeCapability(str, Enum):
    """How a timeframe is obtained from a provider."""

    NATIVE = "native"
    DERIVED = "derived"
    UNSUPPORTED = "unsupported"


class SourceType(str, Enum):
    """Classification of market data source type.

    Used to distinguish between direct spot market data and proxy
    data from related markets (e.g. gold futures as a proxy for
    spot XAU/USD).
    """

    SPOT = "spot"
    FUTURES_PROXY = "futures_proxy"
    LIVE = "live"          # Live streaming source (OANDA primary)
    VERIFIED = "verified"   # Verified via secondary source (TradingView)


class ConnectionState(str, Enum):
    """Live stream connection health state."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    STALE = "stale"
    DEGRADED = "degraded"


class CandleState(str, Enum):
    """Lifecycle state of a live candle."""

    FORMING = "forming"
    CLOSED = "closed"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Normalized candle
# ---------------------------------------------------------------------------

class NormalizedCandle(BaseModel):
    """
    Provider-independent OHLCV candle model.

    All prices are Decimal-safe floats. Timestamps are UTC.

    Source identity fields:
        instrument: Canonical requested instrument (e.g. XAU/USD)
        provider_instrument: Actual provider symbol used (e.g. GC=F)
        source_type: Classification of the data source (SPOT or FUTURES_PROXY)
        source: Provider identifier that produced this candle
    """

    instrument: Instrument
    provider_instrument: str = Field(
        description="Actual provider symbol used (e.g. XAU/USD, GC=F)"
    )
    source_type: SourceType = Field(
        description="Classification of the data source"
    )
    timeframe: Timeframe
    timestamp: datetime = Field(
        description="Candle open time in UTC"
    )
    open: float = Field(gt=0, description="Open price")
    high: float = Field(gt=0, description="High price")
    low: float = Field(gt=0, description="Low price")
    close: float = Field(gt=0, description="Close price")
    volume: Optional[float] = Field(default=None, description="Volume if available")
    is_closed: bool = Field(
        default=True,
        description="True if candle period has completed, False if still forming",
    )
    source: str = Field(
        description="Provider identifier that produced this candle"
    )

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    model_config = {"validate_assignment": True}


# ---------------------------------------------------------------------------
# Latest price
# ---------------------------------------------------------------------------

class LatestPrice(BaseModel):
    """Normalized latest price snapshot."""

    instrument: Instrument
    provider_instrument: str = Field(
        description="Actual provider symbol used (e.g. XAU/USD, GC=F)"
    )
    source_type: SourceType = Field(
        description="Classification of the data source"
    )
    price: float = Field(gt=0)
    bid: Optional[float] = Field(default=None)
    ask: Optional[float] = Field(default=None)
    timestamp: datetime
    source: str
    is_forming: bool = Field(
        default=False,
        description="True if this represents a currently-forming candle's price",
    )


# ---------------------------------------------------------------------------
# Provider capabilities
# ---------------------------------------------------------------------------

class ProviderCapabilities(BaseModel):
    """Describes what a provider supports."""

    provider_name: str
    supported_instruments: list[Instrument]
    timeframe_capabilities: dict[Timeframe, TimeframeCapability]
    max_historical_candles: Optional[int] = None
    requires_api_key: bool = False
    rate_limit_per_minute: Optional[int] = None

    def is_instrument_supported(self, instrument: Instrument) -> bool:
        return instrument in self.supported_instruments

    def is_timeframe_supported(self, timeframe: Timeframe) -> bool:
        cap = self.timeframe_capabilities.get(timeframe)
        return cap in (TimeframeCapability.NATIVE, TimeframeCapability.DERIVED)


# ---------------------------------------------------------------------------
# Provider health result
# ---------------------------------------------------------------------------

class ProviderHealth(BaseModel):
    """Result of a provider health check."""

    provider_name: str
    status: ProviderHealthStatus
    latency_ms: Optional[float] = None
    last_data_timestamp: Optional[datetime] = None
    message: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Market data response wrappers
# ---------------------------------------------------------------------------

class CandlesResponse(BaseModel):
    """Response containing a list of validated candles."""

    instrument: Instrument
    timeframe: Timeframe
    candles: list[NormalizedCandle]
    source: str
    source_type: SourceType = Field(
        description="Classification of the data source for this response"
    )
    count: int
    has_gaps: bool = False


class MarketDataHealthResponse(BaseModel):
    """Overall market data subsystem health."""

    status: ProviderHealthStatus
    primary: ProviderHealth
    fallback: Optional[ProviderHealth] = None
    active_source: Optional[str] = None
    last_data_timestamp: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Live streaming models
# ---------------------------------------------------------------------------

class LiveCandleState(BaseModel):
    """Tracks the lifecycle of a forming/live candle per timeframe."""

    instrument: Instrument
    timeframe: Timeframe
    state: CandleState = CandleState.FORMING
    candle: Optional[NormalizedCandle] = None
    last_update: Optional[datetime] = None
    source: str = "oanda"

    @property
    def is_fresh(self) -> bool:
        """Check if the forming candle has been updated recently."""
        if self.last_update is None:
            return False
        now = datetime.now(timezone.utc)
        age = (now - self.last_update).total_seconds()
        return age < self.timeframe.interval_seconds * 1.5


class LivePriceState(BaseModel):
    """Tracks the latest live price from OANDA and optional TV verification."""

    instrument: Instrument
    price: float = 0.0
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    timestamp: Optional[datetime] = None
    source: str = "oanda"
    # TradingView verification
    tv_price: Optional[float] = None
    tv_timestamp: Optional[datetime] = None
    price_divergence_pct: Optional[float] = None
    is_verified: bool = False


class LiveStreamStatus(BaseModel):
    """Current status of the live streaming subsystem."""

    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    oanda_connected: bool = False
    tv_connected: bool = False
    active_timeframes: list[str] = []
    last_price: Optional[LivePriceState] = None
    candle_states: dict[str, str] = {}  # timeframe -> CandleState
    reconnect_attempts: int = 0
    last_error: Optional[str] = None
    started_at: Optional[datetime] = None
    last_data_at: Optional[datetime] = None
