"""
Scalping Arise — Signal Expiration

TTL-based signal expiration management. Checks active signals against
their configured TTL and transitions expired signals to EXPIRED state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.signal_engine.models import SignalRecord, SignalState
from app.modules.signal_engine.state_machine import SignalStateMachine

logger = logging.getLogger(__name__)


class SignalExpirationManager:
    """
    Manages TTL-based signal expiration.

    On each evaluation cycle, checks all active signals against their
    configured TTL and expires those that have exceeded it.
    """

    def __init__(
        self,
        state_machine: SignalStateMachine,
        default_ttl_seconds: int = 300,
    ) -> None:
        self._state_machine = state_machine
        self._default_ttl = default_ttl_seconds

    @property
    def default_ttl_seconds(self) -> int:
        return self._default_ttl

    def check_expiration(self, record: SignalRecord) -> bool:
        """
        Check if a single signal has exceeded its TTL.

        Returns True if the signal was expired, False otherwise.
        """
        if record.state not in (SignalState.ACTIVE, SignalState.CONFIRMED, SignalState.QUALIFIED, SignalState.CANDIDATE):
            return False

        now = datetime.now(timezone.utc)
        elapsed = (now - record.created_at).total_seconds()
        ttl = record.ttl_seconds or self._default_ttl

        if elapsed > ttl:
            reason = f"TTL expired: {elapsed:.0f}s elapsed, limit {ttl}s"
            return self._state_machine.expire(record, reason)
        return False

    def check_all(self) -> list[SignalRecord]:
        """
        Check all tracked signals for expiration.

        Returns list of signals that were expired.
        """
        expired: list[SignalRecord] = []
        for record in self._state_machine.get_all():
            if self.check_expiration(record):
                expired.append(record)
        if expired:
            logger.info("Expired %d signals due to TTL", len(expired))
        return expired

    def get_expiring_soon(self, within_seconds: int = 60) -> list[SignalRecord]:
        """
        Get signals that will expire within the given time window.

        Useful for preemptive handling (e.g. warn downstream consumers).
        """
        now = datetime.now(timezone.utc)
        expiring: list[SignalRecord] = []

        for record in self._state_machine.get_active():
            elapsed = (now - record.created_at).total_seconds()
            ttl = record.ttl_seconds or self._default_ttl
            remaining = ttl - elapsed

            if 0 < remaining <= within_seconds:
                expiring.append(record)

        return expiring

    def extend_ttl(self, record: SignalRecord, additional_seconds: int) -> bool:
        """
        Extend a signal's TTL by additional seconds.

        Returns True if the extension was applied.
        """
        if record.state in (SignalState.EXPIRED, SignalState.INVALIDATED):
            return False
        record.ttl_seconds += additional_seconds
        logger.info(
            "Extended TTL for signal %s by %ds (new TTL: %ds)",
            record.signal_id, additional_seconds, record.ttl_seconds,
        )
        return True

    def set_ttl(self, record: SignalRecord, ttl_seconds: int) -> None:
        """Override a signal's TTL."""
        record.ttl_seconds = ttl_seconds
