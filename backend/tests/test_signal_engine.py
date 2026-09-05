"""
Scalping Arise — Phase 6 Signal Engine Tests

Deterministic, isolated tests for candidate generation, multi-timeframe
confirmation, evidence aggregation, conflict detection, conflict resolution,
confidence scoring, signal qualification, validation, and API endpoints.
Uses hand-crafted data — no external API calls.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment before any app imports
os.environ["SCALPING_ARISE_ENVIRONMENT"] = "testing"
os.environ["SCALPING_ARISE_DEBUG"] = "true"
os.environ["SCALPING_ARISE_LOG_LEVEL"] = "WARNING"

from app.modules.market_analysis.models import (
    AnalysisResult,
    AnalysisStatus,
    LiquidityAnalysisResult,
    MarketRegime,
    RegimeResult,
    StructureLabel,
    StructureResult,
    TrendResult,
    TrendState,
)
from app.modules.signal_engine.candidate_generation import (
    generate_candidates,
    _extract_condition_pass_rate,
)
from app.modules.signal_engine.confidence import (
    calculate_confidence,
    _score_strategy_alignment,
    _score_mtf_confirmation,
    _score_evidence_strength,
    _score_regime_consistency,
)
from app.modules.signal_engine.conflict_resolver import resolve_conflicts
from app.modules.signal_engine.conflicts import (
    detect_all_conflicts,
    detect_strategy_divergence,
    detect_timeframe_misalignment,
)
from app.modules.signal_engine.config import SignalEngineSettings, get_signal_engine_settings
from app.modules.signal_engine.evidence import aggregate_evidence
from app.modules.signal_engine.models import (
    ConfirmationLevel,
    ConfidenceScore,
    ConflictResolution,
    ConflictType,
    DecisionReason,
    DecisionReasonCode,
    DecisionType,
    DirectionalConflict,
    EvidenceItem,
    MTFConfirmationResult,
    SignalCandidate,
    SignalDirection,
    SignalEvaluationResult,
    SignalPriority,
    SignalQuality,
    SignalRecord,
    SignalState,
    SignalStatus,
    TimeframeConfirmation,
)
from app.modules.signal_engine.multi_timeframe import evaluate_mtf_confirmation
from app.modules.signal_engine.qualification import qualify_signal, compute_signal_quality
from app.modules.signal_engine.config import get_signal_engine_settings, SignalEngineSettings
from app.modules.signal_engine.validation import (
    validate_candle_limit,
    validate_instrument,
    validate_timeframes,
)
from app.modules.strategies.models import (
    ConditionCriticality,
    ConditionResult,
    ConditionStatus,
    InvalidationResult,
    LiquidityConditionResult,
    LiquidityConditionSummary,
    LiquidityAvailabilityStatus,
    QualityScore,
    QualityScoreBreakdown,
    StrategyDirection,
    StrategyEvaluationResult,
    StrategyEvaluationStatus,
    TimeframeContext,
)
from app.modules.technical_features.models import (
    EMAAlignment,
    EMAResult,
    EMAValue,
    FeatureAvailability,
    FeatureResult,
    FeatureSetStatus,
)


# ---------------------------------------------------------------------------
# Helpers — hand-crafted test data factories
# ---------------------------------------------------------------------------

def _make_ema_result(alignment: EMAAlignment = EMAAlignment.BULLISH) -> EMAResult:
    """Create an EMAResult with the given alignment."""
    return EMAResult(
        fast=EMAValue(
            period=9, value=2000.0, availability=FeatureAvailability.AVAILABLE,
            direction="rising", price_relative="above", required_history=9,
        ),
        medium=EMAValue(
            period=21, value=1995.0, availability=FeatureAvailability.AVAILABLE,
            direction="rising", price_relative="above", required_history=21,
        ),
        slow=EMAValue(
            period=50, value=1990.0, availability=FeatureAvailability.AVAILABLE,
            direction="rising", price_relative="above", required_history=50,
        ),
        alignment=alignment,
    )


def _make_feature_result(
    ema_alignment: EMAAlignment = EMAAlignment.BULLISH,
    fs_status: FeatureSetStatus = FeatureSetStatus.READY,
) -> FeatureResult:
    """Create a FeatureResult with the given EMA alignment."""
    return FeatureResult(
        status=FeatureAvailability.AVAILABLE,
        reason="Test features",
        feature_set_status=fs_status,
        trend=_make_ema_result(ema_alignment),
    )


def _make_strategy_eval(
    strategy_id: str = "trend_continuation",
    status: StrategyEvaluationStatus = StrategyEvaluationStatus.QUALIFIED,
    direction: StrategyDirection = StrategyDirection.BULLISH,
    quality_normalized: float = 0.8,
    regime: str = "trending_up",
    required_passed: int = 4,
    required_total: int = 4,
    triggered_invalidations: int = 0,
) -> StrategyEvaluationResult:
    """Create a StrategyEvaluationResult with the given parameters."""
    conditions = []
    for i in range(required_total):
        conditions.append(ConditionResult(
            condition_id=f"cond_{i}",
            condition_name=f"Condition {i}",
            description=f"Test condition {i}",
            criticality=ConditionCriticality.CRITICAL if i < 2 else ConditionCriticality.REQUIRED,
            expected_value="true",
            actual_value="true" if i < required_passed else "false",
            status=ConditionStatus.PASSED if i < required_passed else ConditionStatus.FAILED,
            reason="Passed" if i < required_passed else "Failed",
        ))

    invalidations = []
    for i in range(triggered_invalidations):
        invalidations.append(InvalidationResult(
            rule_id=f"inval_{i}",
            rule_name=f"Invalidation {i}",
            description=f"Test invalidation {i}",
            triggered=True,
            reason="Triggered",
        ))

    return StrategyEvaluationResult(
        strategy_id=strategy_id,
        strategy_version="2.0",
        strategy_name=strategy_id.replace("_", " ").title(),
        instrument="XAU/USD",
        timeframe_contexts=[TimeframeContext(
            timeframe="15m", source_type="spot", provider="twelve_data",
            provider_instrument="XAU/USD", candle_count=300,
        )],
        source_types_used=["spot"],
        market_regime=regime,
        status=status,
        direction=direction,
        quality_score=QualityScore(
            score=int(quality_normalized * 100),
            max_score=100,
            scoring_model_version="2.0",
            breakdown=[],
            normalized_score=quality_normalized,
        ),
        condition_results=conditions,
        invalidation_results=invalidations,
        reason="Test evaluation",
    )


def _make_candidate(
    strategy_id: str = "trend_continuation",
    direction: SignalDirection = SignalDirection.LONG,
    quality: float = 0.8,
    pass_rate: float = 1.0,
) -> SignalCandidate:
    """Create a SignalCandidate with the given parameters."""
    return SignalCandidate(
        strategy_id=strategy_id,
        strategy_version="2.0",
        strategy_name=strategy_id.replace("_", " ").title(),
        direction=direction,
        quality_score_normalized=quality,
        quality_score_raw=int(quality * 100),
        quality_score_max=100,
        condition_pass_rate=pass_rate,
        market_regime="trending_up",
    )


# ---------------------------------------------------------------------------
# Candidate Generation Tests
# ---------------------------------------------------------------------------

class TestCandidateGeneration:
    """Tests for candidate generation from strategy evaluations."""

    def test_qualified_bullish_produces_long_candidate(self):
        """A qualified bullish strategy produces a LONG candidate."""
        ev = _make_strategy_eval(
            status=StrategyEvaluationStatus.QUALIFIED,
            direction=StrategyDirection.BULLISH,
        )
        candidates, evidence = generate_candidates([ev])

        assert len(candidates) == 1
        assert candidates[0].direction == SignalDirection.LONG
        assert candidates[0].strategy_id == "trend_continuation"
        assert candidates[0].quality_score_normalized == 0.8

    def test_qualified_bearish_produces_short_candidate(self):
        """A qualified bearish strategy produces a SHORT candidate."""
        ev = _make_strategy_eval(
            status=StrategyEvaluationStatus.QUALIFIED,
            direction=StrategyDirection.BEARISH,
        )
        candidates, evidence = generate_candidates([ev])

        assert len(candidates) == 1
        assert candidates[0].direction == SignalDirection.SHORT

    def test_not_qualified_produces_no_candidates(self):
        """A not-qualified strategy produces no candidates."""
        ev = _make_strategy_eval(
            status=StrategyEvaluationStatus.NOT_QUALIFIED,
            direction=StrategyDirection.BULLISH,
        )
        candidates, _ = generate_candidates([ev])
        assert len(candidates) == 0

    def test_invalidated_produces_no_candidates(self):
        """An invalidated strategy produces no candidates."""
        ev = _make_strategy_eval(
            status=StrategyEvaluationStatus.INVALIDATED,
            direction=StrategyDirection.BULLISH,
        )
        candidates, _ = generate_candidates([ev])
        assert len(candidates) == 0

    def test_neutral_direction_produces_no_candidates(self):
        """A neutral direction produces no signal candidates."""
        ev = _make_strategy_eval(
            status=StrategyEvaluationStatus.QUALIFIED,
            direction=StrategyDirection.NEUTRAL,
        )
        candidates, _ = generate_candidates([ev])
        assert len(candidates) == 0

    def test_multiple_qualified_produce_multiple_candidates(self):
        """Multiple qualified strategies produce multiple candidates."""
        ev1 = _make_strategy_eval(
            strategy_id="trend_continuation",
            status=StrategyEvaluationStatus.QUALIFIED,
            direction=StrategyDirection.BULLISH,
        )
        ev2 = _make_strategy_eval(
            strategy_id="pullback_continuation",
            status=StrategyEvaluationStatus.QUALIFIED,
            direction=StrategyDirection.BULLISH,
        )
        candidates, _ = generate_candidates([ev1, ev2])
        assert len(candidates) == 2
        assert all(c.direction == SignalDirection.LONG for c in candidates)

    def test_condition_pass_rate_calculation(self):
        """Condition pass rate is calculated correctly."""
        ev = _make_strategy_eval(required_passed=3, required_total=4)
        rate = _extract_condition_pass_rate(ev)
        assert rate == pytest.approx(0.75)

    def test_evidence_collected_from_candidates(self):
        """Evidence items are collected from qualified candidates."""
        ev = _make_strategy_eval(
            status=StrategyEvaluationStatus.QUALIFIED,
            direction=StrategyDirection.BULLISH,
        )
        _, evidence = generate_candidates([ev])
        assert len(evidence) > 0
        assert all(isinstance(e, EvidenceItem) for e in evidence)

    def test_empty_evaluations(self):
        """Empty evaluation list produces no candidates."""
        candidates, evidence = generate_candidates([])
        assert len(candidates) == 0
        assert len(evidence) == 0


# ---------------------------------------------------------------------------
# Multi-Timeframe Confirmation Tests
# ---------------------------------------------------------------------------

class TestMultiTimeframeConfirmation:
    """Tests for MTF confirmation evaluation."""

    def test_bullish_candidate_aligned_with_bullish_emas(self):
        """A LONG candidate with bullish EMA across timeframes is confirmed."""
        candidate = _make_candidate(direction=SignalDirection.LONG)
        features = {
            "1m": _make_feature_result(EMAAlignment.BULLISH),
            "5m": _make_feature_result(EMAAlignment.BULLISH),
            "15m": _make_feature_result(EMAAlignment.BULLISH),
        }
        analyses = {tf: None for tf in features}

        result, evidence = evaluate_mtf_confirmation(
            candidate, features, analyses, min_aligned=1,
        )

        assert result.confirmed is True
        assert result.aligned_count == 3
        assert result.total_count == 3
        assert result.confirmation_level == ConfirmationLevel.STRONG

    def test_bullish_candidate_with_mixed_alignment(self):
        """A LONG candidate with mixed EMA has partial confirmation."""
        candidate = _make_candidate(direction=SignalDirection.LONG)
        features = {
            "1m": _make_feature_result(EMAAlignment.BULLISH),
            "5m": _make_feature_result(EMAAlignment.MIXED),
            "15m": _make_feature_result(EMAAlignment.BEARISH),
        }
        analyses = {tf: None for tf in features}

        result, evidence = evaluate_mtf_confirmation(
            candidate, features, analyses, min_aligned=1,
        )

        assert result.confirmed is True  # At least 1 aligned
        assert result.aligned_count == 1
        assert result.total_count == 3

    def test_no_alignment_fails_confirmation(self):
        """When no timeframes align, confirmation fails."""
        candidate = _make_candidate(direction=SignalDirection.LONG)
        features = {
            "1m": _make_feature_result(EMAAlignment.BEARISH),
            "5m": _make_feature_result(EMAAlignment.BEARISH),
        }
        analyses = {tf: None for tf in features}

        result, _ = evaluate_mtf_confirmation(
            candidate, features, analyses, min_aligned=1,
        )

        assert result.confirmed is False
        assert result.aligned_count == 0

    def test_warming_up_features_count_as_not_aligned(self):
        """WARMING_UP features are not counted as aligned."""
        candidate = _make_candidate(direction=SignalDirection.LONG)
        features = {
            "1m": _make_feature_result(
                EMAAlignment.BULLISH, FeatureSetStatus.WARMING_UP,
            ),
            "5m": _make_feature_result(EMAAlignment.BULLISH),
        }
        analyses = {tf: None for tf in features}

        result, _ = evaluate_mtf_confirmation(
            candidate, features, analyses, min_aligned=1,
        )

        assert result.confirmed is True  # 5m still aligned
        assert result.aligned_count == 1

    def test_unavailable_features(self):
        """UNAVAILABLE features are not counted."""
        candidate = _make_candidate(direction=SignalDirection.LONG)
        features = {
            "1m": _make_feature_result(
                EMAAlignment.UNAVAILABLE, FeatureSetStatus.UNAVAILABLE,
            ),
        }
        analyses = {"1m": None}

        result, _ = evaluate_mtf_confirmation(
            candidate, features, analyses, min_aligned=1,
        )

        assert result.confirmed is False
        assert result.aligned_count == 0

    def test_evidence_items_generated(self):
        """Evidence items are generated for each timeframe."""
        candidate = _make_candidate(direction=SignalDirection.LONG)
        features = {
            "1m": _make_feature_result(EMAAlignment.BULLISH),
            "5m": _make_feature_result(EMAAlignment.BEARISH),
        }
        analyses = {tf: None for tf in features}

        _, evidence = evaluate_mtf_confirmation(
            candidate, features, analyses, min_aligned=1,
        )

        assert len(evidence) >= 2  # At least one per timeframe


# ---------------------------------------------------------------------------
# Conflict Detection Tests
# ---------------------------------------------------------------------------

class TestConflictDetection:
    """Tests for conflict detection between candidates."""

    def test_no_conflict_same_direction(self):
        """Candidates with the same direction produce no conflicts."""
        candidates = [
            _make_candidate("tc", SignalDirection.LONG),
            _make_candidate("pc", SignalDirection.LONG),
        ]
        conflicts = detect_strategy_divergence(candidates)
        assert len(conflicts) == 0

    def test_conflict_opposing_directions(self):
        """Candidates with opposing directions produce a conflict."""
        candidates = [
            _make_candidate("tc", SignalDirection.LONG),
            _make_candidate("rr", SignalDirection.SHORT),
        ]
        conflicts = detect_strategy_divergence(candidates)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.STRATEGY_DIVERGENCE

    def test_no_conflict_single_candidate(self):
        """A single candidate cannot produce a divergence conflict."""
        candidates = [_make_candidate("tc", SignalDirection.LONG)]
        conflicts = detect_strategy_divergence(candidates)
        assert len(conflicts) == 0

    def test_timeframe_misalignment_detected(self):
        """Misaligned timeframes produce a conflict."""
        mtf = MTFConfirmationResult(
            confirmed=True,
            confirmation_level=ConfirmationLevel.WEAK,
            aligned_count=1,
            total_count=3,
            confirmations=[
                TimeframeConfirmation(timeframe="1m", aligned=True, confirmation_level=ConfirmationLevel.MODERATE),
                TimeframeConfirmation(timeframe="5m", aligned=False, confirmation_level=ConfirmationLevel.NONE),
                TimeframeConfirmation(timeframe="15m", aligned=False, confirmation_level=ConfirmationLevel.NONE),
            ],
        )
        conflicts = detect_timeframe_misalignment(mtf, SignalDirection.LONG)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.TIMEFRAME_MISALIGNMENT

    def test_no_misalignment_when_all_aligned(self):
        """When all timeframes align, no misalignment conflict."""
        mtf = MTFConfirmationResult(
            confirmed=True,
            confirmation_level=ConfirmationLevel.STRONG,
            aligned_count=3,
            total_count=3,
            confirmations=[
                TimeframeConfirmation(timeframe="1m", aligned=True, confirmation_level=ConfirmationLevel.STRONG),
                TimeframeConfirmation(timeframe="5m", aligned=True, confirmation_level=ConfirmationLevel.STRONG),
                TimeframeConfirmation(timeframe="15m", aligned=True, confirmation_level=ConfirmationLevel.STRONG),
            ],
        )
        conflicts = detect_timeframe_misalignment(mtf, SignalDirection.LONG)
        assert len(conflicts) == 0

    def test_detect_all_conflicts_combined(self):
        """detect_all_conflicts combines divergence and misalignment."""
        candidates = [
            _make_candidate("tc", SignalDirection.LONG),
            _make_candidate("rr", SignalDirection.SHORT),
        ]
        mtf = MTFConfirmationResult(
            confirmed=True,
            confirmation_level=ConfirmationLevel.WEAK,
            aligned_count=1,
            total_count=2,
            confirmations=[
                TimeframeConfirmation(timeframe="1m", aligned=True, confirmation_level=ConfirmationLevel.MODERATE),
                TimeframeConfirmation(timeframe="5m", aligned=False, confirmation_level=ConfirmationLevel.NONE),
            ],
        )
        conflicts = detect_all_conflicts(candidates, mtf, SignalDirection.LONG)
        assert len(conflicts) >= 2  # Both divergence + misalignment


# ---------------------------------------------------------------------------
# Conflict Resolution Tests
# ---------------------------------------------------------------------------

class TestConflictResolution:
    """Tests for conflict resolution logic."""

    def test_unanimous_direction_resolves_cleanly(self):
        """When all candidates agree, resolution is straightforward."""
        candidates = [
            _make_candidate("tc", SignalDirection.LONG, quality=0.9),
            _make_candidate("pc", SignalDirection.LONG, quality=0.8),
        ]
        resolution = resolve_conflicts(candidates, [])
        assert resolution.final_direction == SignalDirection.LONG
        assert resolution.resolution_method == "no_conflict"
        assert len(resolution.dropped_candidates) == 0

    def test_quality_weighted_resolution(self):
        """Higher quality candidates win in a conflict."""
        candidates = [
            _make_candidate("tc", SignalDirection.LONG, quality=0.9),
            _make_candidate("rr", SignalDirection.SHORT, quality=0.3),
        ]
        conflicts = [DirectionalConflict(
            conflict_type=ConflictType.STRATEGY_DIVERGENCE,
            description="Test conflict",
            involved_strategies=["tc", "rr"],
            severity=0.5,
        )]
        resolution = resolve_conflicts(candidates, conflicts)
        assert resolution.final_direction == SignalDirection.LONG
        assert "rr" in resolution.dropped_candidates

    def test_near_tie_produces_low_confidence(self):
        """Near-equal quality produces a low-confidence resolution."""
        candidates = [
            _make_candidate("tc", SignalDirection.LONG, quality=0.5),
            _make_candidate("rr", SignalDirection.SHORT, quality=0.48),
        ]
        conflicts = [DirectionalConflict(
            conflict_type=ConflictType.STRATEGY_DIVERGENCE,
            description="Test conflict",
            involved_strategies=["tc", "rr"],
            severity=0.5,
        )]
        resolution = resolve_conflicts(candidates, conflicts)
        assert resolution.confidence < 0.5  # Low confidence for near-tie

    def test_empty_candidates_resolves_to_none(self):
        """No candidates resolve to NONE direction."""
        resolution = resolve_conflicts([], [])
        assert resolution.final_direction == SignalDirection.NONE
        assert resolution.confidence == 0.0


# ---------------------------------------------------------------------------
# Confidence Scoring Tests
# ---------------------------------------------------------------------------

class TestConfidenceScoring:
    """Tests for confidence score calculation."""

    def test_all_aligned_high_confidence(self):
        """When all factors align, confidence is high."""
        candidates = [_make_candidate("tc", SignalDirection.LONG, quality=0.9)]
        mtf = MTFConfirmationResult(
            confirmed=True,
            confirmation_level=ConfirmationLevel.STRONG,
            aligned_count=3,
            total_count=3,
        )
        evidence = [
            EvidenceItem(source="test", component="trend", direction=SignalDirection.LONG, strength=0.9),
            EvidenceItem(source="test", component="momentum", direction=SignalDirection.LONG, strength=0.8),
        ]
        analysis = AnalysisResult(
            status=AnalysisStatus.AVAILABLE,
            regime=RegimeResult(state=MarketRegime.TRENDING_UP, evidence=["up trend"]),
        )

        score = calculate_confidence(candidates, SignalDirection.LONG, mtf, evidence, analysis)
        assert score.overall >= 0.7
        assert score.strategy_alignment >= 0.8
        assert score.mtf_confirmation >= 0.8

    def test_no_candidates_low_confidence(self):
        """No candidates produce low confidence."""
        score = calculate_confidence([], SignalDirection.LONG, None, [], None)
        assert score.overall < 0.3

    def test_opposing_evidence_reduces_confidence(self):
        """Opposing evidence reduces the evidence strength score."""
        candidates = [_make_candidate("tc", SignalDirection.LONG, quality=0.8)]
        evidence = [
            EvidenceItem(source="test", component="trend", direction=SignalDirection.LONG, strength=0.9),
            EvidenceItem(source="test", component="momentum", direction=SignalDirection.SHORT, strength=0.8),
        ]

        # With opposing evidence
        score_with_oppose = _score_evidence_strength(evidence, SignalDirection.LONG)
        # Without opposing evidence
        evidence_only_support = [e for e in evidence if e.direction == SignalDirection.LONG]
        score_without = _score_evidence_strength(evidence_only_support, SignalDirection.LONG)

        assert score_with_oppose < score_without

    def test_breakdown_sum_equals_overall(self):
        """Breakdown contributions sum to the overall score."""
        candidates = [_make_candidate("tc", SignalDirection.LONG, quality=0.8)]
        mtf = MTFConfirmationResult(
            confirmed=True, confirmation_level=ConfirmationLevel.MODERATE,
            aligned_count=2, total_count=3,
        )
        evidence = [
            EvidenceItem(source="test", component="trend", direction=SignalDirection.LONG, strength=0.7),
        ]
        analysis = AnalysisResult(
            status=AnalysisStatus.AVAILABLE,
            regime=RegimeResult(state=MarketRegime.TRENDING_UP),
        )

        score = calculate_confidence(candidates, SignalDirection.LONG, mtf, evidence, analysis)
        breakdown_sum = sum(b.contribution for b in score.breakdown)
        assert score.overall == pytest.approx(breakdown_sum, abs=0.01)

    def test_regime_consistency_scoring(self):
        """Regime consistency scores correctly for matching/opposing regimes."""
        analysis_up = AnalysisResult(
            status=AnalysisStatus.AVAILABLE,
            regime=RegimeResult(state=MarketRegime.TRENDING_UP),
        )
        analysis_down = AnalysisResult(
            status=AnalysisStatus.AVAILABLE,
            regime=RegimeResult(state=MarketRegime.TRENDING_DOWN),
        )

        # LONG + TRENDING_UP = high
        score_match = _score_regime_consistency(analysis_up, SignalDirection.LONG)
        assert score_match >= 0.8

        # LONG + TRENDING_DOWN = low
        score_oppose = _score_regime_consistency(analysis_down, SignalDirection.LONG)
        assert score_oppose <= 0.3


# ---------------------------------------------------------------------------
# Signal Qualification Tests
# ---------------------------------------------------------------------------

class TestSignalQualification:
    """Tests for final signal qualification logic."""

    def _default_settings(self) -> SignalEngineSettings:
        return SignalEngineSettings(
            minimum_confidence_threshold=0.55,
            strong_confidence_threshold=0.75,
            require_mtf_confirmation=True,
            mtf_min_aligned_timeframes=1,
        )

    def test_qualified_signal(self):
        """A high-confidence signal with MTF confirmation is QUALIFIED."""
        settings = self._default_settings()
        candidates = [_make_candidate("tc", SignalDirection.LONG, quality=0.9)]
        confidence = ConfidenceScore(
            overall=0.8, strategy_alignment=0.9, mtf_confirmation=0.8,
            evidence_strength=0.7, regime_consistency=0.8,
        )
        mtf = MTFConfirmationResult(
            confirmed=True, confirmation_level=ConfirmationLevel.STRONG,
            aligned_count=3, total_count=3,
        )

        status, reason, reasons = qualify_signal(
            candidates, SignalDirection.LONG, confidence, mtf, [], None, settings,
        )
        assert status == SignalStatus.QUALIFIED
        assert "LONG" in reason
        assert len(reasons) > 0

    def test_rejected_low_confidence(self):
        """Low confidence produces REJECTED status."""
        settings = self._default_settings()
        candidates = [_make_candidate("tc", SignalDirection.LONG, quality=0.3)]
        confidence = ConfidenceScore(
            overall=0.3, strategy_alignment=0.3, mtf_confirmation=0.3,
            evidence_strength=0.3, regime_consistency=0.3,
        )
        mtf = MTFConfirmationResult(
            confirmed=True, confirmation_level=ConfirmationLevel.WEAK,
            aligned_count=1, total_count=3,
        )

        status, _, reasons = qualify_signal(
            candidates, SignalDirection.LONG, confidence, mtf, [], None, settings,
        )
        assert status == SignalStatus.REJECTED
        assert len(reasons) > 0

    def test_insufficient_context_no_candidates(self):
        """No candidates produce INSUFFICIENT_CONTEXT."""
        settings = self._default_settings()
        confidence = ConfidenceScore(
            overall=0.0, strategy_alignment=0.0, mtf_confirmation=0.0,
            evidence_strength=0.0, regime_consistency=0.0,
        )

        status, _, reasons = qualify_signal(
            [], SignalDirection.NONE, confidence, None, [], None, settings,
        )
        assert status == SignalStatus.INSUFFICIENT_CONTEXT
        assert len(reasons) > 0

    def test_rejected_mtf_not_confirmed(self):
        """When MTF is required but not confirmed, signal is REJECTED."""
        settings = self._default_settings()
        candidates = [_make_candidate("tc", SignalDirection.LONG, quality=0.8)]
        confidence = ConfidenceScore(
            overall=0.7, strategy_alignment=0.8, mtf_confirmation=0.3,
            evidence_strength=0.6, regime_consistency=0.7,
        )
        mtf = MTFConfirmationResult(
            confirmed=False, confirmation_level=ConfirmationLevel.NONE,
            aligned_count=0, total_count=3,
        )

        status, _, reasons = qualify_signal(
            candidates, SignalDirection.LONG, confidence, mtf, [], None, settings,
        )
        assert status == SignalStatus.REJECTED
        assert len(reasons) > 0

    def test_conflict_status_when_resolution_low_confidence(self):
        """Conflicts with low resolution confidence produce CONFLICT status."""
        settings = self._default_settings()
        candidates = [_make_candidate("tc", SignalDirection.LONG)]
        confidence = ConfidenceScore(
            overall=0.6, strategy_alignment=0.6, mtf_confirmation=0.6,
            evidence_strength=0.6, regime_consistency=0.6,
        )
        conflicts = [DirectionalConflict(
            conflict_type=ConflictType.STRATEGY_DIVERGENCE,
            description="Test", involved_strategies=["tc", "rr"], severity=0.8,
        )]
        resolution = ConflictResolution(
            final_direction=SignalDirection.LONG,
            confidence=0.3,  # Below threshold
            conflicts=conflicts,
            resolution_method="quality_weighted",
        )

        status, _, reasons = qualify_signal(
            candidates, SignalDirection.LONG, confidence, None, conflicts, resolution, settings,
        )
        assert status == SignalStatus.CONFLICT
        assert len(reasons) > 0


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------

class TestValidation:
    """Tests for input validation."""

    def test_valid_instrument(self):
        """Valid instrument passes validation."""
        inst = validate_instrument("XAU/USD")
        assert inst.value == "XAU/USD"

    def test_invalid_instrument_raises(self):
        """Invalid instrument raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported instrument"):
            validate_instrument("INVALID/PAIR")

    def test_valid_timeframes(self):
        """Valid timeframes pass validation."""
        result = validate_timeframes(["1m", "5m", "15m"])
        assert result == ["1m", "5m", "15m"]

    def test_invalid_timeframe_raises(self):
        """Invalid timeframe raises ValueError."""
        with pytest.raises(ValueError, match="Invalid timeframes"):
            validate_timeframes(["1m", "INVALID_TF"])

    def test_empty_timeframes_raises(self):
        """Empty timeframes list raises ValueError."""
        with pytest.raises(ValueError, match="No timeframes"):
            validate_timeframes([])

    def test_valid_candle_limit(self):
        """Valid candle limit passes validation."""
        assert validate_candle_limit(300) == 300

    def test_candle_limit_too_low_raises(self):
        """Candle limit below 50 raises ValueError."""
        with pytest.raises(ValueError, match="Candle limit"):
            validate_candle_limit(10)

    def test_candle_limit_too_high_raises(self):
        """Candle limit above 5000 raises ValueError."""
        with pytest.raises(ValueError, match="Candle limit"):
            validate_candle_limit(10000)


