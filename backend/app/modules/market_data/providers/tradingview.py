"""
Scalping Arise — TradingView Provider Adapter

Secondary data source for price verification and cross-validation.
Uses tvDatafeed library for periodic candle snapshots and price
comparison against OANDA live data.

TradingView symbols use exchange prefixes: OANDA:XAUUSD

NOTE: tvDatafeed is an unofficial library that reverse-engineers
TradingView's internal protocol. It may break when TradingView
updates their platform. This provider serves as a verification
layer, not the primary data source.

Usage:
    provider = TradingViewProvider(symbol="OANDA:XAUUSD")
    await provider.connect()
    candles = await provider.fetch_historical_candles(instrument, Timeframe.M5, 100)
    price = await provider.fetch_latest_price(instrument)
    await provider.close()
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_data.models import (
    Instrument,
    LatestPrice,
    NormalizedCandle,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
    SourceType,
    Timeframe,
    TimeframeCapability,
)

logger = logging.getLogger(__name__)

# Mapping: internal timeframe → tvDatafeed interval string
_TV_TIMEFRAME_MAP: dict[Timeframe, tuple[str, int]] = {
    Timeframe.M1: ("1", 1),
    Timeframe.M3: ("3", 3),
    Timeframe.M5: ("5", 5),
    Timeframe.M15: ("15", 15),
    Timeframe.M30: ("30", 30),
    Timeframe.H1: ("60", 60),
    Timeframe.H4: ("240", 240),
    Timeframe.D1: ("D", 1),
    Timeframe.W1: ("W", 1),
    Timeframe.MO1: ("M", 1),
}


class TradingViewProvider:
    """TradingView market data adapter for price verification."""

    def __init__(
        self,
        symbol: str = "OANDA:XAUUSD",
        username: str = "",
        password: str = "",
        timeout: float = 15.0,
    ) -> None:
        self._symbol = symbol
        self._username = username
        self._password = password
        self._timeout = timeout
        self._client = None
        self._connected = False

    @property
    def name(self) -> str:
        return "tradingview"

    @property
    def is_connected(self) -> bool:
        return self._connected

    def map_symbol(self, instrument: Instrument) -> str:
        return self._symbol

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name=self.name,
            supported_instruments=[Instrument.XAU_USD],
            timeframe_capabilities={
                Timeframe.M1: TimeframeCapability.NATIVE,
                Timeframe.M3: TimeframeCapability.NATIVE,
                Timeframe.M5: TimeframeCapability.NATIVE,
                Timeframe.M15: TimeframeCapability.NATIVE,
                Timeframe.M30: TimeframeCapability.NATIVE,
                Timeframe.H1: TimeframeCapability.NATIVE,
                Timeframe.H4: TimeframeCapability.NATIVE,
                Timeframe.D1: TimeframeCapability.NATIVE,
                Timeframe.W1: TimeframeCapability.NATIVE,
                Timeframe.MO1: TimeframeCapability.NATIVE,
            },
            max_historical_candles=5000,
            requires_api_key=False,
            rate_limit_per_minute=60,
        )

    async def connect(self) -> bool:
        """
        Initialize the tvDatafeed client.

        Returns True if connection was successful.
        Falls back to guest mode if credentials are not provided.
        """
        try:
            from tvDatafeed import TvDatafeed, Interval

            if self._username and self._password:
                self._client = TvDatafeed(self._username, self._password)
                logger.info("TradingView connected with auth")
            else:
                self._client = TvDatafeed()
                logger.info("TradingView connected as guest")

            self._connected = True
            return True
        except ImportError:
            logger.warning("tvDatafeed package not installed — TradingView provider unavailable")
            self._connected = False
            return False
        except Exception as e:
            logger.error("TradingView connection failed: %s", e)
            self._connected = False
            return False

    async def close(self) -> None:
        """Clean up the tvDatafeed client."""
        self._client = None
        self._connected = False

    async def health_check(self) -> ProviderHealth:
        """Check TradingView availability."""
        if not self._connected:
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderHealthStatus.UNAVAILABLE,
                message="Not connected",
            )

        start = time.monotonic()
        try:
            # Try a minimal fetch to verify connectivity
            candles = await self.fetch_historical_candles(
                Instrument.XAU_USD, Timeframe.H1, limit=1,
            )
            latency = (time.monotonic() - start) * 1000

            if candles:
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.HEALTHY,
                    latency_ms=round(latency, 1),
                    message="Data endpoint responding",
                )
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderHealthStatus.DEGRADED,
                latency_ms=round(latency, 1),
                message="Connected but no data returned",
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderHealthStatus.UNAVAILABLE,
                latency_ms=round(latency, 1),
                message=f"Error: {type(e).__name__}",
            )

    async def fetch_historical_candles(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        limit: int = 100,
    ) -> list[NormalizedCandle]:
        """Fetch historical candles from TradingView."""
        if not self._connected or self._client is None:
            return []

        try:
            from tvDatafeed import Interval

            tv_interval = _TV_TIMEFRAME_MAP.get(timeframe)
            if tv_interval is None:
                raise ValueError(f"Timeframe {timeframe.value} not supported by TradingView")

            # Run synchronous tvDatafeed call in executor to avoid blocking
            loop = asyncio.get_event_loop()

            def _fetch():
                return self._client.get_historical_data(
                    symbol=self._symbol,
                    exchange="OANDA",
                    interval=tv_interval[0],
                    n_bars=limit,
                )

            df = await loop.run_in_executor(None, _fetch)

            if df is None or df.empty:
                return []

            candles = []
            for idx, row in df.iterrows():
                try:
                    ts = idx
                    if hasattr(ts, "to_pydatetime"):
                        ts = ts.to_pydatetime()
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    else:
                        ts = ts.astimezone(timezone.utc)

                    candle = NormalizedCandle(
                        instrument=instrument,
                        provider_instrument=self._symbol,
                        source_type=SourceType.SPOT,  # TV shows spot data
                        timeframe=timeframe,
                        timestamp=ts,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]) if "volume" in row and row["volume"] > 0 else None,
                        is_closed=True,
                        source=self.name,
                    )
                    candles.append(candle)
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning("Skipping malformed TradingView row: %s", e)
                    continue

            return candles
        except Exception as e:
            logger.error("TradingView fetch failed: %s", e)
            return []

    async def fetch_latest_price(
        self,
        instrument: Instrument,
    ) -> Optional[LatestPrice]:
        """Fetch latest price from TradingView (via most recent candle)."""
        candles = await self.fetch_historical_candles(instrument, Timeframe.M1, limit=1)
        if not candles:
            return None

        latest = candles[0]
        return LatestPrice(
            instrument=instrument,
            provider_instrument=self._symbol,
            source_type=SourceType.SPOT,
            price=latest.close,
            timestamp=latest.timestamp,
            source=self.name,
            is_forming=True,
        )

    async def fetch_latest_candle(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> Optional[NormalizedCandle]:
        """Fetch the most recent candle from TradingView."""
        candles = await self.fetch_historical_candles(instrument, timeframe, limit=1)
        return candles[0] if candles else None

    def verify_price(
        self,
        oanda_price: float,
        tv_price: float,
        tolerance_pct: float = 0.3,
    ) -> tuple[bool, float]:
        """
        Compare OANDA price against TradingView price.

        Returns (is_consistent, divergence_pct).
        """
        if oanda_price <= 0 or tv_price <= 0:
            return False, 100.0

        avg = (oanda_price + tv_price) / 2
        divergence_pct = abs(oanda_price - tv_price) / avg * 100

        return divergence_pct <= tolerance_pct, round(divergence_pct, 4)
