"""
Scalping Arise — Connection Health Manager

Monitors live stream connection health, detects stale data,
and manages reconnection with exponential backoff.

States:
    DISCONNECTED → CONNECTING → CONNECTED
    CONNECTED → STALE (no data within threshold)
    CONNECTED → DEGRADED (partial data / TV verification failed)
    STALE/DEGRADED → RECONNECTING (after threshold exceeded)
    RECONNECTING → CONNECTED (on successful reconnect)
    RECONNECTING → DISCONNECTED (after max attempts exceeded)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from app.modules.market_data.config import MarketDataSettings, get_market_data_settings
from app.modules.market_data.models import ConnectionState

logger = logging.getLogger(__name__)


class ConnectionHealthManager:
    """
    Manages connection health state and reconnection logic.

    Uses a deterministic state machine with bounded reconnection
    attempts and exponential backoff.
    """

    def __init__(self, settings: Optional[MarketDataSettings] = None) -> None:
        self._settings = settings or get_market_data_settings()
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._oanda_connected: bool = False
        self._tv_connected: bool = False
        self._last_data_at: Optional[datetime] = None
        self._reconnect_attempts: int = 0
        self._last_error: Optional[str] = None
        self._started_at: Optional[datetime] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._on_state_change: Optional[Callable[[ConnectionState], None]] = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def oanda_connected(self) -> bool:
        return self._oanda_connected

    @property
    def tv_connected(self) -> bool:
        return self._tv_connected

    @property
    def last_data_at(self) -> Optional[datetime]:
        return self._last_data_at

    @property
    def reconnect_attempts(self) -> int:
        return self._reconnect_attempts

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    def set_on_state_change(self, callback: Callable[[ConnectionState], None]) -> None:
        """Set a callback for state changes."""
        self._on_state_change = callback

    def _transition(self, new_state: ConnectionState) -> None:
        """Transition to a new state with logging."""
        old = self._state
        if old == new_state:
            return
        self._state = new_state
        logger.info("Connection state: %s → %s", old.value, new_state.value)
        if self._on_state_change:
            self._on_state_change(new_state)

    def start(self) -> None:
        """Mark the stream manager as started."""
        self._started_at = datetime.now(timezone.utc)
        self._transition(ConnectionState.CONNECTING)

    def mark_oanda_connected(self) -> None:
        """Mark OANDA stream as connected."""
        self._oanda_connected = True
        self._reconnect_attempts = 0
        self._last_error = None
        if self._tv_connected:
            self._transition(ConnectionState.CONNECTED)
        else:
            self._transition(ConnectionState.DEGRADED)

    def mark_oanda_disconnected(self, error: Optional[str] = None) -> None:
        """Mark OANDA stream as disconnected."""
        self._oanda_connected = False
        self._last_error = error
        if not self._tv_connected:
            self._transition(ConnectionState.DISCONNECTED)
        else:
            self._transition(ConnectionState.DEGRADED)

    def mark_tv_connected(self) -> None:
        """Mark TradingView connection as established."""
        self._tv_connected = True
        if self._oanda_connected:
            self._transition(ConnectionState.CONNECTED)
        else:
            self._transition(ConnectionState.DEGRADED)

    def mark_tv_disconnected(self) -> None:
        """Mark TradingView connection as lost."""
        self._tv_connected = False
        if self._oanda_connected:
            self._transition(ConnectionState.DEGRADED)

    def record_data_received(self) -> None:
        """Record that fresh data was received (resets stale timer)."""
        self._last_data_at = datetime.now(timezone.utc)
        if self._state == ConnectionState.STALE:
            if self._oanda_connected:
                self._transition(ConnectionState.CONNECTED)
            else:
                self._transition(ConnectionState.DEGRADED)

    def check_staleness(self) -> bool:
        """
        Check if the stream has gone stale.

        Returns True if data hasn't been received within the threshold.
        """
        if self._last_data_at is None:
            return False

        now = datetime.now(timezone.utc)
        age = (now - self._last_data_at).total_seconds()

        if age > self._settings.live_stale_threshold_seconds:
            if self._state in (ConnectionState.CONNECTED, ConnectionState.DEGRADED):
                self._transition(ConnectionState.STALE)
                logger.warning(
                    "Stream stale: no data for %.1fs (threshold: %ds)",
                    age, self._settings.live_stale_threshold_seconds,
                )
                return True
        return False

    async def start_reconnect(self, reconnect_fn: Callable[[], None]) -> bool:
        """
        Initiate reconnection with exponential backoff.

        Returns True if reconnection was attempted, False if max
        attempts exceeded.
        """
        if self._reconnect_attempts >= self._settings.live_reconnect_max_attempts:
            logger.error(
                "Max reconnection attempts (%d) exceeded. Giving up.",
                self._settings.live_reconnect_max_attempts,
            )
            self._transition(ConnectionState.DISCONNECTED)
            return False

        self._transition(ConnectionState.RECONNECTING)
        self._reconnect_attempts += 1

        # Exponential backoff with cap
        delay = min(
            self._settings.live_reconnect_base_delay * (2 ** (self._reconnect_attempts - 1)),
            self._settings.live_reconnect_max_delay,
        )

        logger.info(
            "Reconnect attempt %d/%d in %.1fs",
            self._reconnect_attempts,
            self._settings.live_reconnect_max_attempts,
            delay,
        )

        await asyncio.sleep(delay)

        try:
            reconnect_fn()
            return True
        except Exception as e:
            self._last_error = str(e)
            logger.error("Reconnect attempt %d failed: %s", self._reconnect_attempts, e)
            return False

    def reset(self) -> None:
        """Reset all health state."""
        self._state = ConnectionState.DISCONNECTED
        self._oanda_connected = False
        self._tv_connected = False
        self._last_data_at = None
        self._reconnect_attempts = 0
        self._last_error = None

    def stop(self) -> None:
        """Stop the health manager and cancel pending reconnects."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        self._transition(ConnectionState.DISCONNECTED)

    def get_status_dict(self) -> dict:
        """Return a JSON-serializable status dictionary."""
        return {
            "connection_state": self._state.value,
            "oanda_connected": self._oanda_connected,
            "tv_connected": self._tv_connected,
            "reconnect_attempts": self._reconnect_attempts,
            "last_error": self._last_error,
            "last_data_at": self._last_data_at.isoformat() if self._last_data_at else None,
            "started_at": self._started_at.isoformat() if self._started_at else None,
        }