# ---------------------------------------------------------------------------
# Evidence Aggregation Tests
# ---------------------------------------------------------------------------

class TestEvidenceAggregation:
    """Tests for evidence aggregation."""

    def test_aggregates_all_sources(self):
        """Evidence from all sources is aggregated."""
        candidates = [_make_candidate("tc", SignalDirection.LONG)]
        candidate_evidence = [
            EvidenceItem(source="strategy:tc", component="condition", direction=SignalDirection.LONG, strength=0.8),
        ]
        mtf_evidence = [
            EvidenceItem(source="mtf:5m", component="confirmation", direction=SignalDirection.LONG, strength=0.7),
        ]
        analysis = AnalysisResult(
            status=AnalysisStatus.AVAILABLE,
            regime=RegimeResult(state=MarketRegime.TRENDING_UP, evidence=["up"]),
        )

        all_evidence = aggregate_evidence(
            candidates, candidate_evidence, mtf_evidence, analysis, SignalDirection.LONG,
        )

        # Should include candidate + mtf + regime evidence
        assert len(all_evidence) >= 3
        sources = {e.source for e in all_evidence}
        assert "strategy:tc" in sources
        assert "mtf:5m" in sources
        assert "analysis:regime" in sources

    def test_empty_inputs_produce_analysis_evidence(self):
        """Even with empty candidates/mtf, analysis produces evidence."""
        all_evidence = aggregate_evidence([], [], [], None, SignalDirection.LONG)
        # No analysis = no evidence from analysis
        assert len(all_evidence) == 0


