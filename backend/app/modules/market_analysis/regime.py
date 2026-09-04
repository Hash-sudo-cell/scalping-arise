"""
Scalping Arise — Market Regime Detection

Deterministic market regime classification based on structural information.
No indicator stack — purely structural analysis.
"""

from __future__ import annotations

import logging

from app.modules.market_analysis.config import MarketAnalysisSettings, get_market_analysis_settings
from app.modules.market_analysis.models import (
    BOSDirection,
    BOSEvent,
    CHOCHEvent,
    MarketRegime,
    StructureLabel,
    StructurePoint,
    RegimeResult,
    TrendState,
)

logger = logging.getLogger(__name__)


def classify_regime(
    trend_state: TrendState,
    structure_points: list[StructurePoint],
    bos_events: list[BOSEvent],
    choch_events: list[CHOCHEvent],
    latest_price: float | None = None,
    settings: MarketAnalysisSettings | None = None,
) -> RegimeResult:
    """
    Classify the current market regime based on available structural info.

    Rules:
        - TRENDING_UP: Bullish trend + bullish BOS or consecutive HH/HL.
        - TRENDING_DOWN: Bearish trend + bearish BOS or consecutive LH/LL.
        - RANGING: Trend is ranging and price is between structural boundaries.
        - VOLATILE: Multiple CHOCH events indicating frequent character changes.
        - UNCLEAR: Insufficient information.

    Args:
        trend_state: Current trend classification.
        structure_points: Classified structure points.
        bos_events: Detected BOS events.
        choch_events: Detected CHOCH events.
        latest_price: Current price for range evaluation (optional).
        settings: Optional settings override.

    Returns:
        RegimeResult with state and evidence.
    """
    cfg = settings or get_market_analysis_settings()
    evidence: list[str] = []

    # Extract labels
    labels = [sp.label for sp in structure_points if sp.label != StructureLabel.INITIAL]
    recent_labels = labels[-8:] if len(labels) > 8 else labels

    # Count consecutive bullish/bearish labels at the tail
    tail_bullish = 0
    for label in reversed(recent_labels):
        if label in (StructureLabel.HH, StructureLabel.HL):
            tail_bullish += 1
        else:
            break

    tail_bearish = 0
    for label in reversed(recent_labels):
        if label in (StructureLabel.LH, StructureLabel.LL):
            tail_bearish += 1
        else:
            break

    # Check for recent BOS
    recent_bullish_bos = any(e.direction == BOSDirection.BULLISH_BOS for e in bos_events[-3:])
    recent_bearish_bos = any(e.direction == BOSDirection.BEARISH_BOS for e in bos_events[-3:])

    # Volatile: multiple CHOCH events
    if len(choch_events) >= 2:
        evidence.append(f"{len(choch_events)} CHOCH events detected — frequent character changes")
        return RegimeResult(state=MarketRegime.VOLATILE, evidence=evidence)

    # Trending up
    if trend_state == TrendState.BULLISH:
        if tail_bullish >= cfg.regime_trend_min_consecutive:
            evidence.append(
                f"Consecutive bullish structure: {tail_bullish} labels "
                f"({' -> '.join(l.value for l in recent_labels[-tail_bullish:])})"
            )
        if recent_bullish_bos:
            evidence.append("Recent bullish BOS confirmed")
        if evidence:
            return RegimeResult(state=MarketRegime.TRENDING_UP, evidence=evidence)
        evidence.append("Bullish trend but limited structural evidence")
        return RegimeResult(state=MarketRegime.TRENDING_UP, evidence=evidence)

    # Trending down
    if trend_state == TrendState.BEARISH:
        if tail_bearish >= cfg.regime_trend_min_consecutive:
            evidence.append(
                f"Consecutive bearish structure: {tail_bearish} labels "
                f"({' -> '.join(l.value for l in recent_labels[-tail_bearish:])})"
            )
        if recent_bearish_bos:
            evidence.append("Recent bearish BOS confirmed")
        if evidence:
            return RegimeResult(state=MarketRegime.TRENDING_DOWN, evidence=evidence)
        evidence.append("Bearish trend but limited structural evidence")
        return RegimeResult(state=MarketRegime.TRENDING_DOWN, evidence=evidence)

    # Ranging
    if trend_state == TrendState.RANGING:
        evidence.append("Mixed HH/HL and LH/LL structure — no sustained direction")

        if latest_price and len(structure_points) >= 2:
            # Check if price is within the range of recent swings
            recent_highs = [
                sp.swing.price for sp in structure_points
                if sp.swing.swing_type.value == "swing_high"
            ]
            recent_lows = [
                sp.swing.price for sp in structure_points
                if sp.swing.swing_type.value == "swing_low"
            ]
            if recent_highs and recent_lows:
                range_high = max(recent_highs[-5:])
                range_low = min(recent_lows[-5:])
                range_pct = ((range_high - range_low) / range_low * 100) if range_low > 0 else 0
                evidence.append(
                    f"Price ({latest_price:.2f}) within range "
                    f"[{range_low:.2f} - {range_high:.2f}] ({range_pct:.2f}%)"
                )

        return RegimeResult(state=MarketRegime.RANGING, evidence=evidence)

    # Unclear
    evidence.append("Insufficient structural information for regime classification")
    return RegimeResult(state=MarketRegime.UNCLEAR, evidence=evidence)
