"""
Scalping Arise — In-Memory Candle Cache

Simple TTL-based cache for recent candles. No persistent storage.
Data is lost on application restart.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Optional

from app.modules.market_data.models import NormalizedCandle

logger = logging.getLogger(__name__)


class CandleCache:
    """
    TTL-based in-memory cache for NormalizedCandles.

    Keyed by (instrument, timeframe). Each entry holds an ordered
    list of candles with a creation timestamp for TTL checks.
    """

    def __init__(
        self,
        enabled: bool = True,
        ttl_seconds: int = 60,
        max_candles: int = 10_000,
    ) -> None:
        self._enabled = enabled
        self._ttl = ttl_seconds
        self._max_candles = max_candles
        self._cache: OrderedDict[str, tuple[float, list[NormalizedCandle]]] = OrderedDict()
        self._total_candles = 0

    def _make_key(self, instrument: str, timeframe: str) -> str:
        return f"{instrument}:{timeframe}"

    def _evict_expired(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired_keys = [
            key for key, (created, _) in self._cache.items()
            if now - created > self._ttl
        ]
        for key in expired_keys:
            _, candles = self._cache.pop(key)
            self._total_candles -= len(candles)

    def _enforce_limit(self) -> None:
        """Enforce max candle count by evicting oldest entries."""
        while self._total_candles > self._max_candles and self._cache:
            _, candles = self._cache.popitem(last=False)
            self._total_candles -= len(candles)

    def get(
        self,
        instrument: str,
        timeframe: str,
        limit: Optional[int] = None,
    ) -> list[NormalizedCandle]:
        """Get cached candles. Returns empty list if expired or missing."""
        if not self._enabled:
            return []

        self._evict_expired()
        key = self._make_key(instrument, timeframe)

        if key not in self._cache:
            return []

        created, candles = self._cache[key]

        # Move to end (most recently accessed)
        self._cache.move_to_end(key)

        if limit:
            return candles[-limit:]
        return list(candles)

    def put(
        self,
        instrument: str,
        timeframe: str,
        candles: list[NormalizedCandle],
    ) -> None:
        """Store candles in cache, replacing any existing entry for this key."""
        if not self._enabled:
            return

        key = self._make_key(instrument, timeframe)

        # Remove old entry if exists
        if key in self._cache:
            _, old_candles = self._cache.pop(key)
            self._total_candles -= len(old_candles)

        self._cache[key] = (time.time(), candles)
        self._total_candles += len(candles)
        self._enforce_limit()

    def update_candle(
        self,
        candle: NormalizedCandle,
    ) -> None:
        """Update or append a single candle (for forming candle updates)."""
        if not self._enabled:
            return

        key = self._make_key(candle.instrument.value, candle.timeframe.value)

        if key in self._cache:
            created, candles = self._cache[key]

            # Find and replace or append
            for i, existing in enumerate(candles):
                if existing.timestamp == candle.timestamp:
                    candles[i] = candle
                    self._cache[key] = (created, candles)
                    self._cache.move_to_end(key)
                    return

            # Not found — append
            candles.append(candle)
            self._total_candles += 1
            self._cache[key] = (created, candles)
            self._cache.move_to_end(key)
        else:
            self.put(candle.instrument.value, candle.timeframe.value, [candle])

    def invalidate(self, instrument: str, timeframe: str) -> None:
        """Remove cached data for a specific instrument/timeframe."""
        key = self._make_key(instrument, timeframe)
        if key in self._cache:
            _, candles = self._cache.pop(key)
            self._total_candles -= len(candles)

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._total_candles = 0

    @property
    def total_candles(self) -> int:
        return self._total_candles

    @property
    def entry_count(self) -> int:
        return len(self._cache)
