"""
Scalping Arise — In-Memory State Store

Thread-safe singleton that holds all critical state in memory
and delegates persistence to the persistence module.

Services read/write through this store instead of holding their own state.
On shutdown, save_all() flushes to disk. On startup, restore_all() reloads.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.modules.persistence import (
    restore_all,
    save_all_snapshots,
)

logger = logging.getLogger(__name__)


class _StateStore:
    """
    Centralized state store — thread-safe singleton.

    Holds:
      - Decision engine state (history, active decisions, emergency, monitoring)
      - News intelligence strategy states
      - Emergency controller state (standalone quick access)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._base_dir: Optional[Path] = None

        # Decision engine state
        self.decision_history: list[dict] = []
        self.decision_active: list[dict] = []
        self.emergency_disabled: bool = False
        self.emergency_toggle_count: int = 0
        self.monitoring_counters: dict[str, Any] = {}

        # News intelligence strategy states
        self.strategy_states: dict[str, dict] = {}

        # Metadata
        self._restored: bool = False
        self._last_save: Optional[datetime] = None

    def set_base_dir(self, path: Path) -> None:
        """Set the persistence directory."""
        self._base_dir = path

    def restore(self) -> dict[str, Any]:
        """Restore all state from disk. Returns keys that were restored."""
        with self._lock:
            data = restore_all(self._base_dir)

            if "decision" in data:
                d = data["decision"]
                self.decision_history = d.get("history", [])
                self.decision_active = d.get("active", [])
                if "emergency" in d:
                    self.emergency_disabled = d["emergency"].get("disabled", False)
                    self.emergency_toggle_count = d["emergency"].get("toggle_count", 0)
                self.monitoring_counters = d.get("monitoring", {})

            if "strategy_states" in data:
                self.strategy_states = data["strategy_states"].get("states", {})

            if "emergency" in data and "decision" not in data:
                e = data["emergency"]
                self.emergency_disabled = e.get("disabled", False)
                self.emergency_toggle_count = e.get("toggle_count", 0)

            self._restored = True
            return list(data.keys())

    def save(self) -> None:
        """Save all state to disk."""
        with self._lock:
            save_all_snapshots(
                decision_history=self.decision_history,
                decision_active=self.decision_active,
                emergency_disabled=self.emergency_disabled,
                emergency_toggle_count=self.emergency_toggle_count,
                monitoring_counters=self.monitoring_counters,
                strategy_states=self.strategy_states,
                base_dir=self._base_dir,
            )
            self._last_save = datetime.now(timezone.utc)

    # -- Decision Engine helpers --

    def add_decision(self, decision: dict) -> None:
        """Add a decision to history and active list."""
        with self._lock:
            self.decision_history.append(decision)
            self.decision_active.append(decision)

    def set_emergency(self, disabled: bool, reason: str = "") -> None:
        """Update emergency state."""
        with self._lock:
            self.emergency_disabled = disabled
            self.emergency_toggle_count += 1

    # -- Strategy State helpers --

    def set_strategy_state(self, strategy_id: str, state: dict) -> None:
        """Update a strategy's state."""
        with self._lock:
            self.strategy_states[strategy_id] = state

    def get_strategy_state(self, strategy_id: str) -> Optional[dict]:
        """Get a strategy's state."""
        with self._lock:
            return self.strategy_states.get(strategy_id)


# Module-level singleton
_store: Optional[_StateStore] = None
_init_lock = threading.Lock()


def get_state_store() -> _StateStore:
    """Get or create the global state store singleton."""
    global _store
    if _store is None:
        with _init_lock:
            if _store is None:
                _store = _StateStore()
    return _store
