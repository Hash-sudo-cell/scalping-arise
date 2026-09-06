"""
Scalping Arise — Monitoring Counters

Thread-safe counters and gauges for the decision engine.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from app.modules.decision.models import MonitoringCounters

logger = logging.getLogger(__name__)


class MonitoringService:
    """
    Thread-safe monitoring counters for the decision engine.

    All mutations are protected by a lock. Counters are monotonically
    increasing (never decrease) except during explicit reset.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters = MonitoringCounters()

    @property
    def counters(self) -> MonitoringCounters:
        """Get a snapshot of the current counters."""
        with self._lock:
            return self._counters.model_copy(deep=True)

    def record_evaluation(
        self,
        *,
        state: str,
        evaluation_ms: float = 0.0,
        gate_failures: Optional[dict[str, int]] = None,
    ) -> None:
        """
        Record a decision evaluation.

        Args:
            state: The final state of the decision.
            evaluation_ms: Total evaluation time.
            gate_failures: Gate name → failure count for this evaluation.
        """
        with self._lock:
            self._counters.total_evaluations += 1
            self._counters.last_evaluation_at = datetime.now(timezone.utc)

            # Update average evaluation time (rolling average)
            n = self._counters.total_evaluations
            old_avg = self._counters.avg_evaluation_ms
            self._counters.avg_evaluation_ms = round(
                old_avg + (evaluation_ms - old_avg) / n, 3
            )

            # State-specific counters
            if state == "actionable":
                self._counters.actionable_decisions += 1
            elif state == "no_trade":
                self._counters.no_trade_decisions += 1
            elif state == "blocked":
                self._counters.blocked_decisions += 1
            elif state == "invalid":
                self._counters.invalid_decisions += 1
            elif state == "expired":
                self._counters.expired_decisions += 1

            # Gate failure counters
            if gate_failures:
                for gate_name, count in gate_failures.items():
                    self._counters.gate_failures[gate_name] = (
                        self._counters.gate_failures.get(gate_name, 0) + count
                    )

    def record_idempotency_hit(self) -> None:
        """Record an idempotency cache hit."""
        with self._lock:
            self._counters.idempotency_cache_hits += 1

    def record_idempotency_miss(self) -> None:
        """Record an idempotency cache miss."""
        with self._lock:
            self._counters.idempotency_cache_misses += 1

    def record_emergency_toggle(self) -> None:
        """Record an emergency disable toggle."""
        with self._lock:
            self._counters.emergency_disable_count += 1

    def record_retention_cleanup(self, count: int = 1) -> None:
        """Record a retention cleanup event."""
        with self._lock:
            self._counters.retention_cleanups += count

    def reset(self) -> None:
        """Reset all counters to zero."""
        with self._lock:
            self._counters = MonitoringCounters()
