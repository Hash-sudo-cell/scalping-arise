"""
Scalping Arise — Audit Trail

Immutable decision audit log backed by a ring buffer.
Every state transition, gate evaluation, and lifecycle event is recorded.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from app.modules.decision.models import (
    AuditAction,
    AuditEntry,
    FinalDecision,
    FinalDecisionState,
    GateName,
    GateStatus,
)

logger = logging.getLogger(__name__)


class AuditTrail:
    """
    Immutable audit trail for decision engine operations.

    Uses a ring buffer to bound memory usage while preserving
    the most recent entries.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)
        self._max_entries = max_entries

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def count(self) -> int:
        return len(self._entries)

    def record(self, entry: AuditEntry) -> None:
        """
        Record an audit entry.

        Args:
            entry: The audit entry to record.
        """
        self._entries.append(entry)
        logger.debug(
            "Audit: decision=%s action=%s state=%s→%s",
            entry.decision_id[:8],
            entry.action.value,
            entry.state_before.value if entry.state_before else "-",
            entry.state_after.value if entry.state_after else "-",
        )

    def record_creation(self, decision: FinalDecision) -> None:
        """Record the creation of a new decision."""
        entry = AuditEntry(
            decision_id=decision.decision_id,
            action=AuditAction.CREATED,
            state_after=decision.state,
            details={
                "instrument": decision.instrument,
                "signal_id": decision.signal_id or "",
                "decision_version": decision.decision_version,
            },
        )
        self.record(entry)

    def record_gate(
        self,
        decision: FinalDecision,
        gate: GateName,
        status: GateStatus,
        reason: str = "",
    ) -> None:
        """Record a gate evaluation result."""
        entry = AuditEntry(
            decision_id=decision.decision_id,
            action=AuditAction.GATE_EVALUATED,
            gate=gate,
            gate_status=status,
            details={"reason": reason},
        )
        self.record(entry)

    def record_expiration(self, decision: FinalDecision) -> None:
        """Record a decision expiration."""
        entry = AuditEntry(
            decision_id=decision.decision_id,
            action=AuditAction.EXPIRED,
            state_before=decision.state,
            state_after=FinalDecisionState.EXPIRED,
        )
        self.record(entry)

    def record_invalidation(self, decision: FinalDecision, reason: str = "") -> None:
        """Record a manual invalidation."""
        entry = AuditEntry(
            decision_id=decision.decision_id,
            action=AuditAction.INVALIDATED,
            state_before=decision.state,
            state_after=FinalDecisionState.INVALIDATED,
            details={"reason": reason},
        )
        self.record(entry)

    def record_emergency(self, disabled: bool, reason: str = "") -> None:
        """Record an emergency toggle event."""
        action = AuditAction.EMERGENCY_DISABLE if disabled else AuditAction.EMERGENCY_ENABLE
        entry = AuditEntry(
            decision_id="system",
            action=action,
            details={"disabled": disabled, "reason": reason},
        )
        self.record(entry)

    def get_for_decision(self, decision_id: str) -> list[AuditEntry]:
        """Get all audit entries for a specific decision."""
        return [e for e in self._entries if e.decision_id == decision_id]

    def get_recent(self, limit: int = 50) -> list[AuditEntry]:
        """Get the most recent audit entries."""
        entries = list(self._entries)
        return entries[-limit:]

    def get_all(self) -> list[AuditEntry]:
        """Get all audit entries."""
        return list(self._entries)

    def clear(self) -> int:
        """Clear all audit entries. Returns the number of entries removed."""
        count = len(self._entries)
        self._entries.clear()
        return count
