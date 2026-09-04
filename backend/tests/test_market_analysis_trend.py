"""
Scalping Arise — Trend Classification Tests

Tests for deterministic trend classification based on structure.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.market_analysis.models import (
    StructureLabel,
    StructurePoint,
    SwingPoint,
    SwingType,
    TrendState,
)
from app.modules.market_analysis.trend import classify_trend


def _structure_point(label: StructureLabel, price: float, index: int) -> StructurePoint:
    swing = SwingPoint(
        index=index,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index),
        price=price,
        swing_type=SwingType.SWING_HIGH if label in (StructureLabel.HH, StructureLabel.LH, StructureLabel.INITIAL) else SwingType.SWING_LOW,
        confirmed=True,
        timeframe="1h",
    )
    return StructurePoint(swing=swing, label=label, reason="test")


class TestTrendClassification:
    def test_bullish_trend(self) -> None:
        """Consecutive HH/HL at the tail should classify as BULLISH."""
        points = [
            _structure_point(StructureLabel.HH, 110, 5),
            _structure_point(StructureLabel.HL, 95, 10),
            _structure_point(StructureLabel.HH, 115, 15),
            _structure_point(StructureLabel.HL, 98, 20),
            _structure_point(StructureLabel.HH, 120, 25),
        ]
        result = classify_trend(points, min_consecutive=2)
        assert result.state == TrendState.BULLISH
        assert "HH" in result.reason or "HL" in result.reason

    def test_bearish_trend(self) -> None:
        """Consecutive LH/LL at the tail should classify as BEARISH."""
        points = [
            _structure_point(StructureLabel.LH, 110, 5),
            _structure_point(StructureLabel.LL, 95, 10),
            _structure_point(StructureLabel.LH, 105, 15),
            _structure_point(StructureLabel.LL, 90, 20),
            _structure_point(StructureLabel.LH, 100, 25),
        ]
        result = classify_trend(points, min_consecutive=2)
        assert result.state == TrendState.BEARISH

    def test_ranging_trend(self) -> None:
        """Mixed labels should classify as RANGING."""
        points = [
            _structure_point(StructureLabel.HH, 110, 5),
            _structure_point(StructureLabel.LL, 90, 10),
            _structure_point(StructureLabel.HH, 108, 15),
            _structure_point(StructureLabel.LL, 88, 20),
        ]
        result = classify_trend(points, min_consecutive=2)
        assert result.state == TrendState.RANGING

    def test_unclear_insufficient_data(self) -> None:
        """No structure points should return UNCLEAR."""
        result = classify_trend([], min_consecutive=2)
        assert result.state == TrendState.UNCLEAR
        assert "Insufficient" in result.reason or "No classified" in result.reason

    def test_single_label_unclear(self) -> None:
        """Only one label should return UNCLEAR or RANGING."""
        points = [_structure_point(StructureLabel.HH, 110, 5)]
        result = classify_trend(points, min_consecutive=2)
        assert result.state in (TrendState.UNCLEAR, TrendState.RANGING)

    def test_structure_labels_populated(self) -> None:
        """Trend result should include the structure labels used."""
        points = [
            _structure_point(StructureLabel.HH, 110, 5),
            _structure_point(StructureLabel.HL, 95, 10),
            _structure_point(StructureLabel.HH, 115, 15),
        ]
        result = classify_trend(points, min_consecutive=2)
        assert len(result.structure_labels) > 0
