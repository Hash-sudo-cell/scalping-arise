"""
Scalping Arise — Persistence Layer Tests
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.modules.persistence import (
    _atomic_read,
    _atomic_write,
    restore_all,
    restore_decision_state,
    restore_emergency_state,
    restore_strategy_states,
    save_all_snapshots,
    save_decision_state,
    save_emergency_state,
    save_strategy_states,
)


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Provide a temporary state directory."""
    return tmp_path / "state"


class TestAtomicIO:
    """Test atomic file operations."""

    def test_atomic_write_creates_file(self, tmp_state_dir):
        path = tmp_state_dir / "test.json"
        _atomic_write(path, {"key": "value"})
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["key"] == "value"

    def test_atomic_write_overwrites_existing(self, tmp_state_dir):
        path = tmp_state_dir / "test.json"
        _atomic_write(path, {"version": 1})
        _atomic_write(path, {"version": 2})
        data = json.loads(path.read_text())
        assert data["version"] == 2

    def test_atomic_read_returns_none_if_missing(self, tmp_state_dir):
        path = tmp_state_dir / "nonexistent.json"
        assert _atomic_read(path) is None

    def test_atomic_read_returns_none_on_corrupt(self, tmp_state_dir):
        path = tmp_state_dir / "corrupt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT JSON{{{")
        assert _atomic_read(path) is None

    def test_atomic_read_roundtrip(self, tmp_state_dir):
        path = tmp_state_dir / "data.json"
        payload = {"nested": {"a": 1}, "list": [1, 2, 3]}
        _atomic_write(path, payload)
        result = _atomic_read(path)
        assert result == payload


class TestDecisionPersistence:
    """Test decision state save/restore."""

    def test_save_and_restore(self, tmp_state_dir):
        history = [{"id": "d1", "state": "actionable"}, {"id": "d2", "state": "blocked"}]
        active = [{"id": "d1", "state": "actionable"}]
        counters = {"total_evaluations": 42}

        save_decision_state(
            history=history,
            active=active,
            emergency_disabled=True,
            emergency_toggle_count=3,
            monitoring_counters=counters,
            base_dir=tmp_state_dir,
        )

        data = restore_decision_state(tmp_state_dir)
        assert data is not None
        assert data["version"] == 1
        assert len(data["history"]) == 2
        assert len(data["active"]) == 1
        assert data["emergency"]["disabled"] is True
        assert data["emergency"]["toggle_count"] == 3
        assert data["monitoring"]["total_evaluations"] == 42

    def test_restore_returns_none_when_empty(self, tmp_state_dir):
        assert restore_decision_state(tmp_state_dir) is None


class TestStrategyPersistence:
    """Test strategy state save/restore."""

    def test_save_and_restore(self, tmp_state_dir):
        states = {
            "strategy_a": {"state": "active", "sample_size": 50},
            "strategy_b": {"state": "restricted", "sample_size": 120},
        }
        save_strategy_states(states, base_dir=tmp_state_dir)

        data = restore_strategy_states(tmp_state_dir)
        assert data is not None
        assert len(data["states"]) == 2
        assert data["states"]["strategy_a"]["state"] == "active"
        assert data["states"]["strategy_b"]["state"] == "restricted"

    def test_restore_returns_none_when_empty(self, tmp_state_dir):
        assert restore_strategy_states(tmp_state_dir) is None


class TestEmergencyPersistence:
    """Test emergency state save/restore."""

    def test_save_and_restore(self, tmp_state_dir):
        save_emergency_state(
            disabled=True,
            toggle_count=5,
            last_reason="Test emergency",
            base_dir=tmp_state_dir,
        )

        data = restore_emergency_state(tmp_state_dir)
        assert data is not None
        assert data["disabled"] is True
        assert data["toggle_count"] == 5
        assert data["last_reason"] == "Test emergency"

    def test_restore_returns_none_when_empty(self, tmp_state_dir):
        assert restore_emergency_state(tmp_state_dir) is None


class TestBulkOperations:
    """Test save_all_snapshots and restore_all."""

    def test_save_and_restore_all(self, tmp_state_dir):
        save_all_snapshots(
            decision_history=[{"id": "d1"}],
            decision_active=[{"id": "d1"}],
            emergency_disabled=True,
            emergency_toggle_count=2,
            monitoring_counters={"total": 10},
            strategy_states={"s1": {"state": "active"}},
            base_dir=tmp_state_dir,
        )

        result = restore_all(tmp_state_dir)
        assert "decision" in result
        assert "strategy_states" in result
        assert "emergency" in result

        assert len(result["decision"]["history"]) == 1
        assert result["decision"]["emergency"]["disabled"] is True
        assert result["strategy_states"]["states"]["s1"]["state"] == "active"

    def test_restore_all_empty(self, tmp_state_dir):
        result = restore_all(tmp_state_dir)
        assert result == {}

    def test_save_partial(self, tmp_state_dir):
        save_all_snapshots(
            strategy_states={"s1": {"state": "disabled"}},
            base_dir=tmp_state_dir,
        )

        result = restore_all(tmp_state_dir)
        assert "strategy_states" in result
        assert "decision" not in result
