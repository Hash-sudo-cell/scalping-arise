"""
Scalping Arise — Market Structure Tests

Tests for HH / HL / LH / LL classification.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.market_analysis.models import StructureLabel, StructurePoint, SwingPoint, SwingType
from app.modules.market_analysis.structure import classify_structure


def _swing(
    index: int,
    price: float,
    swing_type: SwingType,
    hours_offset: int = 0,
) -> SwingPoint:
    return SwingPoint(
        index=index,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hours_offset),
        price=price,
        swing_type=swing_type,
        confirmed=True,
        timeframe="1h",
    )


class TestMarketStructure:
    def test_hh_detection(self) -> None:
        """A swing high above the prior swing high should be HH."""
        swings = [
            _swing(0, 100.0, SwingType.SWING_HIGH, 0),
            _swing(5, 110.0, SwingType.SWING_HIGH, 5),
        ]
        points = classify_structure(swings)
        assert len(points) == 2
        assert points[0].label == StructureLabel.INITIAL
        assert points[1].label == StructureLabel.HH
        assert "110" in points[1].reason or "110.00" in points[1].reason

    def test_hl_detection(self) -> None:
        """A swing low above the prior swing low should be HL."""
        swings = [
            _swing(0, 90.0, SwingType.SWING_LOW, 0),
            _swing(5, 95.0, SwingType.SWING_LOW, 5),
        ]
        points = classify_structure(swings)
        assert len(points) == 2
        assert points[0].label == StructureLabel.INITIAL
        assert points[1].label == StructureLabel.HL

    def test_lh_detection(self) -> None:
        """A swing high below the prior swing high should be LH."""
        swings = [
            _swing(0, 110.0, SwingType.SWING_HIGH, 0),
            _swing(5, 105.0, SwingType.SWING_HIGH, 5),
        ]
        points = classify_structure(swings)
        assert points[1].label == StructureLabel.LH

    def test_ll_detection(self) -> None:
        """A swing low below the prior swing low should be LL."""
        swings = [
            _swing(0, 95.0, SwingType.SWING_LOW, 0),
            _swing(5, 90.0, SwingType.SWING_LOW, 5),
        ]
        points = classify_structure(swings)
        assert points[1].label == StructureLabel.LL

    def test_bullish_structure(self) -> None:
        """A sequence of HH and HL should classify as bullish structure."""
        swings = [
            _swing(0, 100.0, SwingType.SWING_LOW, 0),
            _swing(5, 105.0, SwingType.SWING_HIGH, 5),
            _swing(10, 102.0, SwingType.SWING_LOW, 10),
            _swing(15, 110.0, SwingType.SWING_HIGH, 15),
            _swing(20, 106.0, SwingType.SWING_LOW, 20),
            _swing(25, 115.0, SwingType.SWING_HIGH, 25),
        ]
        points = classify_structure(swings)
        labels = [p.label for p in points if p.label != StructureLabel.INITIAL]
        # Should contain HH and HL predominantly
        hh_count = labels.count(StructureLabel.HH)
        hl_count = labels.count(StructureLabel.HL)
        assert hh_count >= 2
        assert hl_count >= 2

    def test_bearish_structure(self) -> None:
        """A sequence of LH and LL should classify as bearish structure."""
        swings = [
            _swing(0, 115.0, SwingType.SWING_HIGH, 0),
            _swing(5, 110.0, SwingType.SWING_LOW, 5),
            _swing(10, 112.0, SwingType.SWING_HIGH, 10),
            _swing(15, 105.0, SwingType.SWING_LOW, 15),
            _swing(20, 108.0, SwingType.SWING_HIGH, 20),
            _swing(25, 100.0, SwingType.SWING_LOW, 25),
        ]
        points = classify_structure(swings)
        labels = [p.label for p in points if p.label != StructureLabel.INITIAL]
        lh_count = labels.count(StructureLabel.LH)
        ll_count = labels.count(StructureLabel.LL)
        assert lh_count >= 2
        assert ll_count >= 2

    def test_ranging_structure(self) -> None:
        """Mixed swings should produce mixed labels."""
        swings = [
            _swing(0, 100.0, SwingType.SWING_HIGH, 0),
            _swing(5, 105.0, SwingType.SWING_HIGH, 5),
            _swing(10, 102.0, SwingType.SWING_HIGH, 10),
        ]
        points = classify_structure(swings)
        labels = [p.label for p in points if p.label != StructureLabel.INITIAL]
        # Should have a mix of HH and LH
        assert len(labels) >= 2

    def test_empty_swings(self) -> None:
        """Empty swings list should return empty structure."""
        points = classify_structure([])
        assert points == []

    def test_single_swing(self) -> None:
        """A single swing should be classified as INITIAL."""
        swings = [_swing(0, 100.0, SwingType.SWING_HIGH, 0)]
        points = classify_structure(swings)
        assert len(points) == 1
        assert points[0].label == StructureLabel.INITIAL

    def test_equal_highs_classified_as_lh(self) -> None:
        """Equal highs should conservatively be classified as LH."""
        swings = [
            _swing(0, 100.0, SwingType.SWING_HIGH, 0),
            _swing(5, 100.0, SwingType.SWING_HIGH, 5),
        ]
        points = classify_structure(swings)
        assert points[1].label == StructureLabel.LH

    def test_equal_lows_classified_as_ll(self) -> None:
        """Equal lows should conservatively be classified as LL."""
        swings = [
            _swing(0, 90.0, SwingType.SWING_LOW, 0),
            _swing(5, 90.0, SwingType.SWING_LOW, 5),
        ]
        points = classify_structure(swings)
        assert points[1].label == StructureLabel.LL

    def test_interleaved_swings(self) -> None:
        """Interleaved swing highs and lows should be classified independently."""
        swings = [
            _swing(0, 100.0, SwingType.SWING_HIGH, 0),
            _swing(3, 85.0, SwingType.SWING_LOW, 3),
            _swing(6, 110.0, SwingType.SWING_HIGH, 6),
            _swing(9, 88.0, SwingType.SWING_LOW, 9),
        ]
        points = classify_structure(swings)
        # Highs: INITIAL, HH
        # Lows: INITIAL, HL
        high_points = [p for p in points if p.swing.swing_type == SwingType.SWING_HIGH]
        low_points = [p for p in points if p.swing.swing_type == SwingType.SWING_LOW]
        assert high_points[0].label == StructureLabel.INITIAL
        assert high_points[1].label == StructureLabel.HH
        assert low_points[0].label == StructureLabel.INITIAL
        assert low_points[1].label == StructureLabel.HL
