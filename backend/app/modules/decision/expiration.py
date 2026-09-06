"""
Scalping Arise — Decision Expiration

TTL enforcement and expired decision cleanup.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.modules.decision.models import (
    FinalDecision,
    FinalDecisionState,
)
from app.modules.decision.state_machine import is_terminal, transition_to_terminal

logger = logging.getLogger(__name__)


def set_expiration(
    decision: FinalDecision,
    ttl_seconds: int,
) -> None:
    """
    Set the expiration timestamp on a decision.

    Args:
        decision: The decision to set expiration on.
        ttl_seconds: Time-to-live in seconds from creation.
    """
    decision.ttl_seconds = ttl_seconds
    decision.expires_at = decision.created_at + timedelta(seconds=ttl_seconds)


def is_expired(decision: FinalDecision) -> bool:
    """
    Check whether a decision has expired.

    A decision is expired if:
    1. It has an expires_at timestamp and the current time is past it, OR
    2. It is already in a terminal state (EXPIRED or INVALIDATED).
    """
    if is_terminal(decision.state):
        return decision.state == FinalDecisionState.EXPIRED

    if decision.expires_at is None:
        return False

    now = datetime.now(timezone.utc)
    return now > decision.expires_at


def check_and_expire(decision: FinalDecision) -> Optional[FinalDecisionState]:
    """
    Check if a decision has expired and transition it if so.

    Args:
        decision: The decision to check.

    Returns:
        The new state if expired, or None if still valid.
    """
    if is_expired(decision) and not is_terminal(decision.state):
        transition_to_terminal(
            decision,
            FinalDecisionState.EXPIRED,
            reason="Decision TTL elapsed",
        )
        return FinalDecisionState.EXPIRED

    return None


def cleanup_expired(decisions: list[FinalDecision]) -> int:
    """
    Check a list of decisions and expire any that have passed their TTL.

    Returns the number of decisions that were expired.
    """
    count = 0
    for decision in decisions:
        result = check_and_expire(decision)
        if result is not None:
            count += 1
            logger.debug("Decision %s expired", decision.decision_id[:8])
    return count


def get_remaining_ttl(decision: FinalDecision) -> float:
    """
    Get the remaining TTL for a decision in seconds.

    Returns 0.0 if expired, -1.0 if no expiration set.
    """
    if decision.expires_at is None:
        return -1.0

    if is_terminal(decision.state):
        return 0.0

    now = datetime.now(timezone.utc)
    remaining = (decision.expires_at - now).total_seconds()
    return max(0.0, remaining)
