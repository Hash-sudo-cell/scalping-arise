"""
Scalping Arise — Emergency Kill Switch

Provides an immediate disable mechanism for the entire decision engine.
When active, all decisions are BLOCKED regardless of gate results.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class EmergencyController:
    """
    Thread-safe emergency disable controller.

    Uses a lock-protected boolean flag. When active, the gate engine
    short-circuits all evaluations to BLOCKED.
    """

    def __init__(self, initial_state: bool = False) -> None:
        self._lock = threading.Lock()
        self._disabled = initial_state
        self._toggled_at: Optional[datetime] = None
        self._toggle_count = 0
        self._last_reason = ""

    @property
    def is_disabled(self) -> bool:
        """Check if emergency disable is active."""
        with self._lock:
            return self._disabled

    @property
    def toggled_at(self) -> Optional[datetime]:
        """When the emergency was last toggled."""
        with self._lock:
            return self._toggled_at

    @property
    def toggle_count(self) -> int:
        """Total number of emergency toggles."""
        with self._lock:
            return self._toggle_count

    @property
    def last_reason(self) -> str:
        """Reason for the last emergency toggle."""
        with self._lock:
            return self._last_reason

    def disable(self, reason: str = "Manual emergency disable") -> None:
        """
        Activate emergency disable.

        Args:
            reason: Why the emergency was activated.
        """
        with self._lock:
            self._disabled = True
            self._toggled_at = datetime.now(timezone.utc)
            self._toggle_count += 1
            self._last_reason = reason
        logger.warning("EMERGENCY DISABLE ACTIVATED: %s", reason)

    def enable(self, reason: str = "Manual emergency enable") -> None:
        """
        Deactivate emergency disable.

        Args:
            reason: Why the emergency was deactivated.
        """
        with self._lock:
            self._disabled = False
            self._toggled_at = datetime.now(timezone.utc)
            self._toggle_count += 1
            self._last_reason = reason
        logger.info("EMERGENCY DISABLE DEACTIVATED: %s", reason)

    def toggle(self, disable: bool, reason: str = "") -> bool:
        """
        Toggle the emergency state.

        Args:
            disable: True to disable, False to enable.
            reason: Reason for the toggle.

        Returns:
            The new disabled state.
        """
        if disable:
            self.disable(reason or "Emergency toggle to disable")
        else:
            self.enable(reason or "Emergency toggle to enable")
        return self._disabled

    def get_status(self) -> dict:
        """Get the current emergency status."""
        with self._lock:
            return {
                "disabled": self._disabled,
                "toggled_at": self._toggled_at.isoformat() if self._toggled_at else None,
                "toggle_count": self._toggle_count,
                "last_reason": self._last_reason,
            }
