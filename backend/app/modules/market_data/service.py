"""
Scalping Arise — Market Data Service (Hub)

Central data-access layer. Future modules obtain market data
through this service, never directly from provider adapters.

Flow:
    Request → Validation → Cache check → Provider selection → Fetch → Normalize → Validate → Cache → Response

Live streaming:
    When live_enabled=True, the service integrates with LiveStreamManager
    for real-time OANDA data with TradingView verification.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from app.modules.market_data.cache import CandleCache
from app.modules.market_data.config import MarketDataSettings, get_market_data_settings
from app.modules.market_data.failover import FailoverManager, bounded_retry
from app.modules.market_data.models import (
    CandlesResponse,
    Instrument,
    LatestPrice,
    LivePriceState,
    MarketDataHealthResponse,
    NormalizedCandle,
    ProviderHealth,
    ProviderHealthStatus,
    SourceType,
    Timeframe,
    TimeframeCapability,
)
from app.modules.market_data.provider_base import MarketDataProvider
from app.modules.market_data.providers.twelve_data import TwelveDataProvider
from app.modules.market_data.providers.yfinance import YFinanceProvider
from app.modules.market_data.validation import (
    CandleValidationError,
    check_freshness,
    deduplicate_candles,
    detect_gaps,
    validate_candle,
)

logger = logging.getLogger(__name__)

# Lazy import to avoid circular imports
_live_stream_manager = None


def _get_live_stream_manager():
    """Lazy import of LiveStreamManager."""
    global _live_stream_manager
    if _live_stream_manager is None:
        from app.modules.market_data.live.stream_manager import LiveStreamManager
        _live_stream_manager = LiveStreamManager
    return _live_stream_manager


class MarketDataService:
    """
    Central market data service.

    Manages providers, validation, caching, failover, and live streaming.
    """

    def __init__(self, settings: Optional[MarketDataSettings] = None) -> None:
        self._settings = settings or get_market_data_settings()
        self._failover = FailoverManager(self._settings)
        self._cache = CandleCache(
            enabled=self._settings.cache_enabled,
            ttl_seconds=self._settings.cache_ttl_seconds,
            max_candles=self._settings.cache_max_candles,
        )

        # Initialize providers
        self._primary: MarketDataProvider = self._create_primary_provider()
        self._fallback: MarketDataProvider = self._create_fallback_provider()
        self._active_source: Optional[str] = None

        # Live streaming (initialized lazily via start_live_stream)
        self._live_manager = None

    def _create_primary_provider(self) -> MarketDataProvider:
        """Create the primary provider based on config."""
        symbol_map = {Instrument.XAU_USD: self._settings.twelve_data_symbol_xau_usd}
        return TwelveDataProvider(
            api_key=self._settings.twelve_data_api_key,
            base_url=self._settings.twelve_data_base_url,
            timeout=self._settings.request_timeout_seconds,
            symbol_map=symbol_map,
        )

    def _create_fallback_provider(self) -> MarketDataProvider:
        """Create the fallback provider based on config."""
        symbol_map = {Instrument.XAU_USD: self._settings.yfinance_symbol_xau_usd}
        return YFinanceProvider(
            symbol_map=symbol_map,
            timeout=self._settings.request_timeout_seconds,
        )

    @property
    def active_source(self) -> Optional[str]:
        return self._active_source

    @property
    def cache(self) -> CandleCache:
        return self._cache

    async def health_check(self) -> MarketDataHealthResponse:
        """Check health of both providers and return overall status."""
        logger.info("Running market data health check")

        primary_health = await self._primary.health_check()
        self._failover.update_primary_health(primary_health)

        fallback_health = await self._fallback.health_check()
        self._failover.update_fallback_health(fallback_health)

        # Determine overall status
        if primary_health.status == ProviderHealthStatus.HEALTHY:
            overall = ProviderHealthStatus.HEALTHY
            self._active_source = self._primary.name
        elif fallback_health.status == ProviderHealthStatus.HEALTHY:
            overall = ProviderHealthStatus.DEGRADED
            self._active_source = self._fallback.name
        else:
            overall = ProviderHealthStatus.UNAVAILABLE
            self._active_source = None

        return MarketDataHealthResponse(
            status=overall,
            primary=primary_health,
            fallback=fallback_health,
            active_source=self._active_source,
        )

    async def fetch_candles(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        limit: int = 100,
    ) -> CandlesResponse:
        """
        Fetch validated candles with caching and failover.

        Returns CandlesResponse with validated, deduplicated candles.
        """
        # Check cache first
        cached = self._cache.get(instrument.value, timeframe.value, limit=limit)
        if len(cached) >= limit:
            logger.debug("Cache hit: %s %s (%d candles)", instrument.value, timeframe.value, len(cached))
            gaps = detect_gaps(cached)
            cached_slice = cached[-limit:]
            source_type = cached_slice[0].source_type if cached_slice else SourceType.SPOT
            return CandlesResponse(
                instrument=instrument,
                timeframe=timeframe,
                candles=cached_slice,
                source="cache",
                source_type=source_type,
                count=len(cached_slice),
                has_gaps=len(gaps) > 0,
            )

        # Determine active provider
        use_fallback = self._failover.should_use_fallback()
        provider = self._fallback if use_fallback else self._primary

        # Fetch with bounded retry
        candles, error = await bounded_retry(
            lambda: provider.fetch_historical_candles(instrument, timeframe, limit),
            max_retries=self._settings.max_retries,
            delay=self._settings.retry_delay_seconds,
        )

        # If primary failed, try fallback
        if candles is None and not use_fallback:
            logger.warning("Primary failed, attempting fallback")
            candles, error = await bounded_retry(
                lambda: self._fallback.fetch_historical_candles(instrument, timeframe, limit),
                max_retries=self._settings.max_retries,
                delay=self._settings.retry_delay_seconds,
            )
            if candles is not None:
                self._active_source = self._fallback.name

        if candles is None:
            raise RuntimeError(
                f"All providers failed for {instrument.value} {timeframe.value}: {error}"
            )

        # Validate and deduplicate
        validated = []
        for candle in candles:
            try:
                validate_candle(
                    candle,
                    allowed_instruments=[Instrument.XAU_USD],
                    allowed_timeframes=list(Timeframe),
                )
                validated.append(candle)
            except CandleValidationError as e:
                logger.warning("Candle validation failed: %s", e)
                continue

        validated = deduplicate_candles(validated)
        validated.sort(key=lambda c: c.timestamp)

        # Cache the result
        self._cache.put(instrument.value, timeframe.value, validated)

        # Detect gaps
        gaps = detect_gaps(validated)

        source = self._active_source or provider.name
        source_type = validated[0].source_type if validated else SourceType.SPOT
        logger.info(
            "Fetched %d validated candles: %s %s (source=%s, source_type=%s, gaps=%d)",
            len(validated), instrument.value, timeframe.value, source, source_type.value, len(gaps),
        )

        return CandlesResponse(
            instrument=instrument,
            timeframe=timeframe,
            candles=validated,
            source=source,
            source_type=source_type,
            count=len(validated),
            has_gaps=len(gaps) > 0,
        )

    async def fetch_latest_price(
        self,
        instrument: Instrument,
    ) -> Optional[LatestPrice]:
        """Fetch latest price with failover."""
        use_fallback = self._failover.should_use_fallback()
        provider = self._fallback if use_fallback else self._primary

        price = await provider.fetch_latest_price(instrument)

        if price is None and not use_fallback:
            price = await self._fallback.fetch_latest_price(instrument)
            if price is not None:
                self._active_source = self._fallback.name

        return price

    async def fetch_latest_candle(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> Optional[NormalizedCandle]:
        """Fetch latest candle (forming or closed) with failover."""
        use_fallback = self._failover.should_use_fallback()
        provider = self._fallback if use_fallback else self._primary

        candle = await provider.fetch_latest_candle(instrument, timeframe)

        if candle is None and not use_fallback:
            candle = await self._fallback.fetch_latest_candle(instrument, timeframe)
            if candle is not None:
                self._active_source = self._fallback.name

        return candle

    def get_capabilities(self) -> dict:
        """Get combined capabilities from both providers."""
        primary_caps = self._primary.get_capabilities()
        fallback_caps = self._fallback.get_capabilities()

        # Merge: take the best capability for each timeframe
        merged_timeframes: dict[Timeframe, dict] = {}
        for tf in Timeframe:
            primary_cap = primary_caps.timeframe_capabilities.get(tf, TimeframeCapability.UNSUPPORTED)
            fallback_cap = fallback_caps.timeframe_capabilities.get(tf, TimeframeCapability.UNSUPPORTED)

            best = primary_cap if primary_cap != TimeframeCapability.UNSUPPORTED else fallback_cap
            source = self._primary.name if primary_cap != TimeframeCapability.UNSUPPORTED else (
                self._fallback.name if fallback_cap != TimeframeCapability.UNSUPPORTED else None
            )

            merged_timeframes[tf.value] = {
                "capability": best.value,
                "source": source,
            }

        return {
            "primary": {
                "name": primary_caps.provider_name,
                "canonical_instrument": Instrument.XAU_USD.value,
                "provider_instrument": self._primary.map_symbol(Instrument.XAU_USD),
                "source_type": SourceType.SPOT.value,
                "requires_api_key": primary_caps.requires_api_key,
                "rate_limit_per_minute": primary_caps.rate_limit_per_minute,
            },
            "fallback": {
                "name": fallback_caps.provider_name,
                "canonical_instrument": Instrument.XAU_USD.value,
                "provider_instrument": self._fallback.map_symbol(Instrument.XAU_USD),
                "source_type": SourceType.FUTURES_PROXY.value,
                "requires_api_key": fallback_caps.requires_api_key,
                "rate_limit_per_minute": fallback_caps.rate_limit_per_minute,
            },
            "timeframes": merged_timeframes,
            "instruments": [i.value for i in primary_caps.supported_instruments],
            "active_source": self._active_source,
        }

    async def close(self) -> None:
        """Clean up provider resources and live streaming."""
        if self._live_manager and self._live_manager.is_running:
            await self._live_manager.stop()
        if hasattr(self._primary, "close"):
            await self._primary.close()

    # -------------------------------------------------------------------------
    # Live streaming integration
    # -------------------------------------------------------------------------

    async def start_live_stream(
        self,
        on_price_update: Optional[Callable[[LivePriceState], None]] = None,
        on_candle_closed: Optional[Callable[[NormalizedCandle], None]] = None,
    ) -> None:
        """Start live streaming via LiveStreamManager."""
        if not self._settings.live_enabled:
            logger.info("Live streaming disabled via config")
            return

        if self._live_manager and self._live_manager.is_running:
            logger.warning("Live stream already running")
            return

        LiveStreamManager = _get_live_stream_manager()
        self._live_manager = LiveStreamManager(
            settings=self._settings,
            on_price_update=on_price_update,
            on_candle_closed=self._on_live_candle_closed,
        )

        # Store external callbacks for candle-closed events
        self._external_on_candle_closed = on_candle_closed

        await self._live_manager.start()
        logger.info("Live streaming started")

    async def stop_live_stream(self) -> None:
        """Stop live streaming."""
        if self._live_manager and self._live_manager.is_running:
            await self._live_manager.stop()
            self._live_manager = None
            logger.info("Live streaming stopped")

    def _on_live_candle_closed(self, candle: NormalizedCandle) -> None:
        """Handle a closed candle from the live stream."""
        # Push to cache for downstream consumers
        self._cache.update_candle(candle)

        # Forward to external callback if registered
        if hasattr(self, "_external_on_candle_closed") and self._external_on_candle_closed:
            self._external_on_candle_closed(candle)

    def get_live_price(self) -> Optional[LivePriceState]:
        """Get the current live price state."""
        if self._live_manager is None:
            return None
        return self._live_manager.price_state

    def get_live_forming_candle(self, timeframe: Timeframe) -> Optional[NormalizedCandle]:
        """Get the current forming candle for a timeframe."""
        if self._live_manager is None:
            return None
        return self._live_manager.get_forming_candle(timeframe)

    def get_live_status(self) -> Optional[dict]:
        """Get live stream status."""
        if self._live_manager is None:
            return None
        return self._live_manager.get_status().model_dump(mode="json")

    @property
    def live_streaming(self) -> bool:
        """Whether live streaming is active."""
        return self._live_manager is not None and self._live_manager.is_running
