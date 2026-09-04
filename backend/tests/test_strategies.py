"""
Scalping Arise — Phase 5 Strategy Engine Tests

Deterministic, isolated tests for strategy definitions, eligibility gate,
condition engine, invalidation evaluator, quality scorer, and API endpoints.
Uses hand-crafted data — no external API calls.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment before any app imports
os.environ["SCALPING_ARISE_ENVIRONMENT"] = "testing"
os.environ["SCALPING_ARISE_DEBUG"] = "true"
os.environ["SCALPING_ARISE_LOG_LEVEL"] = "WARNING"

from app.modules.market_analysis.models import (
    AnalysisResult,
    AnalysisStatus,
    MarketRegime,
    StructureLabel,
    StructureResult,
    StructurePoint,
    TrendResult,
    TrendState,
    EventsResult,
    ZonesResult,
    RegimeResult,
    SwingPoint,
    SwingType,
)
from app.modules.market_data.models import (
    Instrument,
    SourceType,
    Timeframe,
)
from app.modules.strategies.config import StrategyEngineSettings, get_strategy_engine_settings
from app.modules.strategies.definitions import (
    ALL_STRATEGIES,
    TREND_CONTINUATION,
    PULLBACK_CONTINUATION,
    RANGE_REVERSAL,
    get_all_strategy_definitions,
    get_strategy_definition,
)
from app.modules.strategies.eligibility import run_eligibility_gate, check_source_compatibility
from app.modules.strategies.condition_engine import evaluate_conditions
from app.modules.strategies.invalidation import evaluate_invalidation_rules
from app.modules.strategies.quality import calculate_quality_score
from app.modules.technical_features.models import FeatureSetStatus
from app.modules.strategies.models import (
    ConditionCriticality,
    ConditionResult,
    ConditionStatus,
    EligibilityResult,
    QualityScore,
    SourceCompatibilityPolicy,
    StrategyDefinition,
    StrategyDirection,
    StrategyEvaluationStatus,
    TimeframeContext,
    TimeframeRole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_structure_point(label: StructureLabel, price: float = 2000.0) -> StructurePoint:
    """Create a StructurePoint with the given label."""
    from datetime import datetime, timezone
    sp = SwingPoint(
        index=0,
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        price=price,
        swing_type=SwingType.SWING_HIGH,
        timeframe="1h",
    )
    return StructurePoint(swing=sp, label=label)


def _rising_analysis() -> AnalysisResult:
    """Build an AnalysisResult for a rising market."""
    return AnalysisResult(
        status=AnalysisStatus.AVAILABLE,
        trend=TrendResult(
            state=TrendState.BULLISH,
            reason="price above EMA50",
        ),
        structure=StructureResult(
            latest_labels=[StructureLabel.HH, StructureLabel.HL, StructureLabel.HH],
        ),
        regime=RegimeResult(
            state=MarketRegime.TRENDING_UP,
            evidence=["EMA stack bullish"],
        ),
    )


def _bearish_analysis() -> AnalysisResult:
    """Build an AnalysisResult for a falling market."""
    return AnalysisResult(
        status=AnalysisStatus.AVAILABLE,
        trend=TrendResult(
            state=TrendState.BEARISH,
            reason="price below EMA50",
        ),
        structure=StructureResult(
            latest_labels=[StructureLabel.LL, StructureLabel.LH, StructureLabel.LL],
        ),
        regime=RegimeResult(
            state=MarketRegime.TRENDING_DOWN,
            evidence=["EMA stack bearish"],
        ),
    )


def _ranging_analysis() -> AnalysisResult:
    """Build an AnalysisResult for a ranging market."""
    return AnalysisResult(
        status=AnalysisStatus.AVAILABLE,
        trend=TrendResult(
            state=TrendState.RANGING,
            reason="no clear trend",
        ),
        structure=StructureResult(
            latest_labels=[StructureLabel.HH, StructureLabel.LL, StructureLabel.HH],
        ),
        regime=RegimeResult(
            state=MarketRegime.RANGING,
            evidence=["Sideways structure"],
        ),
    )


def _make_feature_result():
    """Create a minimal FeatureResult for testing."""
    from app.modules.technical_features.models import (
        EMAAlignment,
        EMAValue,
        EMAResult,
        FeatureAvailability,
        FeatureMetadata,
        FeatureResult,
        FeatureSetStatus,
        RSIResult,
        RSISessionState,
        MACDResult,
        MACDContext,
        ATRResult,
        ATRVolatilityState,
        BollingerBandsResult,
        BollingerPosition,
        VolumeResult,
        VolumeState,
        PriceFeatures,
        EMADirection,
    )

    ema_val = EMAValue(
        period=20, value=2000.0, availability=FeatureAvailability.AVAILABLE,
        direction=EMADirection.RISING, price_relative="above", required_history=20,
    )
    ema_medium = EMAValue(
        period=50, value=1990.0, availability=FeatureAvailability.AVAILABLE,
        direction=EMADirection.FLAT, price_relative="above", required_history=50,
    )
    ema_slow = EMAValue(
        period=200, value=1950.0, availability=FeatureAvailability.AVAILABLE,
        direction=EMADirection.FLAT, price_relative="above", required_history=200,
    )
    trend = EMAResult(
        fast=ema_val, medium=ema_medium, slow=ema_slow,
        alignment=EMAAlignment.BULLISH, alignment_evidence=["Bullish EMA stack"],
    )
    rsi = RSIResult(
        period=14, value=55.0, availability=FeatureAvailability.AVAILABLE,
        state=RSISessionState.NEUTRAL, required_history=15,
    )
    macd = MACDResult(
        macd_line=5.0, signal_line=3.0, histogram=2.0,
        fast_period=12, slow_period=26, signal_period=9,
        availability=FeatureAvailability.AVAILABLE,
        context=MACDContext.BULLISH,
        macd_line_availability=FeatureAvailability.AVAILABLE,
        signal_line_availability=FeatureAvailability.AVAILABLE,
        histogram_availability=FeatureAvailability.AVAILABLE,
        required_history=35,
    )
    atr = ATRResult(
        period=14, value=15.0, percentage=0.75,
        availability=FeatureAvailability.AVAILABLE,
        state=ATRVolatilityState.NORMAL, required_history=15,
    )
    bb = BollingerBandsResult(
        middle_band=2000.0, upper_band=2040.0, lower_band=1960.0,
        band_width=4.0, period=20, std_dev=2.0,
        availability=FeatureAvailability.AVAILABLE,
        price_position=BollingerPosition.MIDDLE_REGION,
        required_history=20,
    )
    vol = VolumeResult(
        sma_period=20, current_volume=1200.0, average_volume=1000.0, relative_volume=1.2,
        availability=FeatureAvailability.AVAILABLE,
        state=VolumeState.NORMAL, required_history=20,
    )
    price = PriceFeatures(
        current_price=2000.0, previous_close=1998.0,
        absolute_change=2.0, percentage_change=0.1,
        lookback=20,
        availability=FeatureAvailability.AVAILABLE,
    )
    metadata = FeatureMetadata(
        canonical_instrument="XAU/USD",
        provider_instrument="GC=F",
        provider="yfinance",
        source_type="futures_proxy",
        timeframe="1h",
        candle_count=300,
    )
    return FeatureResult(
        status=FeatureAvailability.AVAILABLE,
        trend=trend, momentum={"rsi": rsi, "macd": macd},
        volatility={"atr": atr, "bollinger_bands": bb},
        volume=vol, price=price,
        feature_set_status=FeatureSetStatus.READY,
        metadata=metadata,
    )


def _make_tf_context(tf: str = "1h", source_type: str = "futures_proxy", count: int = 300):
    """Build a TimeframeContext for eligibility tests."""
    return TimeframeContext(
        timeframe=tf, source_type=source_type,
        provider="yfinance", provider_instrument="GC=F", candle_count=count,
    )


# ---------------------------------------------------------------------------
# Configuration Tests
# ---------------------------------------------------------------------------

class TestConfiguration:
    """StrategyEngineSettings validation."""

    def test_default_settings(self):
        cfg = get_strategy_engine_settings()
        assert cfg.strategy_engine_enabled is True
        assert cfg.max_strategies_per_evaluation == 10
        assert cfg.default_evaluation_timeframes == ["1m", "5m", "15m"]
        assert cfg.quality_score_enabled is True
        assert len(cfg.enabled_strategies) == 3

    def test_settings_is_enabled_property(self):
        cfg = get_strategy_engine_settings()
        assert cfg.is_enabled is True

    def test_settings_disabled(self):
        cfg = StrategyEngineSettings(strategy_engine_enabled=False)
        assert cfg.is_enabled is False


# ---------------------------------------------------------------------------
# Strategy Definition Tests
# ---------------------------------------------------------------------------

class TestStrategyDefinitions:
    """Strategy definition registry and structure."""

    def test_all_strategies_registry_count(self):
        strategies = get_all_strategy_definitions()
        assert len(strategies) == 3

    def test_get_strategy_definition_valid(self):
        s = get_strategy_definition("trend_continuation")
        assert s is not None
        assert s.strategy_id == "trend_continuation"
        assert s.strategy_name == "Trend Continuation"
        assert s.strategy_version == "1.0"
        assert s.enabled is True

    def test_get_strategy_definition_invalid(self):
        s = get_strategy_definition("nonexistent_strategy")
        assert s is None

    def test_trend_continuation_def_exists(self):
        s = TREND_CONTINUATION
        assert s.strategy_id == "trend_continuation"
        assert len(s.required_timeframes) > 0
        assert len(s.required_conditions) > 0
        assert len(s.invalidation_rules) > 0

    def test_pullback_continuation_def_exists(self):
        s = PULLBACK_CONTINUATION
        assert s.strategy_id == "pullback_continuation"
        assert len(s.required_timeframes) > 0

    def test_range_reversal_def_exists(self):
        s = RANGE_REVERSAL
        assert s.strategy_id == "range_reversal"
        assert len(s.required_timeframes) > 0

    def test_all_strategies_unique_ids(self):
        strategies = get_all_strategy_definitions()
        ids = [s.strategy_id for s in strategies]
        assert len(ids) == len(set(ids))

    def test_all_strategies_have_version(self):
        strategies = get_all_strategy_definitions()
        for s in strategies:
            assert s.strategy_version, f"{s.strategy_id} missing version"
            assert len(s.strategy_version) > 0

    def test_all_strategies_have_regimes(self):
        strategies = get_all_strategy_definitions()
        for s in strategies:
            assert len(s.applicable_market_regimes) > 0, f"{s.strategy_id} missing regimes"

    def test_all_strategies_have_conditions(self):
        strategies = get_all_strategy_definitions()
        for s in strategies:
            assert len(s.required_conditions) > 0, f"{s.strategy_id} missing required conditions"

    def test_all_strategies_have_invalidation_rules(self):
        strategies = get_all_strategy_definitions()
        for s in strategies:
            assert len(s.invalidation_rules) > 0, f"{s.strategy_id} missing invalidation rules"

    def test_all_strategies_have_quality_weights(self):
        strategies = get_all_strategy_definitions()
        for s in strategies:
            assert len(s.quality_weights) > 0, f"{s.strategy_id} missing quality weights"

    def test_definition_serialization(self):
        """Strategy definitions can be serialized to JSON."""
        s = TREND_CONTINUATION
        data = s.model_dump(mode="json")
        assert data["strategy_id"] == "trend_continuation"
        assert isinstance(data["required_timeframes"], list)

    def test_timeframe_role_enum(self):
        s = TREND_CONTINUATION
        for tr in s.required_timeframes:
            assert tr.role in [
                TimeframeRole.REQUIRED_CONTEXT,
                TimeframeRole.REQUIRED_SETUP,
                TimeframeRole.OPTIONAL_CONFIRMATION,
            ]


# ---------------------------------------------------------------------------
# Source Compatibility Tests
# ---------------------------------------------------------------------------

class TestSourceCompatibility:
    """Source compatibility policy tests."""

    def test_trend_continuation_policy(self):
        assert TREND_CONTINUATION.source_compatibility_policy == SourceCompatibilityPolicy.FUTURES_PROXY_ALLOWED

    def test_pullback_continuation_policy(self):
        assert PULLBACK_CONTINUATION.source_compatibility_policy == SourceCompatibilityPolicy.FUTURES_PROXY_ALLOWED

    def test_range_reversal_policy(self):
        assert RANGE_REVERSAL.source_compatibility_policy == SourceCompatibilityPolicy.FUTURES_PROXY_ALLOWED

    def test_all_strategies_have_policy(self):
        for s in ALL_STRATEGIES.values():
            assert s.source_compatibility_policy in [
                SourceCompatibilityPolicy.SPOT_ONLY,
                SourceCompatibilityPolicy.SPOT_PREFERRED,
                SourceCompatibilityPolicy.FUTURES_PROXY_ALLOWED,
            ]

    def test_spot_only_policy_passes_spot(self):
        passes, reason = check_source_compatibility(SourceCompatibilityPolicy.SPOT_ONLY, ["spot"])
        assert passes is True
        assert "SPOT" in reason

    def test_spot_only_policy_fails_futures(self):
        passes, reason = check_source_compatibility(SourceCompatibilityPolicy.SPOT_ONLY, ["futures_proxy"])
        assert passes is False

    def test_spot_preferred_policy_passes_spot(self):
        passes, reason = check_source_compatibility(SourceCompatibilityPolicy.SPOT_PREFERRED, ["spot"])
        assert passes is True

    def test_spot_preferred_policy_passes_futures(self):
        passes, reason = check_source_compatibility(SourceCompatibilityPolicy.SPOT_PREFERRED, ["futures_proxy"])
        assert passes is True

    def test_spot_preferred_policy_fails_mixed(self):
        passes, reason = check_source_compatibility(SourceCompatibilityPolicy.SPOT_PREFERRED, ["spot", "futures_proxy"])
        assert passes is False

    def test_futures_proxy_allowed_policy_passes_all(self):
        passes, reason = check_source_compatibility(SourceCompatibilityPolicy.FUTURES_PROXY_ALLOWED, ["spot", "futures_proxy"])
        assert passes is True

    def test_source_compatibility_no_sources(self):
        passes, reason = check_source_compatibility(SourceCompatibilityPolicy.SPOT_ONLY, [])
        assert passes is False
        assert "No source types" in reason


# ---------------------------------------------------------------------------
# Eligibility Gate Tests
# ---------------------------------------------------------------------------

class TestEligibilityGate:
    """Eligibility gate logic tests."""

    def test_eligible_with_all_checks_passing(self):
        strategy = TREND_CONTINUATION
        tfs = [tr.timeframe for tr in strategy.required_timeframes]
        tf_contexts = [_make_tf_context(tf, "futures_proxy") for tf in tfs]
        result = run_eligibility_gate(
            strategy=strategy,
            required_timeframes=tfs,
            timeframe_contexts=tf_contexts,
            source_types_used=["futures_proxy"],
            market_regime="trending_up",
            feature_set_status=FeatureSetStatus.READY,
            analysis_status=AnalysisStatus.AVAILABLE,
        )
        assert result.eligible is True
        assert result.blocked_by is None
        assert all(c.status.value == "passed" for c in result.checks)

    def test_not_eligible_wrong_regime(self):
        strategy = RANGE_REVERSAL
        tfs = [tr.timeframe for tr in strategy.required_timeframes]
        tf_contexts = [_make_tf_context(tf, "futures_proxy") for tf in tfs]
        result = run_eligibility_gate(
            strategy=strategy,
            required_timeframes=tfs,
            timeframe_contexts=tf_contexts,
            source_types_used=["futures_proxy"],
            market_regime="trending_up",
            feature_set_status=FeatureSetStatus.READY,
            analysis_status=AnalysisStatus.AVAILABLE,
        )
        # RANGE_REVERSAL only applies in ranging
        assert result.eligible is False
        assert result.blocked_by == "regime_compatible"

    def test_not_eligible_no_analysis(self):
        strategy = TREND_CONTINUATION
        tfs = [tr.timeframe for tr in strategy.required_timeframes]
        tf_contexts = [_make_tf_context(tf, "futures_proxy") for tf in tfs]
        result = run_eligibility_gate(
            strategy=strategy,
            required_timeframes=tfs,
            timeframe_contexts=tf_contexts,
            source_types_used=["futures_proxy"],
            market_regime="trending_up",
            feature_set_status=FeatureSetStatus.READY,
            analysis_status=None,
        )
        assert result.eligible is False
        assert result.blocked_by == "market_analysis_available"

    def test_not_eligible_insufficient_data(self):
        strategy = TREND_CONTINUATION
        tfs = [tr.timeframe for tr in strategy.required_timeframes]
        result = run_eligibility_gate(
            strategy=strategy,
            required_timeframes=tfs,
            timeframe_contexts=[],
            source_types_used=[],
            market_regime="trending_up",
            feature_set_status=FeatureSetStatus.READY,
            analysis_status=AnalysisStatus.AVAILABLE,
        )
        assert result.eligible is False

    def test_not_eligible_warming_up_features(self):
        strategy = TREND_CONTINUATION
        tfs = [tr.timeframe for tr in strategy.required_timeframes]
        tf_contexts = [_make_tf_context(tf, "futures_proxy") for tf in tfs]
        result = run_eligibility_gate(
            strategy=strategy,
            required_timeframes=tfs,
            timeframe_contexts=tf_contexts,
            source_types_used=["futures_proxy"],
            market_regime="trending_up",
            feature_set_status=FeatureSetStatus.WARMING_UP,
            analysis_status=AnalysisStatus.AVAILABLE,
        )
        assert result.eligible is False
        assert result.blocked_by == "feature_set_usable"

    def test_eligibility_checks_structure(self):
        strategy = TREND_CONTINUATION
        tfs = [tr.timeframe for tr in strategy.required_timeframes]
        tf_contexts = [_make_tf_context(tf, "futures_proxy") for tf in tfs]
        result = run_eligibility_gate(
            strategy=strategy,
            required_timeframes=tfs,
            timeframe_contexts=tf_contexts,
            source_types_used=["futures_proxy"],
            market_regime="trending_up",
            feature_set_status=FeatureSetStatus.READY,
            analysis_status=AnalysisStatus.AVAILABLE,
        )
        assert isinstance(result, EligibilityResult)
        assert len(result.checks) == 5  # 5 eligibility checks
        for check in result.checks:
            assert hasattr(check, "check_name")
            assert hasattr(check, "status")
            assert hasattr(check, "reason")

    def test_eligibility_result_serialization(self):
        strategy = TREND_CONTINUATION
        tfs = [tr.timeframe for tr in strategy.required_timeframes]
        tf_contexts = [_make_tf_context(tf, "futures_proxy") for tf in tfs]
        result = run_eligibility_gate(
            strategy=strategy,
            required_timeframes=tfs,
            timeframe_contexts=tf_contexts,
            source_types_used=["futures_proxy"],
            market_regime="trending_up",
            feature_set_status=FeatureSetStatus.READY,
            analysis_status=AnalysisStatus.AVAILABLE,
        )
        data = result.model_dump(mode="json")
        assert "eligible" in data
        assert "checks" in data

    def test_not_eligible_unknown_regime(self):
        """When regime is None, regime check fails."""
        strategy = TREND_CONTINUATION
        tfs = [tr.timeframe for tr in strategy.required_timeframes]
        tf_contexts = [_make_tf_context(tf, "futures_proxy") for tf in tfs]
        result = run_eligibility_gate(
            strategy=strategy,
            required_timeframes=tfs,
            timeframe_contexts=tf_contexts,
            source_types_used=["futures_proxy"],
            market_regime=None,
            feature_set_status=FeatureSetStatus.READY,
            analysis_status=AnalysisStatus.AVAILABLE,
        )
        assert result.eligible is False


# ---------------------------------------------------------------------------
# Condition Engine Tests
# ---------------------------------------------------------------------------

class TestConditionEngine:
    """Condition evaluator logic tests."""

    def test_evaluate_conditions_returns_list(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        features = _make_feature_result()
        result = evaluate_conditions(
            strategy=strategy,
            analysis=analysis,
            features=features,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        assert isinstance(result, list)
        assert len(result) > 0

    def test_condition_result_structure(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        features = _make_feature_result()
        results = evaluate_conditions(
            strategy=strategy,
            analysis=analysis,
            features=features,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        for r in results:
            assert hasattr(r, "condition_id")
            assert hasattr(r, "status")
            assert hasattr(r, "criticality")
            assert hasattr(r, "evidence")
            assert r.status in [ConditionStatus.PASSED, ConditionStatus.FAILED, ConditionStatus.UNAVAILABLE]

    def test_bullish_trend_has_passed_conditions(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        features = _make_feature_result()
        results = evaluate_conditions(
            strategy=strategy,
            analysis=analysis,
            features=features,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        passed = [r for r in results if r.status == ConditionStatus.PASSED]
        assert len(passed) > 0

    def test_condition_criticality_preserved(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        features = _make_feature_result()
        results = evaluate_conditions(
            strategy=strategy,
            analysis=analysis,
            features=features,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        for r in results:
            assert r.criticality in [
                ConditionCriticality.CRITICAL,
                ConditionCriticality.REQUIRED,
                ConditionCriticality.OPTIONAL,
            ]

    def test_condition_serialization(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        features = _make_feature_result()
        results = evaluate_conditions(
            strategy=strategy,
            analysis=analysis,
            features=features,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        for r in results:
            data = r.model_dump(mode="json")
            assert "condition_id" in data
            assert "status" in data

    def test_no_analysis_returns_unavailable(self):
        strategy = TREND_CONTINUATION
        results = evaluate_conditions(
            strategy=strategy,
            analysis=None,
            features=None,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        # Some conditions require analysis/features and return UNAVAILABLE,
        # but volume_supports always passes since it doesn't need analysis
        unavailable = [r for r in results if r.status == ConditionStatus.UNAVAILABLE]
        assert len(unavailable) > 0

    def test_range_reversal_conditions_on_ranging(self):
        strategy = RANGE_REVERSAL
        analysis = _ranging_analysis()
        features = _make_feature_result()
        results = evaluate_conditions(
            strategy=strategy,
            analysis=analysis,
            features=features,
            direction=StrategyDirection.BULLISH,
            regime_state="ranging",
        )
        passed = [r for r in results if r.status == ConditionStatus.PASSED]
        assert len(passed) > 0


# ---------------------------------------------------------------------------
# Invalidation Evaluator Tests
# ---------------------------------------------------------------------------

class TestInvalidationEvaluator:
    """Invalidation evaluator logic tests."""

    def test_returns_list(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        results = evaluate_invalidation_rules(
            strategy=strategy,
            analysis=analysis,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        assert isinstance(results, list)
        assert len(results) > 0

    def test_result_structure(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        results = evaluate_invalidation_rules(
            strategy=strategy,
            analysis=analysis,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        for r in results:
            assert hasattr(r, "rule_id")
            assert hasattr(r, "triggered")
            assert hasattr(r, "reason")
            assert hasattr(r, "evidence")

    def test_no_invalidation_on_bullish_trend(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        results = evaluate_invalidation_rules(
            strategy=strategy,
            analysis=analysis,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        # With bullish analysis and bullish direction, no invalidation should trigger
        triggered = [r for r in results if r.triggered]
        assert len(triggered) == 0

    def test_invalidation_serialization(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        results = evaluate_invalidation_rules(
            strategy=strategy,
            analysis=analysis,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        for r in results:
            data = r.model_dump(mode="json")
            assert "rule_id" in data
            assert "triggered" in data

    def test_no_analysis_returns_not_triggered(self):
        strategy = TREND_CONTINUATION
        results = evaluate_invalidation_rules(
            strategy=strategy,
            analysis=None,
            direction=StrategyDirection.BULLISH,
            regime_state="trending_up",
        )
        for r in results:
            assert r.triggered is False


# ---------------------------------------------------------------------------
# Quality Score Tests
# ---------------------------------------------------------------------------

class TestQualityScore:
    """Quality scoring logic tests."""

    def test_quality_score_returns_score(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        features = _make_feature_result()
        conditions = evaluate_conditions(
            strategy=strategy, analysis=analysis, features=features,
            direction=StrategyDirection.BULLISH, regime_state="trending_up",
        )
        score = calculate_quality_score(
            strategy=strategy,
            condition_results=conditions,
            direction=StrategyDirection.BULLISH,
        )
        assert isinstance(score, QualityScore)
        assert score.score >= 0
        assert score.max_score > 0
        assert 0.0 <= score.normalized_score <= 1.0

    def test_quality_score_has_breakdown(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        features = _make_feature_result()
        conditions = evaluate_conditions(
            strategy=strategy, analysis=analysis, features=features,
            direction=StrategyDirection.BULLISH, regime_state="trending_up",
        )
        score = calculate_quality_score(
            strategy=strategy,
            condition_results=conditions,
            direction=StrategyDirection.BULLISH,
        )
        assert len(score.breakdown) > 0
        for item in score.breakdown:
            assert hasattr(item, "category")
            assert hasattr(item, "points_awarded")
            assert hasattr(item, "max_points")

    def test_quality_score_serialization(self):
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        features = _make_feature_result()
        conditions = evaluate_conditions(
            strategy=strategy, analysis=analysis, features=features,
            direction=StrategyDirection.BULLISH, regime_state="trending_up",
        )
        score = calculate_quality_score(
            strategy=strategy,
            condition_results=conditions,
            direction=StrategyDirection.BULLISH,
        )
        data = score.model_dump(mode="json")
        assert "score" in data
        assert "max_score" in data
        assert "normalized_score" in data
        assert "breakdown" in data

    def test_quality_score_increases_with_passed_conditions(self):
        """More passed conditions should yield a higher score."""
        strategy = TREND_CONTINUATION
        analysis = _rising_analysis()
        features = _make_feature_result()
        conditions_bullish = evaluate_conditions(
            strategy=strategy, analysis=analysis, features=features,
            direction=StrategyDirection.BULLISH, regime_state="trending_up",
        )
        score_bullish = calculate_quality_score(
            strategy=strategy,
            condition_results=conditions_bullish,
            direction=StrategyDirection.BULLISH,
        )
        conditions_neutral = evaluate_conditions(
            strategy=strategy, analysis=analysis, features=features,
            direction=StrategyDirection.NEUTRAL, regime_state="ranging",
        )
        score_neutral = calculate_quality_score(
            strategy=strategy,
            condition_results=conditions_neutral,
            direction=StrategyDirection.NEUTRAL,
        )
        # More conditions pass for bullish+trending than neutral+ranging
        assert score_bullish.score >= score_neutral.score


# ---------------------------------------------------------------------------
# Strategy Evaluation Result Model Tests
# ---------------------------------------------------------------------------

class TestStrategyEvaluationResult:
    """StrategyEvaluationResult model structure tests."""

    def test_result_structure(self):
        from app.modules.strategies.models import StrategyEvaluationResult
        result = StrategyEvaluationResult(
            strategy_id="test",
            strategy_version="1.0",
            strategy_name="Test",
            instrument="XAU/USD",
            status=StrategyEvaluationStatus.NOT_QUALIFIED,
            direction=StrategyDirection.NONE,
            reason="test reason",
        )
        assert result.strategy_id == "test"
        assert result.status == StrategyEvaluationStatus.NOT_QUALIFIED
        assert result.direction == StrategyDirection.NONE
        assert isinstance(result.evaluation_id, str)
        assert len(result.evaluation_id) > 0

    def test_result_serialization(self):
        from app.modules.strategies.models import StrategyEvaluationResult
        result = StrategyEvaluationResult(
            strategy_id="test",
            strategy_version="1.0",
            strategy_name="Test",
            instrument="XAU/USD",
            status=StrategyEvaluationStatus.QUALIFIED,
            direction=StrategyDirection.BULLISH,
            reason="test",
        )
        data = result.model_dump(mode="json")
        assert data["strategy_id"] == "test"
        assert data["status"] == "qualified"
        assert data["direction"] == "bullish"

    def test_result_has_timestamp(self):
        from app.modules.strategies.models import StrategyEvaluationResult
        result = StrategyEvaluationResult(
            strategy_id="test",
            strategy_version="1.0",
            strategy_name="Test",
            instrument="XAU/USD",
            status=StrategyEvaluationStatus.UNAVAILABLE,
        )
        assert result.evaluation_timestamp is not None


# ---------------------------------------------------------------------------
# Direction Determination Tests
# ---------------------------------------------------------------------------

class TestDirectionDetermination:
    """Test strategy direction inference from analysis data."""

    def test_direction_from_analysis_bullish(self):
        analysis = _rising_analysis()
        from app.modules.strategies.service import _determine_direction
        direction = _determine_direction(analysis, None)
        assert direction == StrategyDirection.BULLISH

    def test_direction_from_analysis_bearish(self):
        analysis = _bearish_analysis()
        from app.modules.strategies.service import _determine_direction
        direction = _determine_direction(analysis, None)
        assert direction == StrategyDirection.BEARISH

    def test_direction_from_analysis_ranging(self):
        analysis = _ranging_analysis()
        from app.modules.strategies.service import _determine_direction
        direction = _determine_direction(analysis, None)
        assert direction == StrategyDirection.NEUTRAL

    def test_direction_from_analysis_none(self):
        from app.modules.strategies.service import _determine_direction
        direction = _determine_direction(None, None)
        assert direction == StrategyDirection.NONE

    def test_direction_from_features_bullish(self):
        features = _make_feature_result()
        from app.modules.strategies.service import _determine_direction
        direction = _determine_direction(None, features)
        assert direction == StrategyDirection.BULLISH


# ---------------------------------------------------------------------------
# API Endpoint Tests
# ---------------------------------------------------------------------------

class TestStrategiesAPI:
    """Strategy API endpoint tests using TestClient."""

    def test_health_returns_200(self, client):
        response = client.get("/api/v1/strategies/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["module"] == "strategies"

    def test_capabilities_returns_200(self, client):
        response = client.get("/api/v1/strategies/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert data["module"] == "strategies"
        assert "strategies" in data
        assert len(data["strategies"]) == 3

    def test_list_returns_200(self, client):
        response = client.get("/api/v1/strategies")
        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data
        assert data["count"] == 3

    def test_list_has_all_strategies(self, client):
        response = client.get("/api/v1/strategies")
        data = response.json()
        ids = [s["strategy_id"] for s in data["strategies"]]
        assert "trend_continuation" in ids
        assert "pullback_continuation" in ids
        assert "range_reversal" in ids

    def test_evaluate_unknown_strategy_returns_unavailable(self, client):
        response = client.get("/api/v1/strategies/evaluate?strategy_id=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unavailable"

    def test_evaluate_invalid_timeframes_returns_error(self, client):
        response = client.get(
            "/api/v1/strategies/evaluate?strategy_id=trend_continuation&timeframes="
        )
        assert response.status_code in [400, 422]

    def test_evaluate_all_returns_200(self, client):
        response = client.get("/api/v1/strategies/evaluate-all")
        assert response.status_code == 200
        data = response.json()
        assert "evaluations" in data
        assert data["count"] == 3

    def test_health_structure(self, client):
        response = client.get("/api/v1/strategies/health")
        data = response.json()
        assert "status" in data
        assert "module" in data
        assert "configuration" in data
        assert "strategies_registered" in data
        assert "strategies_enabled" in data

    def test_capabilities_structure(self, client):
        response = client.get("/api/v1/strategies/capabilities")
        data = response.json()
        assert "module" in data
        assert "status" in data
        assert "strategies" in data
        for s in data["strategies"]:
            assert "strategy_id" in s
            assert "enabled" in s
            assert "source_compatibility_policy" in s
