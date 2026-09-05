"""
Scalping Arise — Signal State Machine

Manages the lifecycle of signal records through state transitions:
    NO_SIGNAL → CANDIDATE → QUALIFIED → CONFIRMED → ACTIVE
    Any → EXPIRED (TTL elapsed)
    Any → INVALIDATED (market condition change)

Each transition is tracked with timestamps and reasons for full traceability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.signal_engine.models import (
    DecisionType,
    SignalDirection,
    SignalRecord,
    SignalState,
    StateTransition,
)

logger = logging.getLogger(__name__)

# Valid state transitions
_VALID_TRANSITIONS: dict[SignalState, set[SignalState]] = {
    SignalState.NO_SIGNAL: {SignalState.CANDIDATE},
    SignalState.CANDIDATE: {SignalState.QUALIFIED, SignalState.NO_SIGNAL},
    SignalState.QUALIFIED: {SignalState.CONFIRMED, SignalState.NO_SIGNAL},
    SignalState.CONFIRMED: {SignalState.ACTIVE, SignalState.INVALIDATED},
    SignalState.ACTIVE: {SignalState.EXPIRED, SignalState.INVALIDATED},
    SignalState.EXPIRED: set(),  # terminal
    SignalState.INVALIDATED: set(),  # terminal
}

# States that allow a transition to EXPIRED
_EXPIRABLE_STATES = {SignalState.ACTIVE, SignalState.CONFIRMED, SignalState.QUALIFIED, SignalState.CANDIDATE}

# States that allow a transition to INVALIDATED
_INVALIDATABLE_STATES = {SignalState.ACTIVE, SignalState.CONFIRMED, SignalState.QUALIFIED}


class SignalStateMachine:
    """
    Manages signal lifecycle state transitions.

    Enforces valid transitions, tracks timestamps, and maintains
    the state history for each signal record.
    """

    def __init__(self) -> None:
        self._records: dict[str, SignalRecord] = {}

    def register(self, record: SignalRecord) -> None:
        """Register a signal record for state tracking."""
        self._records[record.signal_id] = record

    def get(self, signal_id: str) -> Optional[SignalRecord]:
        """Get a signal record by ID."""
        return self._records.get(signal_id)

    def get_all(self) -> list[SignalRecord]:
        """Get all tracked signal records."""
        return list(self._records.values())

    def get_active(self) -> list[SignalRecord]:
        """Get all signals in active (actionable) states."""
        return [r for r in self._records.values() if r.is_active]

    def get_by_state(self, state: SignalState) -> list[SignalRecord]:
        """Get all signals in a specific state."""
        return [r for r in self._records.values() if r.state == state]

    def transition(
        self,
        record: SignalRecord,
        new_state: SignalState,
        reason: str = "",
    ) -> bool:
        """
        Attempt a state transition on a signal record.

        Returns True if transition was valid and applied, False otherwise.
        """
        old_state = record.state

        # Allow same-state transitions (idempotent)
        if old_state == new_state:
            return True

        # Check if transition is valid
        valid_targets = _VALID_TRANSITIONS.get(old_state, set())
        if new_state not in valid_targets:
            logger.warning(
                "Invalid transition: %s → %s for signal %s",
                old_state.value,
                new_state.value,
                record.signal_id,
            )
            return False

        # Apply transition
        record.state = new_state
        record.state_history.append(StateTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
        ))

        # Update directional fields
        if new_state == SignalState.QUALIFIED:
            record.qualified_at = datetime.now(timezone.utc)
        elif new_state == SignalState.CONFIRMED:
            record.confirmed_at = datetime.now(timezone.utc)
        elif new_state == SignalState.ACTIVE:
            record.activated_at = datetime.now(timezone.utc)
        elif new_state == SignalState.EXPIRED:
            record.expired_at = datetime.now(timezone.utc)
        elif new_state == SignalState.INVALIDATED:
            record.invalidated_at = datetime.now(timezone.utc)

        logger.info(
            "Signal %s: %s → %s (%s)",
            record.signal_id,
            old_state.value,
            new_state.value,
            reason or "no reason",
        )
        return True

    def expire(self, record: SignalRecord, reason: str = "TTL elapsed") -> bool:
        """Transition a signal to EXPIRED state."""
        if record.state not in _EXPIRABLE_STATES:
            return False
        return self.transition(record, SignalState.EXPIRED, reason)

    def invalidate(self, record: SignalRecord, reason: str = "Market condition change") -> bool:
        """Transition a signal to INVALIDATED state."""
        if record.state not in _INVALIDATABLE_STATES:
            return False
        return self.transition(record, SignalState.INVALIDATED, reason)

    def cleanup_terminal(self, max_age_seconds: float = 3600) -> int:
        """
        Remove terminal signal records older than max_age_seconds.

        Returns the number of records removed.
        """
        now = datetime.now(timezone.utc)
        to_remove = []
        for sid, record in self._records.items():
            if record.state in (SignalState.EXPIRED, SignalState.INVALIDATED):
                terminal_time = record.expired_at or record.invalidated_at
                if terminal_time and (now - terminal_time).total_seconds() > max_age_seconds:
                    to_remove.append(sid)
        for sid in to_remove:
            del self._records[sid]
        return len(to_remove)

    def count_active(self) -> int:
        """Count signals in actionable states."""
        return len(self.get_active())

    def can_activate(self, max_active: int) -> bool:
        """Check if we can activate another signal without exceeding the limit."""
        return self.count_active() < max_active
