"""
Scalping Arise — Decision State Machine

Strict state machine for FinalDecision lifecycle transitions.
Every transition is validated — invalid transitions raise StateTransitionError.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.decision.models import (
    AuditAction,
    AuditEntry,
    FinalDecision,
    FinalDecisionState,
)

logger = logging.getLogger(__name__)


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: FinalDecisionState, to_state: FinalDecisionState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition: {from_state.value} → {to_state.value}"
        )


# Valid transitions: from_state → set of allowed to_states
_VALID_TRANSITIONS: dict[FinalDecisionState, set[FinalDecisionState]] = {
    FinalDecisionState.EVALUATING: {
        FinalDecisionState.WAITING,
        FinalDecisionState.ACTIONABLE,
        FinalDecisionState.NO_TRADE,
        FinalDecisionState.BLOCKED,
        FinalDecisionState.INVALID,
        FinalDecisionState.EXPIRED,
    },
    FinalDecisionState.WAITING: {
        FinalDecisionState.ACTIONABLE,
        FinalDecisionState.NO_TRADE,
        FinalDecisionState.BLOCKED,
        FinalDecisionState.INVALID,
        FinalDecisionState.EXPIRED,
    },
    FinalDecisionState.ACTIONABLE: {
        FinalDecisionState.EXPIRED,
        FinalDecisionState.INVALIDATED,
    },
    FinalDecisionState.NO_TRADE: {
        FinalDecisionState.EXPIRED,
        FinalDecisionState.INVALIDATED,
    },
    FinalDecisionState.BLOCKED: {
        FinalDecisionState.EXPIRED,
        FinalDecisionState.INVALIDATED,
    },
    FinalDecisionState.INVALID: {
        FinalDecisionState.EXPIRED,
        FinalDecisionState.INVALIDATED,
    },
    # Terminal states — no transitions out
    FinalDecisionState.EXPIRED: set(),
    FinalDecisionState.INVALIDATED: set(),
}


def get_valid_transitions(state: FinalDecisionState) -> set[FinalDecisionState]:
    """Get the set of valid target states from the given state."""
    return _VALID_TRANSITIONS.get(state, set()).copy()


def can_transition(from_state: FinalDecisionState, to_state: FinalDecisionState) -> bool:
    """Check whether a transition is valid without raising."""
    return to_state in _VALID_TRANSITIONS.get(from_state, set())


def validate_transition(from_state: FinalDecisionState, to_state: FinalDecisionState) -> None:
    """
    Validate a state transition. Raises StateTransitionError if invalid.

    Args:
        from_state: Current state.
        to_state: Desired target state.

    Raises:
        StateTransitionError: If the transition is not allowed.
    """
    if not can_transition(from_state, to_state):
        raise StateTransitionError(from_state, to_state)


def transition_decision(
    decision: FinalDecision,
    new_state: FinalDecisionState,
    *,
    reason: Optional[str] = None,
) -> AuditEntry:
    """
    Transition a FinalDecision to a new state.

    Validates the transition, updates the decision in-place, and returns
    an AuditEntry recording the transition.

    Args:
        decision: The decision to transition.
        new_state: The target state.
        reason: Optional human-readable reason for the transition.

    Returns:
        AuditEntry recording this transition.

    Raises:
        StateTransitionError: If the transition is invalid.
    """
    old_state = decision.state
    validate_transition(old_state, new_state)

    decision.state = new_state
    decision.updated_at = datetime.now(timezone.utc)

    # Build audit entry
    details: dict = {}
    if reason:
        details["reason"] = reason

    entry = AuditEntry(
        decision_id=decision.decision_id,
        action=AuditAction.STATE_TRANSITION,
        state_before=old_state,
        state_after=new_state,
        details=details,
    )

    logger.debug(
        "Decision %s: %s → %s (reason=%s)",
        decision.decision_id[:8],
        old_state.value,
        new_state.value,
        reason or "none",
    )

    return entry


def is_terminal(state: FinalDecisionState) -> bool:
    """Check whether a state is terminal (no transitions out)."""
    return len(_VALID_TRANSITIONS.get(state, set())) == 0


def transition_to_terminal(
    decision: FinalDecision,
    terminal_state: FinalDecisionState,
    *,
    reason: str = "",
) -> AuditEntry:
    """
    Transition to a terminal state (EXPIRED or INVALIDATED).

    Convenience wrapper that validates the terminal state is actually terminal.

    Args:
        decision: The decision to transition.
        terminal_state: Must be EXPIRED or INVALIDATED.
        reason: Human-readable reason.

    Returns:
        AuditEntry recording the transition.

    Raises:
        StateTransitionError: If the target is not terminal or transition is invalid.
    """
    if not is_terminal(terminal_state):
        raise ValueError(f"{terminal_state.value} is not a terminal state")
    return transition_decision(decision, terminal_state, reason=reason)