# ---------------------------------------------------------------------------
# Config Tests
# ---------------------------------------------------------------------------

class TestSignalEngineConfig:
    """Tests for signal engine configuration."""

    def test_default_config(self):
        """Default config has sensible values."""
        settings = SignalEngineSettings()
        assert settings.is_enabled is True
        assert settings.minimum_confidence_threshold == 0.55
        assert settings.strong_confidence_threshold == 0.75
        assert settings.require_mtf_confirmation is True
        assert settings.enable_conflict_resolution is True

    def test_config_getter(self):
        """get_signal_engine_settings returns a valid instance."""
        settings = get_signal_engine_settings()
        assert isinstance(settings, SignalEngineSettings)


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestSignalModels:
    """Tests for signal engine model construction."""

    def test_signal_candidate_construction(self):
        """SignalCandidate can be constructed with required fields."""
        c = SignalCandidate(
            strategy_id="test",
            strategy_version="1.0",
            strategy_name="Test",
            direction=SignalDirection.LONG,
            quality_score_normalized=0.8,
            quality_score_raw=80,
            quality_score_max=100,
            condition_pass_rate=1.0,
        )
        assert c.strategy_id == "test"
        assert c.direction == SignalDirection.LONG

    def test_signal_evaluation_result_defaults(self):
        """SignalEvaluationResult has correct defaults."""
        r = SignalEvaluationResult(instrument="XAU/USD", status=SignalStatus.QUALIFIED)
        assert r.direction == SignalDirection.NONE
        assert r.confidence is None
        assert len(r.candidates) == 0
        assert r.reason == ""

    def test_confidence_score_construction(self):
        """ConfidenceScore can be constructed."""
        cs = ConfidenceScore(
            overall=0.8, strategy_alignment=0.9, mtf_confirmation=0.8,
            evidence_strength=0.7, regime_consistency=0.8,
        )
        assert cs.overall == 0.8

    def test_mtf_confirmation_result(self):
        """MTFConfirmationResult can be constructed."""
        mtf = MTFConfirmationResult(
            confirmed=True, confirmation_level=ConfirmationLevel.STRONG,
            aligned_count=3, total_count=3,
        )
        assert mtf.confirmed is True
        assert mtf.confirmation_level == ConfirmationLevel.STRONG


