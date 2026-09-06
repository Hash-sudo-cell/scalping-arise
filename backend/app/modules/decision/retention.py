"""
Scalping Arise — Data Retention

Enforces retention policies on decision history and audit trail.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.modules.decision.config import DecisionEngineSettings
from app.modules.decision.models import FinalDecision, FinalDecisionState, RetentionPolicy

logger = logging.getLogger(__name__)


def is_retention_eligible(
    decision: FinalDecision,
    max_age_days: int = 30,
) -> bool:
    """
    Check if a decision is eligible for retention cleanup.

    A decision is eligible if:
    1. It is in a terminal state (EXPIRED, INVALIDATED), AND
    2. Its last update (or creation) is older than max_age_days.
    """
    terminal_states = {
        FinalDecisionState.EXPIRED,
        FinalDecisionState.INVALIDATED,
    }
    if decision.state not in terminal_states:
        return False

    ref_time = decision.updated_at or decision.created_at
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return ref_time < cutoff


def cleanup_retention(
    decisions: list[FinalDecision],
    max_age_days: int = 30,
    max_entries: int = 10000,
) -> tuple[list[FinalDecision], int]:
    """
    Clean up decisions based on retention policy.

    Removes:
    1. Terminal decisions older than max_age_days
    2. Excess decisions beyond max_entries (keeps newest)

    Args:
        decisions: List of all decisions (modified in-place).
        max_age_days: Maximum age for terminal decisions.
        max_entries: Maximum total decisions to keep.

    Returns:
        Tuple of (surviving decisions, number removed).
    """
    original_count = len(decisions)
    to_remove: set[int] = set()

    # Phase 1: Remove expired terminal decisions
    for i, decision in enumerate(decisions):
        if is_retention_eligible(decision, max_age_days):
            to_remove.add(i)

    # Phase 2: If still over max_entries, remove oldest non-terminal
    surviving = [d for i, d in enumerate(decisions) if i not in to_remove]
    if len(surviving) > max_entries:
        # Sort by created_at ascending (oldest first)
        surviving.sort(key=lambda d: d.created_at)
        excess = len(surviving) - max_entries
        # Remove the oldest non-terminal decisions
        removed = 0
        for d in surviving:
            if removed >= excess:
                break
            terminal_states = {FinalDecisionState.EXPIRED, FinalDecisionState.INVALIDATED}
            if d.state not in terminal_states:
                # Find and remove from original list
                for i, orig in enumerate(decisions):
                    if orig.decision_id == d.decision_id:
                        to_remove.add(i)
                        removed += 1
                        break

    # Build surviving list
    surviving = [d for i, d in enumerate(decisions) if i not in to_remove]
    removed_count = original_count - len(surviving)

    return surviving, removed_count


def enforce_retention(
    decisions: list[FinalDecision],
    settings: Optional[DecisionEngineSettings] = None,
) -> int:
    """
    Enforce retention policy on the decision list.

    Modifies the list in-place and returns the number removed.
    """
    from app.modules.decision.config import get_decision_engine_settings

    cfg = settings or get_decision_engine_settings()
    _, removed = cleanup_retention(
        decisions,
        max_age_days=cfg.retention_days,
        max_entries=cfg.decision_history_max_size,
    )
    if removed > 0:
        logger.info("Retention cleanup: removed %d decisions", removed)
    return removed
