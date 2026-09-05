"""
Scalping Arise — Signal Invalidation Pipeline

Detects market condition changes that should invalidate active signals.
When conditions that supported the signal are no longer met, the signal
is transitioned to INVALIDATED state with a typed reason.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_analysis.models import AnalysisResult, MarketRegime
from app.modules.signal_engine.models import (
    DecisionReason,
    DecisionReasonCode,
    EvidenceItem,
    SignalDirection,
    SignalRecord,
    SignalState,
)
from app.modules.signal_engine.state_machine import SignalStateMachine

logger = logging.getLogger(__name__)


class SignalInvalidator:
    """
    Detects market condition changes that invalidate active signals.

    Checks regime shifts, MTF confirmation loss, and evidence
    degradation against the conditions that originally supported the signal.
    """

    def __init__(self, state_machine: SignalStateMachine) -> None:
        self._state_machine = state_machine

    def check_regime_shift(
        self,
        record: SignalRecord,
        current_analysis: Optional[AnalysisResult],
    ) -> bool:
        """
        Check if a regime shift invalidates the signal.

        A trend-following signal is invalidated if the regime shifts
        to ranging. A reversal signal is invalidated if regime shifts
        to trending.
        """
        if record.state not in (SignalState.ACTIVE, SignalState.CONFIRMED):
            return False

        if not current_analysis or not current_analysis.regime:
            return False

        current_regime = current_analysis.regime.state

        # Check original regime from candidates
        original_regimes = {
            c.market_regime for c in record.candidates if c.market_regime
        }

        if not original_regimes:
            return False

        # Trend-following signals invalidated by ranging regime
        is_trend_following = any(
            r in ("trending_up", "trending_down") for r in original_regimes
        )
        if is_trend_following and current_regime == MarketRegime.RANGING:
            return self._invalidate(
                record,
                f"Regime shifted to ranging — trend-following signal invalidated",
                DecisionReasonCode.INVALIDATED_BY_MARKET,
            )

        # Reversal signals invalidated by trending regime
        is_reversal = any(r == "ranging" for r in original_regimes)
        if is_reversal and current_regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN):
            return self._invalidate(
                record,
                f"Regime shifted to {current_regime.value} — reversal signal invalidated",
                DecisionReasonCode.INVALIDATED_BY_MARKET,
            )

        return False

    def check_mtf_loss(
        self,
        record: SignalRecord,
        current_aligned_count: int,
        min_aligned: int = 1,
    ) -> bool:
        """
        Check if multi-timeframe confirmation has been lost.

        If the number of aligned timeframes drops below the minimum,
        the signal is invalidated.
        """
        if record.state not in (SignalState.ACTIVE, SignalState.CONFIRMED):
            return False

        if current_aligned_count < min_aligned:
            return self._invalidate(
                record,
                f"MTF confirmation lost: {current_aligned_count}/{min_aligned} aligned",
                DecisionReasonCode.MTF_NOT_CONFIRMED,
            )
        return False

    def check_evidence_degradation(
        self,
        record: SignalRecord,
        current_evidence: list[EvidenceItem],
        min_supporting: int = 2,
    ) -> bool:
        """
        Check if supporting evidence has degraded below threshold.

        If the number of supporting evidence items drops below the
        minimum, the signal is invalidated.
        """
        if record.state not in (SignalState.ACTIVE, SignalState.CONFIRMED):
            return False

        supporting = [
            e for e in current_evidence
            if e.direction == record.direction
        ]

        if len(supporting) < min_supporting:
            return self._invalidate(
                record,
                f"Evidence degraded: {len(supporting)} supporting items (min: {min_supporting})",
                DecisionReasonCode.INSUFFICIENT_DATA,
            )
        return False

    def check_all(
        self,
        current_analysis: Optional[AnalysisResult] = None,
        current_aligned_count: Optional[int] = None,
        current_evidence: Optional[list[EvidenceItem]] = None,
        min_aligned: int = 1,
        min_supporting_evidence: int = 2,
    ) -> list[SignalRecord]:
        """
        Run all invalidation checks on active signals.

        Returns list of signals that were invalidated.
        """
        invalidated: list[SignalRecord] = []

        for record in self._state_machine.get_active():
            was_invalidated = False

            # Regime check
            if current_analysis and not was_invalidated:
                was_invalidated = self.check_regime_shift(record, current_analysis)

            # MTF check
            if current_aligned_count is not None and not was_invalidated:
                was_invalidated = self.check_mtf_loss(record, current_aligned_count, min_aligned)

            # Evidence check
            if current_evidence is not None and not was_invalidated:
                was_invalidated = self.check_evidence_degradation(
                    record, current_evidence, min_supporting_evidence,
                )

            if was_invalidated:
                invalidated.append(record)

        if invalidated:
            logger.info("Invalidated %d signals due to market condition changes", len(invalidated))

        return invalidated

    def _invalidate(
        self,
        record: SignalRecord,
        reason_text: str,
        reason_code: DecisionReasonCode,
    ) -> bool:
        """Transition a signal to INVALIDATED with a structured reason."""
        record.reasons.append(DecisionReason(
            code=reason_code,
            detail=reason_text,
        ))
        return self._state_machine.invalidate(record, reason_text)
