"""
Scalping Arise — yfinance Provider Adapter

Fallback market data provider. Uses yfinance (Yahoo Finance)
for XAU/USD data. No API key required.

Ticker: GC=F (Gold Futures) or XAUUSD=X (XAU/USD spot).
Intervals: 1m, 2m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo.
Limitations:
    - 1m data: last 7 days only
    - Intraday (<1d): last 60 days only
    - 3m not natively supported (derived from 1m)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
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

# Mapping: internal timeframe -> yfinance interval string
_YF_INTERVAL_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M3: "1m",  # Derived: fetch 1m, aggregate to 3m
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H4: "1h",  # Derived: fetch 1h, aggregate to 4h
    Timeframe.D1: "1d",
    Timeframe.W1: "1wk",
    Timeframe.MO1: "1mo",
}

# How many source candles needed for derived timeframe
_DERIVATION_factors: dict[Timeframe, int] = {
    Timeframe.M3: 3,   # 3 x 1m -> 3m
    Timeframe.H4: 4,   # 4 x 1h -> 4h
}


class YFinanceProvider:
    """yfinance (Yahoo Finance) market data adapter."""

    def __init__(
        self,
        symbol_map: Optional[dict[Instrument, str]] = None,
        timeout: float = 15.0,
    ) -> None:
        self._symbol_map = symbol_map or {Instrument.XAU_USD: "GC=F"}
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "yfinance"

    def map_symbol(self, instrument: Instrument) -> str:
        return self._symbol_map.get(instrument, instrument.value)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name=self.name,
            supported_instruments=[Instrument.XAU_USD],
            timeframe_capabilities={
                Timeframe.M1: TimeframeCapability.NATIVE,
                Timeframe.M3: TimeframeCapability.DERIVED,
                Timeframe.M5: TimeframeCapability.NATIVE,
                Timeframe.M15: TimeframeCapability.NATIVE,
                Timeframe.M30: TimeframeCapability.NATIVE,
                Timeframe.H1: TimeframeCapability.NATIVE,
                Timeframe.H4: TimeframeCapability.DERIVED,
                Timeframe.D1: TimeframeCapability.NATIVE,
                Timeframe.W1: TimeframeCapability.NATIVE,
                Timeframe.MO1: TimeframeCapability.NATIVE,
            },
            max_historical_candles=None,  # Depends on timeframe
            requires_api_key=False,
            rate_limit_per_minute=None,
        )

    def _get_yf_interval(self, timeframe: Timeframe) -> str:
        return _YF_INTERVAL_MAP.get(timeframe, "1d")

    def _is_derived(self, timeframe: Timeframe) -> bool:
        return timeframe in _DERIVATION_factors

    def _get_period_for_limit(self, timeframe: Timeframe, limit: int) -> str:
        """Convert a candle limit into a yfinance period string."""
        interval_secs = timeframe.interval_seconds
        total_secs = interval_secs * limit

        if total_secs <= 86400:
            return "1d"
        elif total_secs <= 604800:
            return "5d"
        elif total_secs <= 2_592_000:
            return "1mo"
        elif total_secs <= 7_776_000:
            return "3mo"
        elif total_secs <= 15_552_000:
            return "6mo"
        elif total_secs <= 31_536_000:
            return "1y"
        else:
            return "2y"

    def _parse_yf_timestamp(self, ts) -> datetime:
        """Convert yfinance timestamp to UTC datetime."""
        if hasattr(ts, "to_pydatetime"):
            dt = ts.to_pydatetime()
        elif hasattr(ts, "item"):
            dt = datetime.fromtimestamp(ts.item(), tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        # Normalize to UTC if timezone-aware
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt

    def _df_to_candles(self, df, instrument: Instrument, timeframe: Timeframe) -> list[NormalizedCandle]:
        """Convert a yfinance DataFrame to NormalizedCandle list."""
        # yfinance >=1.7 returns MultiIndex columns (Price, ticker).
        # Flatten so row["Open"] yields a scalar.
        if hasattr(df.columns, "levels") and df.columns.nlevels > 1:
            df = df.droplevel(1, axis=1)

        provider_symbol = self.map_symbol(instrument)
        candles = []
        for idx, row in df.iterrows():
            try:
                ts = self._parse_yf_timestamp(idx)
                candle = NormalizedCandle(
                    instrument=instrument,
                    provider_instrument=provider_symbol,
                    source_type=SourceType.FUTURES_PROXY,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]) if "Volume" in row and row["Volume"] > 0 else None,
                    is_closed=True,
                    source=self.name,
                )
                candles.append(candle)
            except (ValueError, KeyError, TypeError) as e:
                logger.warning("Skipping malformed yfinance row: %s", e)
                continue
        return candles

    def _aggregate_candles(
        self,
        source_candles: list[NormalizedCandle],
        target_timeframe: Timeframe,
        factor: int,
    ) -> list[NormalizedCandle]:
        """Aggregate source candles into higher-timeframe candles."""
        if len(source_candles) < factor:
            return []

        aggregated = []
        for i in range(0, len(source_candles), factor):
            batch = source_candles[i : i + factor]
            if len(batch) < factor:
                break  # Skip incomplete final batch

            candle = NormalizedCandle(
                instrument=batch[0].instrument,
                provider_instrument=batch[0].provider_instrument,
                source_type=batch[0].source_type,
                timeframe=target_timeframe,
                timestamp=batch[0].timestamp,
                open=batch[0].open,
                high=max(c.high for c in batch),
                low=min(c.low for c in batch),
                close=batch[-1].close,
                volume=sum(c.volume for c in batch if c.volume) if any(c.volume for c in batch) else None,
                is_closed=True,
                source=self.name,
            )
            aggregated.append(candle)

        return aggregated

    async def health_check(self) -> ProviderHealth:
        """Check yfinance availability by attempting a small fetch."""
        start = time.monotonic()
        try:
            import yfinance as yf

            ticker = self.map_symbol(Instrument.XAU_USD)
            data = yf.download(
                tickers=ticker,
                period="1d",
                interval="1d",
                progress=False,
            )
            latency = (time.monotonic() - start) * 1000

            if data is not None and not data.empty:
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.HEALTHY,
                    latency_ms=round(latency, 1),
                    message="Download endpoint responding",
                )
            else:
                return ProviderHealth(
                    provider_name=self.name,
                    status=ProviderHealthStatus.DEGRADED,
                    latency_ms=round(latency, 1),
                    message="Empty response from Yahoo Finance",
                )
        except ImportError:
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderHealthStatus.UNAVAILABLE,
                message="yfinance package not installed",
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
        """Fetch historical candles from yfinance."""
        try:
            import yfinance as yf
        except ImportError:
            raise RuntimeError("yfinance package not installed")

        ticker = self.map_symbol(instrument)
        yf_interval = self._get_yf_interval(timeframe)
        period = self._get_period_for_limit(timeframe, limit)

        # For derived timeframes, fetch more source data
        if self._is_derived(timeframe):
            factor = _DERIVATION_factors[timeframe]
            extended_limit = limit * factor + factor  # Extra for aggregation
            period = self._get_period_for_limit(Timeframe.M1 if timeframe == Timeframe.M3 else Timeframe.H1, extended_limit)

        logger.debug(
            "yfinance download: ticker=%s interval=%s period=%s",
            ticker, yf_interval, period,
        )

        data = yf.download(
            tickers=ticker,
            period=period,
            interval=yf_interval,
            progress=False,
        )

        if data is None or data.empty:
            return []

        candles = self._df_to_candles(data, instrument, timeframe)

        # Derive higher timeframe if needed
        if self._is_derived(timeframe):
            factor = _DERIVATION_factors[timeframe]
            candles = self._aggregate_candles(candles, timeframe, factor)

        # Return only the requested number
        return candles[-limit:] if len(candles) > limit else candles

    async def fetch_latest_price(
        self,
        instrument: Instrument,
    ) -> Optional[LatestPrice]:
        """Fetch latest price from yfinance."""
        try:
            import yfinance as yf

            ticker = self.map_symbol(instrument)
            data = yf.download(
                tickers=ticker,
                period="1d",
                interval="1m",
                progress=False,
            )

            if data is None or data.empty:
                return None

            # yfinance >=1.7 MultiIndex columns -- flatten
            if hasattr(data.columns, "levels") and data.columns.nlevels > 1:
                data = data.droplevel(1, axis=1)

            last_row = data.iloc[-1]
            last_idx = data.index[-1]

            provider_symbol = self.map_symbol(instrument)
            return LatestPrice(
                instrument=instrument,
                provider_instrument=provider_symbol,
                source_type=SourceType.FUTURES_PROXY,
                price=float(last_row["Close"]),
                timestamp=self._parse_yf_timestamp(last_idx),
                source=self.name,
                is_forming=True,
            )
        except Exception as e:
            logger.warning("Failed to fetch latest price from yfinance: %s", e)
            return None

    async def fetch_latest_candle(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> Optional[NormalizedCandle]:
        """Fetch the most recent candle from yfinance."""
        candles = await self.fetch_historical_candles(instrument, timeframe, limit=1)
        return candles[0] if candles else None
