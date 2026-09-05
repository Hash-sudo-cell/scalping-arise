"""
Scalping Arise — OANDA V20 Provider Adapter

Primary live market data source. Uses OANDA V20 API for:
- REST: historical candles, latest price, account validation
- SSE streaming: real-time price ticks and candle updates

OANDA uses underscores in instrument names (XAU_USD, not XAU/USD).
Streaming uses Server-Sent Events (SSE), not WebSocket.

Practice endpoint: https://api-fxpractice.oanda.com/v3
Live endpoint:     https://api-fxtrade.oanda.com/v3
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

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

# Mapping: internal timeframe → OANDA V20 granularity
_TIMEFRAME_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "M1",
    Timeframe.M3: "M3",
    Timeframe.M5: "M5",
    Timeframe.M15: "M15",
    Timeframe.M30: "M30",
    Timeframe.H1: "H1",
    Timeframe.H4: "H4",
    Timeframe.D1: "D",
    Timeframe.W1: "W",
    Timeframe.MO1: "M",
}


class OandaProvider:
    """OANDA V20 market data adapter — REST + SSE streaming."""

    def __init__(
        self,
        account_id: str,
        api_token: str,
        base_url: str = "https://api-fxpractice.oanda.com/v3",
        stream_url: str = "https://stream-fxpractice.oanda.com/v3",
        timeout: float = 10.0,
        instrument: str = "XAU_USD",
    ) -> None:
        self._account_id = account_id
        self._api_token = api_token
        self._base_url = base_url.rstrip("/")
        self._stream_url = stream_url.rstrip("/")
        self._timeout = timeout
        self._instrument = instrument
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={
                    "Authorization": f"Bearer {self._api_token}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @property
    def name(self) -> str:
        return "oanda"

    def map_symbol(self, instrument: Instrument) -> str:
        return self._instrument

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
            requires_api_key=True,
            rate_limit_per_minute=120,
        )

    def _oanda_timestamp_to_utc(self, ts_str: str) -> datetime:
        """Parse OANDA timestamp to UTC datetime.

        OANDA format: '2024-01-15T14:30:00.000000000Z'
        """
        # Strip nanoseconds if present
        clean = ts_str.rstrip("Z")
        if "." in clean:
            date_part, frac = clean.split(".", 1)
            # Truncate fractional to 6 digits (microseconds)
            frac = frac[:6].ljust(6, "0")
            clean = f"{date_part}.{frac}"
        else:
            clean = clean
        dt = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S.%f")
        return dt.replace(tzinfo=timezone.utc)

    def _parse_oanda_candle(
        self,
        mid: dict,
        instrument: Instrument,
        timeframe: Timeframe,
        is_closed: bool,
    ) -> NormalizedCandle:
        """Convert OANDA mid candle to NormalizedCandle."""
        return NormalizedCandle(
            instrument=instrument,
            provider_instrument=self._instrument,
            source_type=SourceType.LIVE,
            timeframe=timeframe,
            timestamp=self._oanda_timestamp_to_utc(mid["time"]),
            open=float(mid["o"]),
            high=float(mid["h"]),
            low=float(mid["l"]),
            close=float(mid["c"]),
            volume=float(mid.get("v", 0)),
            is_closed=is_closed,
            source=self.name,
        )

    async def health_check(self) -> ProviderHealth:
        """Check OANDA account access via a minimal price request."""
        start = time.monotonic()
        try:
            client = await self._get_client()
            url = f"{self._base_url}/accounts/{self._account_id}/pricing"
            response = await client.get(
                url,
                params={"instruments": self._instrument},
            )
            latency = (time.monotonic() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                prices = data.get("prices", [])
                if prices:
                    return ProviderHealth(
                        provider_name=self.name,
                        status=ProviderHealthStatus.HEALTHY,
                        latency_ms=round(latency, 1),
                        message=f"Account accessible, {len(prices)} instrument(s)",
                    )
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.DEGRADED,
                    latency_ms=round(latency, 1),
                    message="Account accessible but no price data",
                )
            elif response.status_code == 401:
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.UNAVAILABLE,
                    latency_ms=round(latency, 1),
                    message="Invalid API token",
                )
            elif response.status_code == 403:
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.UNAVAILABLE,
                    latency_ms=round(latency, 1),
                    message="Account not authorized",
                )
            else:
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.DEGRADED,
                    latency_ms=round(latency, 1),
                    message=f"HTTP {response.status_code}",
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
        """Fetch historical candles from OANDA REST API."""
        granularity = _TIMEFRAME_MAP.get(timeframe)
        if granularity is None:
            raise ValueError(f"Timeframe {timeframe.value} not supported by OANDA")

        client = await self._get_client()
        url = f"{self._base_url}/accounts/{self._account_id}/instruments/{self._instrument}/candles"

        params = {
            "granularity": granularity,
            "count": min(limit, 5000),
            "price": "MBA",  # Mid, Bid, Ask
        }

        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        candles = []
        for candle_data in data.get("candles", []):
            try:
                if candle_data.get("mid"):
                    candle = self._parse_oanda_candle(
                        candle_data["mid"],
                        instrument,
                        timeframe,
                        is_closed=candle_data.get("complete", False),
                    )
                    candles.append(candle)
            except (ValueError, KeyError) as e:
                logger.warning("Skipping malformed OANDA candle: %s", e)
                continue

        return candles

    async def fetch_latest_price(
        self,
        instrument: Instrument,
    ) -> Optional[LatestPrice]:
        """Fetch latest price from OANDA pricing endpoint."""
        try:
            client = await self._get_client()
            url = f"{self._base_url}/accounts/{self._account_id}/pricing"
            response = await client.get(
                url,
                params={"instruments": self._instrument},
            )
            response.raise_for_status()
            data = response.json()

            prices = data.get("prices", [])
            if not prices:
                return None

            price_data = prices[0]
            bid = float(price_data.get("bids", [{}])[0].get("price", 0)) if price_data.get("bids") else None
            ask = float(price_data.get("asks", [{}])[0].get("price", 0)) if price_data.get("asks") else None
            mid = (bid + ask) / 2 if bid and ask else bid or ask or 0

            return LatestPrice(
                instrument=instrument,
                provider_instrument=self._instrument,
                source_type=SourceType.LIVE,
                price=mid,
                bid=bid,
                ask=ask,
                timestamp=self._oanda_timestamp_to_utc(price_data.get("time", datetime.now(timezone.utc).isoformat())),
                source=self.name,
                is_forming=True,
            )
        except Exception as e:
            logger.warning("Failed to fetch OANDA latest price: %s", e)
            return None

    async def fetch_latest_candle(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> Optional[NormalizedCandle]:
        """Fetch the most recent candle from OANDA."""
        candles = await self.fetch_historical_candles(instrument, timeframe, limit=1)
        return candles[0] if candles else None

    async def stream_pricing(self) -> AsyncIterator[dict]:
        """
        Stream real-time pricing via OANDA SSE endpoint.

        Yields parsed JSON dicts from the SSE stream.
        Each dict contains: type, time, bids, asks, closeoutBid, closeoutAsk, tradeable.
        """
        client = await self._get_client()
        url = f"{self._stream_url}/accounts/{self._account_id}/pricing/stream"
        params = {"instruments": self._instrument}

        logger.info("Connecting to OANDA pricing stream: %s", self._instrument)

        async with client.stream("GET", url, params=params) as response:
            response.raise_for_status()
            buffer = ""

            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line or line.startswith(":"):
                        # SSE comment or empty line
                        continue

                    if line.startswith("event:"):
                        # Event type line — next data line has the payload
                        continue

                    if line.startswith("data:"):
                        payload = line[len("data:"):].strip()
                        if not payload:
                            continue
                        try:
                            data = json.loads(payload)
                            yield data
                        except json.JSONDecodeError as e:
                            logger.warning("Failed to parse OANDA SSE data: %s", e)
                            continue

    async def stream_candles(self, timeframe: Timeframe) -> AsyncIterator[dict]:
        """
        Stream real-time candle updates via OANDA SSE endpoint.

        Yields parsed JSON dicts with candle data.
        """
        granularity = _TIMEFRAME_MAP.get(timeframe)
        if granularity is None:
            raise ValueError(f"Timeframe {timeframe.value} not supported by OANDA streaming")

        client = await self._get_client()
        url = f"{self._stream_url}/accounts/{self._account_id}/candles/stream"
        params = {
            "instrument": self._instrument,
            "granularity": granularity,
        }

        logger.info("Connecting to OANDA candle stream: %s %s", self._instrument, granularity)

        async with client.stream("GET", url, params=params) as response:
            response.raise_for_status()
            buffer = ""

            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line or line.startswith(":"):
                        continue

                    if line.startswith("data:"):
                        payload = line[len("data:"):].strip()
                        if not payload:
                            continue
                        try:
                            data = json.loads(payload)
                            yield data
                        except json.JSONDecodeError as e:
                            logger.warning("Failed to parse OANDA candle SSE data: %s", e)
                            continue
