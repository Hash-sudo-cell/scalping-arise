"""
Scalping Arise — Twelve Data Provider Adapter

Primary market data provider. Uses Twelve Data REST API for
XAU/USD OHLC data.

Free tier: 8 API credits/min, 800 requests/day.
Supports: 1min, 5min, 15min, 30min, 1h, 2h, 4h, 1day, 1week, 1month.
XAU/USD symbol: "XAU/USD" (native).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

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

# Mapping: internal timeframe -> Twelve Data interval string
_TIMEFRAME_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1min",
    Timeframe.M3: "3min",
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1day",
    Timeframe.W1: "1week",
    Timeframe.MO1: "1month",
}


class TwelveDataProvider:
    """Twelve Data market data adapter."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.twelvedata.com",
        timeout: float = 10.0,
        symbol_map: Optional[dict[Instrument, str]] = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._symbol_map = symbol_map or {Instrument.XAU_USD: "XAU/USD"}
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @property
    def name(self) -> str:
        return "twelve_data"

    def map_symbol(self, instrument: Instrument) -> str:
        return self._symbol_map.get(instrument, instrument.value)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name=self.name,
            supported_instruments=[Instrument.XAU_USD],
            timeframe_capabilities={
                Timeframe.M1: TimeframeCapability.NATIVE,
                Timeframe.M3: TimeframeCapability.UNSUPPORTED,
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
            requires_api_key=True,
            rate_limit_per_minute=8,
        )

    def _parse_td_timestamp(self, dt_str: str) -> datetime:
        """Parse Twelve Data timestamp string to UTC datetime.

        Twelve Data time_series endpoint returns timestamps in UTC.
        Format: "2024-01-15 14:30:00"
        """
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)

    def _parse_td_candle(
        self,
        row: dict,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> NormalizedCandle:
        """Convert a Twelve Data row to NormalizedCandle."""
        return NormalizedCandle(
            instrument=instrument,
            provider_instrument=self.map_symbol(instrument),
            source_type=SourceType.SPOT,
            timeframe=timeframe,
            timestamp=self._parse_td_timestamp(row["datetime"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0)) if row.get("volume") else None,
            is_closed=True,
            source=self.name,
        )

    async def _request(self, endpoint: str, params: dict) -> dict:
        """Make an authenticated request to Twelve Data."""
        client = await self._get_client()
        params["apikey"] = self._api_key

        url = f"{self._base_url}/{endpoint}"
        logger.debug("Twelve Data request: %s %s", endpoint, {k: v for k, v in params.items() if k != "apikey"})

        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> ProviderHealth:
        """Check Twelve Data availability via a minimal price request."""
        start = time.monotonic()
        try:
            data = await self._request(
                "price",
                {"symbol": self.map_symbol(Instrument.XAU_USD)},
            )
            latency = (time.monotonic() - start) * 1000

            if "price" in data:
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.HEALTHY,
                    latency_ms=round(latency, 1),
                    message="Price endpoint responding",
                )
            elif "code" in data:
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.UNAVAILABLE,
                    latency_ms=round(latency, 1),
                    message=data.get("message", "API error"),
                )
            else:
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.DEGRADED,
                    latency_ms=round(latency, 1),
                    message="Unexpected response format",
                )
        except httpx.TimeoutException:
            latency = (time.monotonic() - start) * 1000
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderHealthStatus.UNAVAILABLE,
                latency_ms=round(latency, 1),
                message="Request timed out",
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderHealthStatus.UNAVAILABLE,
                latency_ms=round(latency, 1),
                message=f"Connection error: {type(e).__name__}",
            )

    async def fetch_historical_candles(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        limit: int = 100,
    ) -> list[NormalizedCandle]:
        """Fetch historical candles from Twelve Data."""
        td_interval = _TIMEFRAME_MAP.get(timeframe)
        if td_interval is None:
            raise ValueError(f"Timeframe {timeframe.value} not supported by Twelve Data")

        symbol = self.map_symbol(instrument)
        data = await self._request(
            "time_series",
            {
                "symbol": symbol,
                "interval": td_interval,
                "outputsize": min(limit, 5000),
            },
        )

        if "values" not in data:
            error_msg = data.get("message", "No data returned")
            raise RuntimeError(f"Twelve Data error: {error_msg}")

        candles = []
        for row in data["values"]:
            try:
                candle = self._parse_td_candle(row, instrument, timeframe)
                candles.append(candle)
            except (ValueError, KeyError) as e:
                logger.warning("Skipping malformed candle: %s", e)
                continue

        # Twelve Data returns newest first; reverse to ascending
        candles.reverse()
        return candles

    async def fetch_latest_price(
        self,
        instrument: Instrument,
    ) -> Optional[LatestPrice]:
        """Fetch latest price from Twelve Data."""
        try:
            data = await self._request(
                "price",
                {"symbol": self.map_symbol(instrument)},
            )
            if "price" not in data:
                return None

            return LatestPrice(
                instrument=instrument,
                provider_instrument=self.map_symbol(instrument),
                source_type=SourceType.SPOT,
                price=float(data["price"]),
                timestamp=datetime.now(timezone.utc),
                source=self.name,
                is_forming=True,
            )
        except Exception as e:
            logger.warning("Failed to fetch latest price: %s", e)
            return None

    async def fetch_latest_candle(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> Optional[NormalizedCandle]:
        """Fetch the most recent candle (may be forming)."""
        candles = await self.fetch_historical_candles(instrument, timeframe, limit=1)
        return candles[0] if candles else None
