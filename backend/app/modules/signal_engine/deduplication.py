"""
Scalping Arise — Signal Deduplication

Prevents duplicate signals within a configurable time window.
Uses a hash-based key derived from instrument, direction, strategy IDs,
and a time bucket to identify potential duplicates.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.modules.signal_engine.models import (
    DeduplicationEntry,
    DecisionType,
    SignalDirection,
    SignalRecord,
)

logger = logging.getLogger(__name__)


def _compute_dedup_key(
    instrument: str,
    direction: SignalDirection,
    decision: DecisionType,
    strategy_ids: list[str],
    window_seconds: int,
) -> str:
    """
    Compute a deduplication key from signal characteristics.

    The key is a stable hash of:
    - instrument (canonical)
    - direction/decision
    - sorted strategy IDs
    - time bucket (floor to window_seconds)

    Signals with the same key within the window are considered duplicates.
    """
    now = datetime.now(timezone.utc)
    time_bucket = int(now.timestamp()) // max(window_seconds, 1)

    raw = f"{instrument}|{direction.value}|{decision.value}|{'|'.join(sorted(strategy_ids))}|{time_bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class SignalDeduplicator:
    """
    Hash-based signal deduplication.

    Maintains a time-windowed cache of dedup keys. When a new signal
    is evaluated, its key is checked against the cache. If a match
    exists within the dedup window, the signal is blocked as a duplicate.
    """

    def __init__(self, window_seconds: int = 60) -> None:
        self._window = timedelta(seconds=window_seconds)
        self._entries: dict[str, DeduplicationEntry] = {}
        self._window_seconds = window_seconds

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def compute_key(
        self,
        instrument: str,
        direction: SignalDirection,
        decision: DecisionType,
        strategy_ids: list[str],
    ) -> str:
        """Compute a dedup key for the given signal characteristics."""
        return _compute_dedup_key(
            instrument, direction, decision, strategy_ids, self._window_seconds,
        )

    def is_duplicate(
        self,
        instrument: str,
        direction: SignalDirection,
        decision: DecisionType,
        strategy_ids: list[str],
        exclude_signal_id: Optional[str] = None,
    ) -> bool:
        """
        Check if a signal would be a duplicate within the dedup window.

        Returns True if a matching signal was already recorded within the window.
        """
        if decision == DecisionType.NO_TRADE:
            return False  # NO_TRADE signals are never duplicates

        key = self.compute_key(instrument, direction, decision, strategy_ids)

        # Check if key exists and hasn't expired
        entry = self._entries.get(key)
        if entry is None:
            return False

        # Check if the entry is still within the dedup window
        now = datetime.now(timezone.utc)
        if now > entry.expires_at:
            # Entry expired — not a duplicate
            del self._entries[key]
            return False

        # Check if it's the same signal (allow re-registration)
        if exclude_signal_id and entry.signal_id == exclude_signal_id:
            return False

        logger.info(
            "Duplicate blocked: instrument=%s direction=%s decision=%s (key=%s)",
            instrument, direction.value, decision.value, key[:8],
        )
        return True

    def register(self, record: SignalRecord) -> None:
        """
        Register a signal record for dedup tracking.

        The entry expires after the dedup window.
        """
        if record.decision == DecisionType.NO_TRADE:
            return  # Don't track NO_TRADE signals

        strategy_ids = [c.strategy_id for c in record.candidates]
        key = self.compute_key(
            record.instrument, record.direction, record.decision, strategy_ids,
        )

        now = datetime.now(timezone.utc)
        self._entries[key] = DeduplicationEntry(
            dedup_key=key,
            signal_id=record.signal_id,
            instrument=record.instrument,
            direction=record.direction,
            decision=record.decision,
            created_at=now,
            expires_at=now + self._window,
        )

        record.dedup_key = key

    def unregister(self, signal_id: str) -> None:
        """Remove a signal from dedup tracking (e.g. on invalidation)."""
        to_remove = [
            key for key, entry in self._entries.items()
            if entry.signal_id == signal_id
        ]
        for key in to_remove:
            del self._entries[key]

    def cleanup_expired(self) -> int:
        """Remove expired dedup entries. Returns count removed."""
        now = datetime.now(timezone.utc)
        expired = [k for k, e in self._entries.items() if now > e.expires_at]
        for k in expired:
            del self._entries[k]
        return len(expired)

    def active_count(self) -> int:
        """Count non-expired dedup entries."""
        now = datetime.now(timezone.utc)
        return sum(1 for e in self._entries.values() if now <= e.expires_at)
