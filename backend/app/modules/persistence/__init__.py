"""
Scalping Arise — State Persistence

Provides save/restore for critical in-memory state to JSON files.
Handles: decision engine, news intelligence strategy states, emergency state.

Design:
  - JSON file-backed (no database dependency)
  - Atomic writes (write to .tmp then rename)
  - Auto-save via save_snapshot() called from services
  - Auto-restore via restore_all() called from lifespan
  - All operations are sync (called at startup/shutdown boundaries)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default persistence directory
_DEFAULT_DIR = Path("data/state")


def _ensure_dir(path: Path) -> None:
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically: write to temp file, then rename."""
    _ensure_dir(path.parent)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=path.stem
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        # Atomic rename on Windows: must remove target first
        if path.exists():
            path.unlink()
        os.rename(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_read(path: Path) -> Optional[dict[str, Any]]:
    """Read JSON file. Returns None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", path, e)
        return None


# ---------------------------------------------------------------------------
# Decision Engine Persistence
# ---------------------------------------------------------------------------

def save_decision_state(
    history: list[dict],
    active: list[dict],
    emergency_disabled: bool,
    emergency_toggle_count: int,
    monitoring_counters: dict,
    base_dir: Optional[Path] = None,
) -> None:
    """Save decision engine state to disk."""
    base = base_dir or _DEFAULT_DIR
    path = base / "decision_state.json"
    data = {
        "version": 1,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "history": history,
        "active": active,
        "emergency": {
            "disabled": emergency_disabled,
            "toggle_count": emergency_toggle_count,
        },
        "monitoring": monitoring_counters,
    }
    _atomic_write(path, data)
    logger.info("Decision state saved: %d history, %d active", len(history), len(active))


def restore_decision_state(
    base_dir: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Restore decision engine state from disk."""
    base = base_dir or _DEFAULT_DIR
    path = base / "decision_state.json"
    return _atomic_read(path)


# ---------------------------------------------------------------------------
# News Intelligence Strategy State Persistence
# ---------------------------------------------------------------------------

def save_strategy_states(
    states: dict[str, dict],
    base_dir: Optional[Path] = None,
) -> None:
    """Save news intelligence strategy states to disk."""
    base = base_dir or _DEFAULT_DIR
    path = base / "strategy_states.json"
    data = {
        "version": 1,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "states": states,
    }
    _atomic_write(path, data)
    logger.info("Strategy states saved: %d strategies", len(states))


def restore_strategy_states(
    base_dir: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Restore news intelligence strategy states from disk."""
    base = base_dir or _DEFAULT_DIR
    path = base / "strategy_states.json"
    return _atomic_read(path)


# ---------------------------------------------------------------------------
# Emergency State Persistence (standalone, quick access)
# ---------------------------------------------------------------------------

def save_emergency_state(
    disabled: bool,
    toggle_count: int = 0,
    last_reason: str = "",
    base_dir: Optional[Path] = None,
) -> None:
    """Save emergency controller state to disk."""
    base = base_dir or _DEFAULT_DIR
    path = base / "emergency_state.json"
    data = {
        "version": 1,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "disabled": disabled,
        "toggle_count": toggle_count,
        "last_reason": last_reason,
    }
    _atomic_write(path, data)
    logger.info("Emergency state saved: disabled=%s", disabled)


def restore_emergency_state(
    base_dir: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Restore emergency controller state from disk."""
    base = base_dir or _DEFAULT_DIR
    path = base / "emergency_state.json"
    return _atomic_read(path)


# ---------------------------------------------------------------------------
# Bulk Operations
# ---------------------------------------------------------------------------

def save_all_snapshots(
    *,
    decision_history: list[dict] | None = None,
    decision_active: list[dict] | None = None,
    emergency_disabled: bool = False,
    emergency_toggle_count: int = 0,
    monitoring_counters: dict | None = None,
    strategy_states: dict[str, dict] | None = None,
    base_dir: Optional[Path] = None,
) -> None:
    """Save all state snapshots at once (for shutdown)."""
    base = base_dir or _DEFAULT_DIR
    _ensure_dir(base)

    if decision_history is not None and decision_active is not None:
        save_decision_state(
            history=decision_history,
            active=decision_active,
            emergency_disabled=emergency_disabled,
            emergency_toggle_count=emergency_toggle_count,
            monitoring_counters=monitoring_counters or {},
            base_dir=base,
        )

    if strategy_states is not None:
        save_strategy_states(states=strategy_states, base_dir=base)

    # Always save emergency state
    save_emergency_state(
        disabled=emergency_disabled,
        toggle_count=emergency_toggle_count,
        base_dir=base,
    )


def restore_all(
    base_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Restore all state snapshots at once (for startup)."""
    base = base_dir or _DEFAULT_DIR
    result: dict[str, Any] = {}

    decision = restore_decision_state(base)
    if decision:
        result["decision"] = decision

    strategies = restore_strategy_states(base)
    if strategies:
        result["strategy_states"] = strategies

    emergency = restore_emergency_state(base)
    if emergency:
        result["emergency"] = emergency

    if result:
        logger.info("State restored: %s", list(result.keys()))
    else:
        logger.info("No saved state found — starting fresh")

    return result
