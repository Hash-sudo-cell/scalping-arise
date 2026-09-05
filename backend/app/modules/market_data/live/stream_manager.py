"""
Scalping Arise — Live Stream Manager

Central orchestrator for live market data streaming. Manages:
- OANDA SSE pricing/candle streams (primary live source)
- TradingView snapshots (secondary verification)
- Multi-timeframe candle lifecycle (1m, 5m, 15m)
- Connection health monitoring and reconnection
- Price divergence detection and verification

Architecture:
    OANDA SSE Stream → LiveStreamManager → CandleLifecycle per TF → Cache + Downstream
    TradingView Poll  → Price Verification → Consistency Check

The LiveStreamManager is instantiated during app startup and shut
down cleanly during app shutdown. It maintains state for all active
timeframes and exposes a thread-safe interface for querying live data.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from app.modules.market_data.config import MarketDataSettings, get_market_data_settings
from app.modules.market_data.live.candle_lifecycle import CandleLifecycle
from app.modules.market_data.live.connection_health import ConnectionHealthManager
from app.modules.market_data.models import (
    CandleState,
    ConnectionState,
    Instrument,
    LatestPrice,
    LiveCandleState,
    LivePriceState,
    LiveStreamStatus,
    NormalizedCandle,
    SourceType,
    Timeframe,
)
from app.modules.market_data.providers.oanda import OandaProvider
from app.modules.market_data.providers.tradingview import TradingViewProvider

logger = logging.getLogger(__name__)


class LiveStreamManager:
    """
    Manages live streaming from OANDA with TradingView verification.

    Lifecycle:
        1. start() — initialize providers, begin streaming
        2. Running — processes ticks, manages candle lifecycle
        3. stop() — graceful shutdown, close connections
    """

    def __init__(
        self,
        settings: Optional[MarketDataSettings] = None,
        on_price_update: Optional[Callable[[LivePriceState], None]] = None,
        on_candle_closed: Optional[Callable[[NormalizedCandle], None]] = None,
    ) -> None:
        self._settings = settings or get_market_data_settings()
        self._on_price_update = on_price_update
        self._on_candle_closed = on_candle_closed

        # Providers
        self._oanda = OandaProvider(
            account_id=self._settings.oanda_account_id,
            api_token=self._settings.oanda_api_token,
            base_url=self._settings.oanda_rest_url,
            stream_url=self._settings.oanda_stream_url,
            instrument=self._settings.oanda_instrument,
        )
        self._tradingview = TradingViewProvider(
            symbol=self._settings.tv_symbol,
            username=self._settings.tv_username,
            password=self._settings.tv_password,
        )

        # Connection health
        self._health = ConnectionHealthManager(self._settings)

        # Parse active timeframes
        self._active_timeframes: list[Timeframe] = []
        for tf_str in self._settings.live_stream_timeframes:
            try:
                self._active_timeframes.append(Timeframe(tf_str))
            except ValueError:
                logger.warning("Invalid live timeframe: %s", tf_str)

        # Candle lifecycle per timeframe
        self._lifecycles: dict[Timeframe, CandleLifecycle] = {}
        for tf in self._active_timeframes:
            self._lifecycles[tf] = CandleLifecycle(Instrument.XAU_USD, tf)

        # Live state
        self._price_state = LivePriceState(instrument=Instrument.XAU_USD)
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # TV verification polling
        self._tv_verify_task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def health(self) -> ConnectionHealthManager:
        return self._health

    @property
    def price_state(self) -> LivePriceState:
        return self._price_state

    async def start(self) -> None:
        """Start live streaming."""
        if self._running:
            logger.warning("LiveStreamManager already running")
            return

        if not self._settings.live_enabled:
            logger.info("Live streaming disabled via config")
            return

        if not self._settings.oanda_account_id or not self._settings.oanda_api_token:
            logger.warning("OANDA credentials not configured — live streaming disabled")
            return

        logger.info(
            "Starting LiveStreamManager: timeframes=%s",
            [tf.value for tf in self._active_timeframes],
        )

        self._running = True
        self._health.start()

        # Start OANDA pricing stream
        self._tasks.append(asyncio.create_task(self._run_oanda_pricing()))

        # Start OANDA candle streams (one per timeframe)
        for tf in self._active_timeframes:
            self._tasks.append(asyncio.create_task(self._run_oanda_candles(tf)))

        # Start TradingView verification polling
        self._tv_verify_task = asyncio.create_task(self._run_tv_verification())

        # Start staleness checker
        self._tasks.append(asyncio.create_task(self._run_staleness_checker()))

    async def stop(self) -> None:
        """Gracefully stop live streaming."""
        if not self._running:
            return

        logger.info("Stopping LiveStreamManager")
        self._running = False

        # Close all forming candles
        for tf, lifecycle in self._lifecycles.items():
            closed = lifecycle.close_current()
            if closed and self._on_candle_closed:
                self._on_candle_closed(closed)

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tv_verify_task and not self._tv_verify_task.done():
            self._tv_verify_task.cancel()

        # Wait for tasks to finish
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Close providers
        await self._oanda.close()
        await self._tradingview.close()

        self._health.stop()
        self._tasks.clear()

        logger.info("LiveStreamManager stopped")

    # -------------------------------------------------------------------------
    # OANDA Streams
    # -------------------------------------------------------------------------

    async def _run_oanda_pricing(self) -> None:
        """Run the OANDA pricing SSE stream."""
        retry_count = 0
        max_retries = self._settings.live_reconnect_max_attempts

        while self._running and retry_count < max_retries:
            try:
                async for tick in self._oanda.stream_pricing():
                    if not self._running:
                        break
                    self._process_price_tick(tick)
                    self._health.record_data_received()
                    retry_count = 0  # Reset on successful data

            except asyncio.CancelledError:
                break
            except Exception as e:
                retry_count += 1
                logger.error(
                    "OANDA pricing stream error (attempt %d/%d): %s",
                    retry_count, max_retries, e,
                )
                self._health.mark_oanda_disconnected(str(e))

                if self._running and retry_count < max_retries:
                    delay = min(
                        self._settings.live_reconnect_base_delay * (2 ** (retry_count - 1)),
                        self._settings.live_reconnect_max_delay,
                    )
                    await asyncio.sleep(delay)

        if retry_count >= max_retries:
            logger.error("OANDA pricing stream: max retries exceeded")
            self._health.mark_oanda_disconnected("Max retries exceeded")

    def _process_price_tick(self, tick: dict) -> None:
        """Process a pricing tick from OANDA SSE."""
        if tick.get("type") != "PRICE":
            return

        try:
            bids = tick.get("bids", [])
            asks = tick.get("asks", [])

            bid = float(bids[0]["price"]) if bids else None
            ask = float(asks[0]["price"]) if asks else None
            mid = (bid + ask) / 2 if bid and ask else bid or ask or 0

            timestamp = self._oanda._oanda_timestamp_to_utc(tick["time"])

            self._price_state = LivePriceState(
                instrument=Instrument.XAU_USD,
                price=mid,
                bid=bid,
                ask=ask,
                spread=round(ask - bid, 4) if bid and ask else None,
                timestamp=timestamp,
                source="oanda",
                tv_price=self._price_state.tv_price,
                tv_timestamp=self._price_state.tv_timestamp,
                price_divergence_pct=self._price_state.price_divergence_pct,
                is_verified=self._price_state.is_verified,
            )

            # Update all candle lifecycles with this tick
            for tf, lifecycle in self._lifecycles.items():
                closed_candle = lifecycle.update(
                    tick_timestamp=timestamp,
                    open_price=mid,
                    high=mid,
                    low=mid,
                    close=mid,
                )
                if closed_candle and self._on_candle_closed:
                    self._on_candle_closed(closed_candle)

            if self._on_price_update:
                self._on_price_update(self._price_state)

        except Exception as e:
            logger.warning("Failed to process price tick: %s", e)

    async def _run_oanda_candles(self, timeframe: Timeframe) -> None:
        """Run an OANDA candle stream for a specific timeframe."""
        retry_count = 0
        max_retries = self._settings.live_reconnect_max_attempts

        while self._running and retry_count < max_retries:
            try:
                async for candle_data in self._oanda.stream_candles(timeframe):
                    if not self._running:
                        break
                    self._process_candle_tick(timeframe, candle_data)
                    self._health.record_data_received()
                    retry_count = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                retry_count += 1
                logger.error(
                    "OANDA %s candle stream error (attempt %d/%d): %s",
                    timeframe.value, retry_count, max_retries, e,
                )

                if self._running and retry_count < max_retries:
                    delay = min(
                        self._settings.live_reconnect_base_delay * (2 ** (retry_count - 1)),
                        self._settings.live_reconnect_max_delay,
                    )
                    await asyncio.sleep(delay)

    def _process_candle_tick(self, timeframe: Timeframe, candle_data: dict) -> None:
        """Process a candle tick from OANDA SSE."""
        if candle_data.get("type") != "CANDLE":
            return

        try:
            candle_info = candle_data.get("candle", {})
            mid = candle_info.get("mid", {})
            if not mid:
                return

            timestamp = self._oanda._oanda_timestamp_to_utc(mid["time"])
            is_closed = candle_info.get("complete", False)

            lifecycle = self._lifecycles.get(timeframe)
            if lifecycle is None:
                return

            closed_candle = lifecycle.update(
                tick_timestamp=timestamp,
                open_price=float(mid["o"]),
                high=float(mid["h"]),
                low=float(mid["l"]),
                close=float(mid["c"]),
                volume=float(mid.get("v", 0)),
            )

            if closed_candle and self._on_candle_closed:
                self._on_candle_closed(closed_candle)

        except Exception as e:
            logger.warning("Failed to process %s candle tick: %s", timeframe.value, e)

    # -------------------------------------------------------------------------
    # TradingView Verification
    # -------------------------------------------------------------------------

    async def _run_tv_verification(self) -> None:
        """Periodically fetch TradingView price for verification."""
        # Connect to TradingView
        connected = await self._tradingview.connect()
        if connected:
            self._health.mark_tv_connected()
        else:
            logger.warning("TradingView unavailable — verification disabled")
            return

        while self._running:
            try:
                await asyncio.sleep(30)  # Verify every 30 seconds

                if not self._tradingview.is_connected:
                    continue

                tv_price_data = await self._tradingview.fetch_latest_price(Instrument.XAU_USD)
                if tv_price_data is None:
                    continue

                oanda_price = self._price_state.price
                tv_price = tv_price_data.price

                is_consistent, divergence_pct = self._tradingview.verify_price(
                    oanda_price,
                    tv_price,
                    tolerance_pct=self._settings.live_price_verification_tolerance_pct,
                )

                self._price_state.tv_price = tv_price
                self._price_state.tv_timestamp = tv_price_data.timestamp
                self._price_state.price_divergence_pct = divergence_pct
                self._price_state.is_verified = is_consistent

                if not is_consistent:
                    logger.warning(
                        "Price divergence: OANDA=%.2f TV=%.2f (%.4f%%)",
                        oanda_price, tv_price, divergence_pct,
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("TV verification error: %s", e)
                await asyncio.sleep(10)

    # -------------------------------------------------------------------------
    # Staleness Checker
    # -------------------------------------------------------------------------

    async def _run_staleness_checker(self) -> None:
        """Periodically check for stale data."""
        while self._running:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                self._health.check_staleness()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Staleness check error: %s", e)

    # -------------------------------------------------------------------------
    # Query Interface
    # -------------------------------------------------------------------------

    def get_forming_candle(self, timeframe: Timeframe) -> Optional[NormalizedCandle]:
        """Get the current forming candle for a timeframe."""
        lifecycle = self._lifecycles.get(timeframe)
        if lifecycle is None:
            return None
        return lifecycle.current_candle

    def get_closed_candles(self, timeframe: Timeframe, limit: int = 100) -> list[NormalizedCandle]:
        """
        Get recently closed candles from the cache.

        Note: This returns candles from the cache, not from the lifecycle
        directly. Closed candles are pushed to cache by the on_candle_closed
        callback.
        """
        # This will be wired to the cache in the integration step
        return []

    def get_status(self) -> LiveStreamStatus:
        """Get current live stream status."""
        candle_states = {}
        for tf, lifecycle in self._lifecycles.items():
            candle_states[tf.value] = lifecycle.state.value

        return LiveStreamStatus(
            connection_state=self._health.state,
            oanda_connected=self._health.oanda_connected,
            tv_connected=self._health.tv_connected,
            active_timeframes=[tf.value for tf in self._active_timeframes],
            last_price=self._price_state if self._price_state.price > 0 else None,
            candle_states=candle_states,
            reconnect_attempts=self._health.reconnect_attempts,
            last_error=self._health.last_error,
            started_at=self._health.started_at,
            last_data_at=self._health.last_data_at,
        )

    def get_lifecycle(self, timeframe: Timeframe) -> Optional[CandleLifecycle]:
        """Get the candle lifecycle manager for a timeframe."""
        return self._lifecycles.get(timeframe)