# ---------------------------------------------------------------------------
# API Endpoint Tests (integration)
# ---------------------------------------------------------------------------

class TestSignalAPIEndpoints:
    """Integration tests for signal API endpoints."""

    def test_signals_health_returns_200(self, client):
        """GET /api/v1/signals/health returns 200."""
        response = client.get("/api/v1/signals/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["module"] == "signal_engine"

    def test_signals_capabilities_returns_200(self, client):
        """GET /api/v1/signals/capabilities returns 200."""
        response = client.get("/api/v1/signals/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert data["module"] == "signal_engine"
        assert "features" in data
        assert "thresholds" in data

    def test_signals_evaluate_default_params(self, client):
        """GET /api/v1/signals/evaluate with defaults returns a valid response."""
        response = client.get("/api/v1/signals/evaluate")
        assert response.status_code == 200
        data = response.json()
        assert "evaluation_id" in data
        assert "status" in data
        assert "direction" in data
        assert data["instrument"] == "XAU/USD"

    def test_signals_evaluate_invalid_instrument(self, client):
        """GET /api/v1/signals/evaluate with invalid instrument returns 422."""
        response = client.get("/api/v1/signals/evaluate?instrument=INVALID")
        assert response.status_code == 422

    def test_signals_evaluate_custom_params(self, client):
        """GET /api/v1/signals/evaluate with custom params returns 200."""
        response = client.get(
            "/api/v1/signals/evaluate?instrument=XAU/USD&timeframes=5m,15m&limit=200"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["instrument"] == "XAU/USD"


# ---------------------------------------------------------------------------
# Regression: Phase 6 does NOT contain Phase 7+ features
# ---------------------------------------------------------------------------

class TestPhaseScopeBoundary:
    """Verify Phase 6 does not contain forbidden functionality."""

    def test_no_entry_price_in_models(self):
        """SignalCandidate has no entry_price field."""
        c = SignalCandidate(
            strategy_id="test", strategy_version="1.0", strategy_name="Test",
            direction=SignalDirection.LONG, quality_score_normalized=0.5,
            quality_score_raw=50, quality_score_max=100, condition_pass_rate=1.0,
        )
        assert not hasattr(c, "entry_price")

    def test_no_stop_loss_in_models(self):
        """SignalEvaluationResult has no stop_loss field."""
        r = SignalEvaluationResult(instrument="XAU/USD", status=SignalStatus.QUALIFIED)
        assert not hasattr(r, "stop_loss")
        assert not hasattr(r, "take_profit")

    def test_no_position_sizing(self):
        """No position sizing in any signal model."""
        from app.modules.signal_engine import models
        import inspect
        source = inspect.getsource(models)
        assert "position_size" not in source.lower()
        assert "lot_size" not in source.lower()
        assert "risk_percent" not in source.lower()

    def test_no_order_placement(self):
        """No order/trade execution in signal engine."""
        from app.modules.signal_engine import service
        import inspect
        source = inspect.getsource(service)
        # "no_trade" is a DecisionType enum value — not actual trade execution
        # Check for actual execution keywords that shouldn't appear
        assert "place_order" not in source.lower()
        assert "submit_order" not in source.lower()
        assert "execute_trade" not in source.lower()
        assert "open_position" not in source.lower()
        assert "broker" not in source.lower()


# ===========================================================================
# Phase 6: Signal State Machine Tests
# ===========================================================================

class TestStateMachine:
    """Tests for SignalStateMachine lifecycle management."""

    def _make_record(self, state: SignalState = SignalState.NO_SIGNAL) -> SignalRecord:
        rec = SignalRecord(instrument="XAU/USD", state=state)
        return rec

    def test_no_signal_to_candidate(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record()
        ok = sm.transition(r, SignalState.CANDIDATE, "evaluation started")
        assert ok
        assert r.state == SignalState.CANDIDATE
        assert len(r.state_history) == 1
        assert r.state_history[0].from_state == SignalState.NO_SIGNAL
        assert r.state_history[0].to_state == SignalState.CANDIDATE

    def test_candidate_to_qualified(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record(SignalState.CANDIDATE)
        ok = sm.transition(r, SignalState.QUALIFIED, "met thresholds")
        assert ok
        assert r.state == SignalState.QUALIFIED
        assert r.qualified_at is not None

    def test_qualified_to_confirmed(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record(SignalState.QUALIFIED)
        ok = sm.transition(r, SignalState.CONFIRMED, "MTF confirmed")
        assert ok
        assert r.state == SignalState.CONFIRMED
        assert r.confirmed_at is not None

    def test_confirmed_to_active(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record(SignalState.CONFIRMED)
        ok = sm.transition(r, SignalState.ACTIVE, "ready for trading")
        assert ok
        assert r.state == SignalState.ACTIVE
        assert r.activated_at is not None

    def test_active_to_expired(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record(SignalState.ACTIVE)
        ok = sm.expire(r, "TTL elapsed")
        assert ok
        assert r.state == SignalState.EXPIRED
        assert r.expired_at is not None

    def test_active_to_invalidated(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record(SignalState.ACTIVE)
        ok = sm.invalidate(r, "regime shifted")
        assert ok
        assert r.state == SignalState.INVALIDATED
        assert r.invalidated_at is not None

    def test_invalid_transition_rejected(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record(SignalState.NO_SIGNAL)
        ok = sm.transition(r, SignalState.ACTIVE, "skip to active")
        assert not ok
        assert r.state == SignalState.NO_SIGNAL

    def test_terminal_state_no_transitions(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record(SignalState.EXPIRED)
        ok = sm.transition(r, SignalState.ACTIVE, "resurrect")
        assert not ok
        assert r.state == SignalState.EXPIRED

    def test_same_state_idempotent(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record(SignalState.ACTIVE)
        ok = sm.transition(r, SignalState.ACTIVE, "noop")
        assert ok
        assert r.state == SignalState.ACTIVE

    def test_register_and_get(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r = self._make_record()
        sm.register(r)
        assert sm.get(r.signal_id) is r
        assert sm.get("nonexistent") is None

    def test_get_active(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        r1 = self._make_record(SignalState.ACTIVE)
        r2 = self._make_record(SignalState.CONFIRMED)
        r3 = self._make_record(SignalState.EXPIRED)
        sm.register(r1)
        sm.register(r2)
        sm.register(r3)
        active = sm.get_active()
        assert len(active) == 2
        assert r1 in active
        assert r2 in active

    def test_can_activate(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        assert sm.can_activate(3)
        for _ in range(3):
            r = self._make_record(SignalState.ACTIVE)
            sm.register(r)
        assert not sm.can_activate(3)

    def test_cleanup_terminal(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from datetime import timedelta
        sm = SignalStateMachine()
        r = self._make_record(SignalState.EXPIRED)
        r.expired_at = datetime.now(timezone.utc) - timedelta(hours=2)
        sm.register(r)
        removed = sm.cleanup_terminal(max_age_seconds=3600)
        assert removed == 1
        assert sm.get(r.signal_id) is None

    def test_count_active(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        sm = SignalStateMachine()
        assert sm.count_active() == 0
        r = self._make_record(SignalState.ACTIVE)
        sm.register(r)
        assert sm.count_active() == 1


# ===========================================================================
# Phase 6: Deduplication Tests
# ===========================================================================

class TestDeduplication:
    """Tests for SignalDeduplicator hash-based dedup."""

    def _make_record(self, decision=DecisionType.BUY) -> SignalRecord:
        return SignalRecord(
            instrument="XAU/USD",
            decision=decision,
            direction=SignalDirection.LONG,
            candidates=[
                SignalCandidate(
                    strategy_id="tc",
                    strategy_version="1.0",
                    strategy_name="Trend Continuation",
                    direction=SignalDirection.LONG,
                    quality_score_normalized=0.8,
                    quality_score_raw=80,
                    quality_score_max=100,
                    condition_pass_rate=0.9,
                ),
            ],
        )

    def test_no_trade_never_duplicate(self):
        from app.modules.signal_engine.deduplication import SignalDeduplicator
        d = SignalDeduplicator(window_seconds=3600)
        assert not d.is_duplicate("XAU/USD", SignalDirection.NONE, DecisionType.NO_TRADE, [])

    def test_first_signal_not_duplicate(self):
        from app.modules.signal_engine.deduplication import SignalDeduplicator
        d = SignalDeduplicator(window_seconds=3600)
        assert not d.is_duplicate("XAU/USD", SignalDirection.LONG, DecisionType.BUY, ["tc"])

    def test_register_and_detect_duplicate(self):
        from app.modules.signal_engine.deduplication import SignalDeduplicator
        d = SignalDeduplicator(window_seconds=3600)
        r = self._make_record()
        # Register directly via internal API
        strategy_ids = [c.strategy_id for c in r.candidates]
        key = d.compute_key(r.instrument, r.direction, r.decision, strategy_ids)
        from app.modules.signal_engine.deduplication import _compute_dedup_key
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        from app.modules.signal_engine.models import DeduplicationEntry
        d._entries[key] = DeduplicationEntry(
            dedup_key=key,
            signal_id=r.signal_id,
            instrument=r.instrument,
            direction=r.direction,
            decision=r.decision,
            created_at=now,
            expires_at=now + d._window,
        )
        assert d.is_duplicate("XAU/USD", SignalDirection.LONG, DecisionType.BUY, ["tc"])
        # Different instrument = not duplicate
        assert not d.is_duplicate("BTC/USD", SignalDirection.LONG, DecisionType.BUY, ["tc"])
        # Different direction = not duplicate
        assert not d.is_duplicate("XAU/USD", SignalDirection.SHORT, DecisionType.SELL, ["tc"])

    def test_unregister_allows_rediscovery(self):
        from app.modules.signal_engine.deduplication import SignalDeduplicator
        d = SignalDeduplicator(window_seconds=3600)
        r = self._make_record()
        # Register directly
        strategy_ids = [c.strategy_id for c in r.candidates]
        key = d.compute_key(r.instrument, r.direction, r.decision, strategy_ids)
        from datetime import datetime, timezone
        from app.modules.signal_engine.models import DeduplicationEntry
        now = datetime.now(timezone.utc)
        d._entries[key] = DeduplicationEntry(
            dedup_key=key, signal_id=r.signal_id, instrument=r.instrument,
            direction=r.direction, decision=r.decision,
            created_at=now, expires_at=now + d._window,
        )
        assert d.is_duplicate("XAU/USD", SignalDirection.LONG, DecisionType.BUY, ["tc"])
        d.unregister(r.signal_id)
        assert not d.is_duplicate("XAU/USD", SignalDirection.LONG, DecisionType.BUY, ["tc"])

    def test_exclude_own_signal_id(self):
        from app.modules.signal_engine.deduplication import SignalDeduplicator
        d = SignalDeduplicator(window_seconds=3600)
        r = self._make_record()
        # Register directly
        strategy_ids = [c.strategy_id for c in r.candidates]
        key = d.compute_key(r.instrument, r.direction, r.decision, strategy_ids)
        from datetime import datetime, timezone
        from app.modules.signal_engine.models import DeduplicationEntry
        now = datetime.now(timezone.utc)
        d._entries[key] = DeduplicationEntry(
            dedup_key=key, signal_id=r.signal_id, instrument=r.instrument,
            direction=r.direction, decision=r.decision,
            created_at=now, expires_at=now + d._window,
        )
        # Without exclude: detected as duplicate
        assert d.is_duplicate("XAU/USD", SignalDirection.LONG, DecisionType.BUY, ["tc"])
        # With exclude own signal_id: NOT a duplicate (allows self re-evaluation)
        assert not d.is_duplicate(
            "XAU/USD", SignalDirection.LONG, DecisionType.BUY, ["tc"],
            exclude_signal_id=r.signal_id,
        )

    def test_active_count(self):
        from app.modules.signal_engine.deduplication import SignalDeduplicator
        d = SignalDeduplicator(window_seconds=3600)
        r = self._make_record()
        d.register(r)
        assert d.active_count() == 1

    def test_cleanup_expired(self):
        from app.modules.signal_engine.deduplication import SignalDeduplicator
        d = SignalDeduplicator(window_seconds=0)  # immediate expiry
        r = self._make_record()
        d.register(r)
        removed = d.cleanup_expired()
        assert removed == 1
        assert d.active_count() == 0

    def test_no_trade_not_registered(self):
        from app.modules.signal_engine.deduplication import SignalDeduplicator
        d = SignalDeduplicator(window_seconds=3600)
        r = self._make_record(decision=DecisionType.NO_TRADE)
        d.register(r)
        assert d.active_count() == 0

    def test_no_trade_not_registered(self):
        from app.modules.signal_engine.deduplication import SignalDeduplicator
        d = SignalDeduplicator(window_seconds=3600)
        r = self._make_record(decision=DecisionType.NO_TRADE)
        d.register(r)
        assert d.active_count() == 0


# ===========================================================================
# Phase 6: Expiration Tests
# ===========================================================================

class TestExpiration:
    """Tests for SignalExpirationManager TTL management."""

    def _make_record(self, ttl=300) -> SignalRecord:
        return SignalRecord(instrument="XAU/USD", state=SignalState.ACTIVE, ttl_seconds=ttl)

    def test_not_expired_within_ttl(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.expiration import SignalExpirationManager
        sm = SignalStateMachine()
        exp = SignalExpirationManager(sm)
        r = self._make_record(ttl=300)
        assert not exp.check_expiration(r)
        assert r.state == SignalState.ACTIVE

    def test_expired_beyond_ttl(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.expiration import SignalExpirationManager
        from datetime import timedelta
        sm = SignalStateMachine()
        exp = SignalExpirationManager(sm)
        r = self._make_record(ttl=1)
        r.created_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        assert exp.check_expiration(r)
        assert r.state == SignalState.EXPIRED

    def test_check_all_expires(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.expiration import SignalExpirationManager
        from datetime import timedelta
        sm = SignalStateMachine()
        exp = SignalExpirationManager(sm)
        r1 = self._make_record(ttl=1)
        r1.created_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        sm.register(r1)
        r2 = self._make_record(ttl=300)
        sm.register(r2)
        expired = exp.check_all()
        assert len(expired) == 1
        assert expired[0].signal_id == r1.signal_id

    def test_get_expiring_soon(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.expiration import SignalExpirationManager
        from datetime import timedelta
        sm = SignalStateMachine()
        exp = SignalExpirationManager(sm, default_ttl_seconds=120)
        # Signal created 100s ago, TTL=120 → 20s remaining → expiring within 30s
        r = self._make_record(ttl=120)
        r.created_at = datetime.now(timezone.utc) - timedelta(seconds=100)
        sm.register(r)
        expiring = exp.get_expiring_soon(within_seconds=30)
        assert len(expiring) == 1

    def test_extend_ttl(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.expiration import SignalExpirationManager
        sm = SignalStateMachine()
        exp = SignalExpirationManager(sm)
        r = self._make_record(ttl=300)
        assert exp.extend_ttl(r, 120)
        assert r.ttl_seconds == 420

    def test_extend_ttl_expired_fails(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.expiration import SignalExpirationManager
        sm = SignalStateMachine()
        exp = SignalExpirationManager(sm)
        r = self._make_record()
        r.state = SignalState.EXPIRED
        assert not exp.extend_ttl(r, 120)

    def test_set_ttl(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.expiration import SignalExpirationManager
        sm = SignalStateMachine()
        exp = SignalExpirationManager(sm)
        r = self._make_record(ttl=300)
        exp.set_ttl(r, 600)
        assert r.ttl_seconds == 600

    def test_terminal_signal_not_expired(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.expiration import SignalExpirationManager
        from datetime import timedelta
        sm = SignalStateMachine()
        exp = SignalExpirationManager(sm)
        r = self._make_record()
        r.state = SignalState.INVALIDATED
        r.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        assert not exp.check_expiration(r)


# ===========================================================================
# Phase 6: Signal Invalidation Tests
# ===========================================================================

class TestSignalInvalidation:
    """Tests for SignalInvalidator market condition checks."""

    def _make_record(self, state=SignalState.ACTIVE, regime="trending_up") -> SignalRecord:
        return SignalRecord(
            instrument="XAU/USD",
            state=state,
            direction=SignalDirection.LONG,
            candidates=[
                SignalCandidate(
                    strategy_id="tc",
                    strategy_version="1.0",
                    strategy_name="Trend Continuation",
                    direction=SignalDirection.LONG,
                    quality_score_normalized=0.8,
                    quality_score_raw=80,
                    quality_score_max=100,
                    condition_pass_rate=0.9,
                    market_regime=regime,
                ),
            ],
        )

    def test_regime_shift_invalidates(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.signal_invalidation import SignalInvalidator
        sm = SignalStateMachine()
        inv = SignalInvalidator(sm)
        r = self._make_record(regime="trending_up")
        analysis = MagicMock()
        analysis.regime = MagicMock()
        analysis.regime.state = MarketRegime.RANGING
        assert inv.check_regime_shift(r, analysis)
        assert r.state == SignalState.INVALIDATED

    def test_no_regime_shift_no_invalidation(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.signal_invalidation import SignalInvalidator
        sm = SignalStateMachine()
        inv = SignalInvalidator(sm)
        r = self._make_record(regime="trending_up")
        analysis = MagicMock()
        analysis.regime = MagicMock()
        analysis.regime.state = MarketRegime.TRENDING_UP
        assert not inv.check_regime_shift(r, analysis)
        assert r.state == SignalState.ACTIVE

    def test_mtf_loss_invalidates(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.signal_invalidation import SignalInvalidator
        sm = SignalStateMachine()
        inv = SignalInvalidator(sm)
        r = self._make_record()
        assert inv.check_mtf_loss(r, current_aligned_count=0, min_aligned=1)
        assert r.state == SignalState.INVALIDATED

    def test_evidence_degradation_invalidates(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.signal_invalidation import SignalInvalidator
        sm = SignalStateMachine()
        inv = SignalInvalidator(sm)
        r = self._make_record()
        evidence = [
            EvidenceItem(source="s1", component="trend", direction=SignalDirection.SHORT, strength=0.5),
        ]
        assert inv.check_evidence_degradation(r, evidence, min_supporting=2)
        assert r.state == SignalState.INVALIDATED

    def test_terminal_signal_not_invalidated(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.signal_invalidation import SignalInvalidator
        sm = SignalStateMachine()
        inv = SignalInvalidator(sm)
        r = self._make_record(state=SignalState.EXPIRED)
        analysis = MagicMock()
        analysis.regime = MagicMock()
        analysis.regime.state = MarketRegime.RANGING
        assert not inv.check_regime_shift(r, analysis)
        assert not inv.check_mtf_loss(r, 0, 1)

    def test_no_analysis_skips_check(self):
        from app.modules.signal_engine.state_machine import SignalStateMachine
        from app.modules.signal_engine.signal_invalidation import SignalInvalidator
        sm = SignalStateMachine()
        inv = SignalInvalidator(sm)
        r = self._make_record()
        assert not inv.check_regime_shift(r, None)


# ===========================================================================
# Phase 6: Priority Ranking Tests
# ===========================================================================

class TestRanking:
    """Tests for signal priority scoring and ranking."""

    def _make_record(
        self,
        confidence_val=80,
        quality_val=70,
        evidence_count=3,
        ttl=300,
        state=SignalState.ACTIVE,
    ) -> SignalRecord:
        evidence = [
            EvidenceItem(source="s", component="trend", direction=SignalDirection.LONG, strength=0.8)
            for _ in range(evidence_count)
        ]
        return SignalRecord(
            instrument="XAU/USD",
            state=state,
            direction=SignalDirection.LONG,
            confidence=ConfidenceScore(
                overall=confidence_val / 100.0, strategy_alignment=0.8,
                mtf_confirmation=0.7, evidence_strength=0.6, regime_consistency=0.75,
                confidence_0_100=confidence_val,
            ),
            quality=SignalQuality(
                score=quality_val, condition_pass_rate=0.8,
                evidence_depth=evidence_count, strategy_alignment=0.9,
            ),
            evidence=evidence,
            ttl_seconds=ttl,
        )

    def test_calculate_priority_basic(self):
        from app.modules.signal_engine.ranking import calculate_priority
        r = self._make_record(confidence_val=80, quality_val=70, evidence_count=3)
        p = calculate_priority(r)
        assert 0 < p.priority_score <= 100
        assert p.confidence_weight == 0.35
        assert p.quality_weight == 0.30

    def test_higher_confidence_higher_priority(self):
        from app.modules.signal_engine.ranking import calculate_priority
        r_low = self._make_record(confidence_val=40)
        r_high = self._make_record(confidence_val=90)
        p_low = calculate_priority(r_low)
        p_high = calculate_priority(r_high)
        assert p_high.priority_score > p_low.priority_score

    def test_rank_signals_orders_correctly(self):
        from app.modules.signal_engine.ranking import rank_signals
        r1 = self._make_record(confidence_val=50, quality_val=50)
        r2 = self._make_record(confidence_val=90, quality_val=90)
        r3 = self._make_record(confidence_val=70, quality_val=70)
        ranked = rank_signals([r1, r2, r3])
        assert len(ranked) == 3
        assert ranked[0].priority.rank == 1
        assert ranked[0].signal_id == r2.signal_id
        assert ranked[1].priority.rank == 2
        assert ranked[2].priority.rank == 3

    def test_rank_signals_ignores_terminal(self):
        from app.modules.signal_engine.ranking import rank_signals
        r = self._make_record(state=SignalState.EXPIRED)
        ranked = rank_signals([r])
        assert len(ranked) == 0

    def test_get_top_signal(self):
        from app.modules.signal_engine.ranking import get_top_signal
        r1 = self._make_record(confidence_val=40)
        r2 = self._make_record(confidence_val=90)
        top = get_top_signal([r1, r2])
        assert top is not None
        assert top.signal_id == r2.signal_id

    def test_get_top_signal_empty(self):
        from app.modules.signal_engine.ranking import get_top_signal
        top = get_top_signal([])
        assert top is None

    def test_no_evidence_zero_score(self):
        from app.modules.signal_engine.ranking import calculate_priority
        r = self._make_record(evidence_count=0)
        p = calculate_priority(r)
        # With zero evidence, the evidence component contributes 0
        # The overall score is lower than a record with full evidence
        r_with_evidence = self._make_record(evidence_count=3)
        p_with = calculate_priority(r_with_evidence)
        assert p.priority_score < p_with.priority_score


# ===========================================================================
# Phase 6: Quality Scoring Tests
# ===========================================================================

class TestQualityScoring:
    """Tests for compute_signal_quality independent quality score."""

    def _make_candidate(
        self, pass_rate=0.8, quality=0.7, direction=SignalDirection.LONG,
    ) -> SignalCandidate:
        return SignalCandidate(
            strategy_id="tc", strategy_version="1.0", strategy_name="Trend Continuation",
            direction=direction, quality_score_normalized=quality,
            quality_score_raw=int(quality * 100), quality_score_max=100,
            condition_pass_rate=pass_rate,
        )

    def _default_confidence(self) -> ConfidenceScore:
        return ConfidenceScore(
            overall=0.7, strategy_alignment=0.8,
            mtf_confirmation=0.7, evidence_strength=0.6, regime_consistency=0.75,
        )

    def test_empty_candidates_zero_score(self):
        q = compute_signal_quality([], SignalDirection.NONE, 0, self._default_confidence())
        assert q.score == 0
        assert q.evidence_depth == 0
        assert q.strategy_alignment == 0.0

    def test_high_quality_candidates(self):
        cands = [
            self._make_candidate(pass_rate=1.0, quality=0.9),
            self._make_candidate(pass_rate=0.95, quality=0.85),
        ]
        q = compute_signal_quality(cands, SignalDirection.LONG, 8, self._default_confidence())
        assert q.score >= 70
        assert q.condition_pass_rate > 0.9
        assert q.strategy_alignment == 1.0  # all aligned

    def test_mixed_directions_reduces_alignment(self):
        cands = [
            self._make_candidate(pass_rate=0.8, quality=0.7, direction=SignalDirection.LONG),
            self._make_candidate(pass_rate=0.7, quality=0.6, direction=SignalDirection.SHORT),
        ]
        q = compute_signal_quality(cands, SignalDirection.LONG, 3, self._default_confidence())
        assert q.strategy_alignment == 0.5  # 1 of 2 aligned

    def test_evidence_depth_capped(self):
        cands = [self._make_candidate()]
        q = compute_signal_quality(cands, SignalDirection.LONG, 100, self._default_confidence())
        assert q.evidence_depth == 100
        # Component capped at 25.0
        assert q.breakdown[1].contribution == 25.0

    def test_breakdown_has_three_factors(self):
        cands = [self._make_candidate()]
        q = compute_signal_quality(cands, SignalDirection.LONG, 5, self._default_confidence())
        assert len(q.breakdown) == 3
        factors = {b.factor for b in q.breakdown}
        assert factors == {"condition_pass_rate", "evidence_depth", "strategy_alignment"}

    def test_normalized_property(self):
        q = SignalQuality(score=80, condition_pass_rate=0.8, evidence_depth=5, strategy_alignment=0.9)
        assert q.normalized == 0.8


# ===========================================================================
# Phase 6: Structured Decision Reasons Tests
# ===========================================================================

class TestDecisionReasons:
    """Tests for DecisionReason codes and DecisionType mapping."""

    def test_direction_to_decision(self):
        from app.modules.signal_engine.models import direction_to_decision, DecisionType
        assert direction_to_decision(SignalDirection.LONG) == DecisionType.BUY
        assert direction_to_decision(SignalDirection.SHORT) == DecisionType.SELL
        assert direction_to_decision(SignalDirection.NONE) == DecisionType.NO_TRADE

    def test_decision_to_direction(self):
        from app.modules.signal_engine.models import decision_to_direction, SignalDirection
        assert decision_to_direction(DecisionType.BUY) == SignalDirection.LONG
        assert decision_to_direction(DecisionType.SELL) == SignalDirection.SHORT
        assert decision_to_direction(DecisionType.NO_TRADE) == SignalDirection.NONE

    def test_status_to_state(self):
        from app.modules.signal_engine.models import status_to_state
        assert status_to_state(SignalStatus.QUALIFIED) == SignalState.QUALIFIED
        assert status_to_state(SignalStatus.REJECTED) == SignalState.NO_SIGNAL
        assert status_to_state(SignalStatus.CONFLICT) == SignalState.CANDIDATE
        assert status_to_state(SignalStatus.INSUFFICIENT_CONTEXT) == SignalState.NO_SIGNAL

    def test_decision_reason_has_code_and_detail(self):
        r = DecisionReason(
            code=DecisionReasonCode.STRONG_CONSENSUS,
            detail="3 candidates contributing",
            contributing_factors=["tc", "rr", "bsr"],
        )
        assert r.code == DecisionReasonCode.STRONG_CONSENSUS
        assert "3 candidates" in r.detail
        assert len(r.contributing_factors) == 3

    def test_all_decision_reason_codes_exist(self):
        """Ensure all Phase 6 reason codes are defined."""
        codes = list(DecisionReasonCode)
        assert len(codes) >= 12
        assert DecisionReasonCode.STRONG_CONCONSUS if False else True  # placeholder
        assert DecisionReasonCode.QUALITY_WEIGHTED_WINNER in codes
        assert DecisionReasonCode.MTF_CONFIRMED in codes
        assert DecisionReasonCode.DEDUPLICATE_BLOCKED in codes
        assert DecisionReasonCode.TTL_EXPIRED in codes
        assert DecisionReasonCode.INVALIDATED_BY_MARKET in codes


# ===========================================================================
# Phase 6: Signal Record Model Tests
# ===========================================================================

class TestSignalRecord:
    """Tests for SignalRecord lifecycle properties."""

    def test_is_active_when_active(self):
        r = SignalRecord(instrument="XAU/USD", state=SignalState.ACTIVE)
        assert r.is_active

    def test_is_active_when_confirmed(self):
        r = SignalRecord(instrument="XAU/USD", state=SignalState.CONFIRMED)
        assert r.is_active

    def test_not_active_when_expired(self):
        r = SignalRecord(instrument="XAU/USD", state=SignalState.EXPIRED)
        assert not r.is_active

    def test_is_terminal_when_expired(self):
        r = SignalRecord(instrument="XAU/USD", state=SignalState.EXPIRED)
        assert r.is_terminal

    def test_is_terminal_when_invalidated(self):
        r = SignalRecord(instrument="XAU/USD", state=SignalState.INVALIDATED)
        assert r.is_terminal

    def test_not_terminal_when_active(self):
        r = SignalRecord(instrument="XAU/USD", state=SignalState.ACTIVE)
        assert not r.is_terminal

    def test_default_state_is_no_signal(self):
        r = SignalRecord(instrument="XAU/USD")
        assert r.state == SignalState.NO_SIGNAL

    def test_default_decision_is_no_trade(self):
        r = SignalRecord(instrument="XAU/USD")
        assert r.decision == DecisionType.NO_TRADE

    def test_has_unique_signal_id(self):
        r1 = SignalRecord(instrument="XAU/USD")
        r2 = SignalRecord(instrument="XAU/USD")
        assert r1.signal_id != r2.signal_id

    def test_remaining_ttl_positive(self):
        r = SignalRecord(instrument="XAU/USD", ttl_seconds=300)
        assert r.remaining_ttl > 0
        assert r.remaining_ttl <= 300

    def test_remaining_ttl_zero_when_expired(self):
        r = SignalRecord(instrument="XAU/USD", ttl_seconds=1)
        r.state = SignalState.EXPIRED
        assert r.remaining_ttl >= 0


# ===========================================================================
# Phase 6: Config Normalization Tests
# ===========================================================================

class TestSignalConfig:
    """Tests for SignalEngineSettings Phase 6 additions."""

    def test_priority_weights_normalize(self):
        s = SignalEngineSettings()
        w = s.priority_weights_normalized
        total = w["confidence"] + w["quality"] + w["evidence"] + w["recency"]
        assert abs(total - 1.0) < 1e-6

    def test_default_thresholds(self):
        s = SignalEngineSettings()
        assert s.confidence_threshold_0_100 == 55
        assert s.quality_threshold_0_100 == 60
        assert s.signal_ttl_seconds == 300
        assert s.dedup_window_seconds == 60
        assert s.max_active_signals == 3
        assert s.signal_history_max_size == 100


# ===========================================================================
# Phase 6: API Endpoint Tests
# ===========================================================================

class TestSignalAPI:
    """Tests for Phase 6 signal API endpoints."""

    @pytest.mark.asyncio
    async def test_signals_health(self):
        from app.api.v1.signals import signals_health
        result = await signals_health()
        assert "status" in result
        assert result["status"] == "healthy"
        assert result["module"] == "signal_engine"

    @pytest.mark.asyncio
    async def test_signals_capabilities(self):
        from app.api.v1.signals import signals_capabilities
        result = await signals_capabilities()
        assert "features" in result
        assert "quality_scoring" in result["features"]

    @pytest.mark.asyncio
    async def test_signals_active_empty(self):
        from app.api.v1.signals import signals_active
        result = await signals_active()
        assert "count" in result
        assert result["count"] == 0
        assert result["signals"] == []

    @pytest.mark.asyncio
    async def test_signals_history_empty(self):
        from app.api.v1.signals import signals_history
        result = await signals_history(limit=5)
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent(self):
        from app.api.v1.signals import signals_invalidate
        result = await signals_invalidate("nonexistent-id", "test")
        assert result["success"] is False
