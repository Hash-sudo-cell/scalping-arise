"""
Scalping Arise — Trade Planning & Risk Engine Tests

Comprehensive test suite for Phase 7: models, config, instrument specs,
eligibility, entry, SL, TP, position sizing, risk guardrails, R:R,
freshness, price validation, cost validation, and service orchestrator.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

from app.modules.trade_planning.models import (
    CostEstimate,
    EligibilityCheck,
    EligibilityResult,
    EntryPlan,
    EntryState,
    EntryType,
    FreshnessCheck,
    InstrumentSpecification,
    PlanRejectionReason,
    PlanSide,
    PlanState,
    PlanTransition,
    PositionSizeResult,
    PriceTickCheck,
    RiskCalculation,
    RiskParameters,
    StopLossPlan,
    TakeProfitPlan,
    TakeProfitTarget,
    TPTarget,
    TradePlan,
    VolatilityAdjustment,
    side_from_decision,
    rr_ratio,
)


# ===========================================================================
# Model Tests
# ===========================================================================

class TestPlanState:
    def test_plan_state_values(self):
        assert PlanState.NO_PLAN == "no_plan"
        assert PlanState.DRAFT == "draft"
        assert PlanState.CALCULATED == "calculated"
        assert PlanState.VALIDATED == "validated"
        assert PlanState.APPROVED == "approved"
        assert PlanState.REJECTED == "rejected"
        assert PlanState.EXPIRED == "expired"
        assert PlanState.INVALIDATED == "invalidated"

    def test_plan_state_is_str_enum(self):
        assert isinstance(PlanState.APPROVED, str)
        assert PlanState.APPROVED.value == "approved"


class TestPlanSide:
    def test_plan_side_values(self):
        assert PlanSide.LONG == "long"
        assert PlanSide.SHORT == "short"


class TestSideFromDecision:
    def test_buy_maps_to_long(self):
        assert side_from_decision("buy") == PlanSide.LONG

    def test_sell_maps_to_short(self):
        assert side_from_decision("sell") == PlanSide.SHORT

    def test_no_trade_maps_to_none(self):
        assert side_from_decision("no_trade") is None

    def test_unknown_maps_to_none(self):
        assert side_from_decision("unknown") is None


class TestRrRatio:
    def test_basic_ratio(self):
        assert rr_ratio(30.0, 10.0) == 3.0

    def test_zero_risk(self):
        assert rr_ratio(30.0, 0.0) == 0.0

    def test_negative_risk(self):
        assert rr_ratio(30.0, -5.0) == 0.0

    def test_equal_reward_risk(self):
        assert rr_ratio(15.0, 15.0) == 1.0

    def test_fractional(self):
        result = rr_ratio(10.0, 7.0)
        assert abs(result - 1.4286) < 0.01


class TestInstrumentSpecification:
    def test_round_price(self):
        spec = InstrumentSpecification(
            instrument="XAU/USD", tick_size=0.01, contract_size=100.0,
            lot_step=0.01, min_lot=0.01, max_lot=100.0, price_precision=2,
            pip_value_per_lot=1.0, typical_spread_pips=3.0, margin_rate=0.05,
        )
        assert spec.round_price(2650.456) == 2650.46
        assert spec.round_price(2650.451) == 2650.45

    def test_round_lots(self):
        spec = InstrumentSpecification(
            instrument="XAU/USD", tick_size=0.01, contract_size=100.0,
            lot_step=0.01, min_lot=0.01, max_lot=100.0, price_precision=2,
            pip_value_per_lot=1.0, typical_spread_pips=3.0, margin_rate=0.05,
        )
        assert spec.round_lots(0.123) == 0.12
        assert spec.round_lots(0.001) == 0.01  # clamped to min
        assert spec.round_lots(200.0) == 100.0  # clamped to max

    def test_ticks_between(self):
        spec = InstrumentSpecification(
            instrument="XAU/USD", tick_size=0.01, contract_size=100.0,
            lot_step=0.01, min_lot=0.01, max_lot=100.0, price_precision=2,
            pip_value_per_lot=1.0, typical_spread_pips=3.0, margin_rate=0.05,
        )
        assert spec.ticks_between(2650.00, 2650.50) == 50.0

    def test_pip_distance(self):
        spec = InstrumentSpecification(
            instrument="XAU/USD", tick_size=0.01, contract_size=100.0,
            lot_step=0.01, min_lot=0.01, max_lot=100.0, price_precision=2,
            pip_value_per_lot=1.0, typical_spread_pips=3.0, margin_rate=0.05,
        )
        assert spec.pip_distance(2650.00, 2650.50) == 5.0

    def test_is_tick_aligned(self):
        spec = InstrumentSpecification(
            instrument="XAU/USD", tick_size=0.01, contract_size=100.0,
            lot_step=0.01, min_lot=0.01, max_lot=100.0, price_precision=2,
            pip_value_per_lot=1.0, typical_spread_pips=3.0, margin_rate=0.05,
        )
        assert spec.is_tick_aligned(2650.00) is True
        assert spec.is_tick_aligned(2650.005) is False


class TestTradePlan:
    def test_default_state(self):
        plan = TradePlan(instrument="XAU/USD", side=PlanSide.LONG)
        assert plan.state == PlanState.NO_PLAN
        assert plan.is_actionable is False
        assert plan.is_terminal is False

    def test_actionable_when_approved(self):
        plan = TradePlan(instrument="XAU/USD", side=PlanSide.LONG, state=PlanState.APPROVED)
        assert plan.is_actionable is True

    def test_actionable_when_validated(self):
        plan = TradePlan(instrument="XAU/USD", side=PlanSide.LONG, state=PlanState.VALIDATED)
        assert plan.is_actionable is True

    def test_terminal_when_rejected(self):
        plan = TradePlan(instrument="XAU/USD", side=PlanSide.LONG, state=PlanState.REJECTED)
        assert plan.is_terminal is True

    def test_terminal_when_expired(self):
        plan = TradePlan(instrument="XAU/USD", side=PlanSide.LONG, state=PlanState.EXPIRED)
        assert plan.is_terminal is True

    def test_unique_plan_ids(self):
        p1 = TradePlan(instrument="XAU/USD", side=PlanSide.LONG)
        p2 = TradePlan(instrument="XAU/USD", side=PlanSide.LONG)
        assert p1.plan_id != p2.plan_id

    def test_age_seconds(self):
        plan = TradePlan(instrument="XAU/USD", side=PlanSide.LONG)
        plan.created_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        assert plan.age_seconds >= 9.0

    def test_remaining_ttl(self):
        plan = TradePlan(instrument="XAU/USD", side=PlanSide.LONG, ttl_seconds=300)
        plan.created_at = datetime.now(timezone.utc) - timedelta(seconds=100)
        assert plan.remaining_ttl >= 190.0
        assert plan.remaining_ttl <= 210.0


class TestPlanTransition:
    def test_transition_creation(self):
        t = PlanTransition(
            from_state=PlanState.NO_PLAN,
            to_state=PlanState.DRAFT,
            reason="Starting",
        )
        assert t.from_state == PlanState.NO_PLAN
        assert t.to_state == PlanState.DRAFT
        assert t.reason == "Starting"


# ===========================================================================
# Config Tests
# ===========================================================================

from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings


class TestTradePlanningSettings:
    def test_defaults(self):
        s = TradePlanningSettings()
        assert s.trade_planning_enabled is True
        assert s.min_signal_confidence_0_100 == 55
        assert s.min_signal_quality_0_100 == 60
        assert s.risk_per_trade_pct == 1.0
        assert s.max_daily_loss_pct == 3.0
        assert s.max_drawdown_pct == 10.0
        assert s.min_risk_reward_ratio == 1.0
        assert s.plan_ttl_seconds == 300

    def test_is_enabled(self):
        s = TradePlanningSettings()
        assert s.is_enabled is True

    def test_disabled(self):
        s = TradePlanningSettings(trade_planning_enabled=False)
        assert s.is_enabled is False

    def test_get_settings(self):
        s = get_trade_planning_settings()
        assert isinstance(s, TradePlanningSettings)


# ===========================================================================
# Instrument Specs Tests
# ===========================================================================

from app.modules.trade_planning.instrument_specs import (
    get_spec,
    get_spec_or_raise,
    is_instrument_supported,
    list_instruments,
    register_spec,
)


class TestInstrumentSpecs:
    def test_xau_usd_spec(self):
        spec = get_spec("XAU/USD")
        assert spec is not None
        assert spec.tick_size == 0.01
        assert spec.contract_size == 100.0
        assert spec.min_lot == 0.01
        assert spec.max_lot == 100.0

    def test_btc_usd_spec(self):
        spec = get_spec("BTC/USD")
        assert spec is not None
        assert spec.contract_size == 1.0

    def test_unknown_instrument(self):
        assert get_spec("DOGE/USD") is None

    def test_get_spec_or_raise(self):
        spec = get_spec_or_raise("XAU/USD")
        assert spec.instrument == "XAU/USD"

    def test_get_spec_or_raise_unknown(self):
        with pytest.raises(ValueError, match="No specification"):
            get_spec_or_raise("DOGE/USD")

    def test_is_instrument_supported(self):
        assert is_instrument_supported("XAU/USD") is True
        assert is_instrument_supported("DOGE/USD") is False

    def test_list_instruments(self):
        instruments = list_instruments()
        assert "XAU/USD" in instruments
        assert "BTC/USD" in instruments
        assert len(instruments) >= 7

    def test_register_spec(self):
        custom = InstrumentSpecification(
            instrument="DOGE/USD",
            tick_size=0.00001,
            contract_size=1.0,
            lot_step=1.0,
            min_lot=1.0,
            max_lot=10000.0,
            price_precision=5,
            pip_value_per_lot=0.00001,
            typical_spread_pips=10.0,
            margin_rate=0.10,
        )
        register_spec(custom)
        assert is_instrument_supported("DOGE/USD") is True
        assert get_spec("DOGE/USD") is custom


# ===========================================================================
# Eligibility Tests
# ===========================================================================

from app.modules.trade_planning.eligibility import check_signal_eligibility
from app.modules.signal_engine.models import (
    ConfidenceScore,
    DecisionType,
    SignalDirection,
    SignalQuality,
    SignalRecord,
    SignalState,
)


def _make_signal(
    *,
    decision: DecisionType = DecisionType.BUY,
    state: SignalState = SignalState.ACTIVE,
    confidence: int = 75,
    quality: int = 70,
    instrument: str = "XAU/USD",
) -> SignalRecord:
    """Create a test signal record."""
    cs = ConfidenceScore(
        overall=confidence / 100.0,
        strategy_alignment=0.8,
        mtf_confirmation=0.7,
        evidence_strength=0.6,
        regime_consistency=0.9,
    )
    cs.confidence_0_100 = confidence
    sq = SignalQuality(
        score=quality,
        condition_pass_rate=0.8,
        evidence_depth=3,
        strategy_alignment=0.9,
    )
    return SignalRecord(
        instrument=instrument,
        decision=decision,
        state=state,
        direction=SignalDirection.LONG if decision == DecisionType.BUY else SignalDirection.SHORT,
        confidence=cs,
        quality=sq,
    )


class TestEligibility:
    def test_eligible_signal(self):
        signal = _make_signal()
        result = check_signal_eligibility(signal)
        assert result.eligible is True
        assert result.blocked_by is None

    def test_no_trade_not_eligible(self):
        signal = _make_signal(decision=DecisionType.NO_TRADE)
        result = check_signal_eligibility(signal)
        assert result.eligible is False
        assert result.blocked_by == "signal_decision"

    def test_low_confidence(self):
        signal = _make_signal(confidence=30)
        result = check_signal_eligibility(signal)
        assert result.eligible is False
        assert result.blocked_by == "signal_confidence"

    def test_low_quality(self):
        signal = _make_signal(quality=40)
        result = check_signal_eligibility(signal)
        assert result.eligible is False
        assert result.blocked_by == "signal_quality"

    def test_unsupported_instrument(self):
        signal = _make_signal(instrument="SHIBA/USD")
        result = check_signal_eligibility(signal)
        assert result.eligible is False
        assert result.blocked_by == "instrument_supported"

    def test_inactive_signal(self):
        from app.modules.trade_planning.config import TradePlanningSettings
        settings = TradePlanningSettings(require_signal_active=True)
        signal = _make_signal(state=SignalState.CONFIRMED)
        result = check_signal_eligibility(signal, settings=settings)
        assert result.eligible is False
        assert result.blocked_by == "signal_state"

    def test_no_confidence_score(self):
        signal = _make_signal()
        signal.confidence = None
        result = check_signal_eligibility(signal)
        assert result.eligible is False

    def test_no_quality_score(self):
        signal = _make_signal()
        signal.quality = None
        result = check_signal_eligibility(signal)
        assert result.eligible is False


# ===========================================================================
# Entry Tests
# ===========================================================================

from app.modules.trade_planning.entry import plan_entry


class TestEntryPlanning:
    def test_entry_ready_long(self):
        result = plan_entry(
            side=PlanSide.LONG,
            current_price=2650.00,
            bid=2649.90,
            ask=2650.10,
            spread_pips=2.0,
            price_check=PriceTickCheck(is_valid=True, current_price=2650.00),
            instrument="XAU/USD",
        )
        assert result.state == EntryState.ENTRY_READY
        assert result.entry_price is not None
        assert result.entry_price > 0

    def test_entry_ready_short(self):
        result = plan_entry(
            side=PlanSide.SHORT,
            current_price=2650.00,
            bid=2649.90,
            ask=2650.10,
            spread_pips=2.0,
            price_check=PriceTickCheck(is_valid=True, current_price=2650.00),
            instrument="XAU/USD",
        )
        assert result.state == EntryState.ENTRY_READY

    def test_price_invalid(self):
        result = plan_entry(
            side=PlanSide.LONG,
            current_price=2650.00,
            price_check=PriceTickCheck(is_valid=False, current_price=2650.00, reason="Stale"),
            instrument="XAU/USD",
        )
        assert result.state == EntryState.ENTRY_UNAVAILABLE

    def test_spread_too_wide(self):
        result = plan_entry(
            side=PlanSide.LONG,
            current_price=2650.00,
            spread_pips=100.0,
            price_check=PriceTickCheck(is_valid=True, current_price=2650.00),
            instrument="XAU/USD",
        )
        assert result.state == EntryState.ENTRY_UNAVAILABLE

    def test_spread_wide_wait(self):
        result = plan_entry(
            side=PlanSide.LONG,
            current_price=2650.00,
            spread_pips=8.0,  # > 5.0 max but < 10.0 (2x max)
            price_check=PriceTickCheck(is_valid=True, current_price=2650.00),
            instrument="XAU/USD",
        )
        assert result.state == EntryState.WAIT_FOR_ENTRY

    def test_zero_price(self):
        result = plan_entry(
            side=PlanSide.LONG,
            current_price=0.0,
            price_check=PriceTickCheck(is_valid=True, current_price=0.0),
            instrument="XAU/USD",
        )
        assert result.state == EntryState.ENTRY_UNAVAILABLE


# ===========================================================================
# Stop-Loss Tests
# ===========================================================================

from app.modules.trade_planning.stop_loss import plan_stop_loss


class TestStopLoss:
    def test_invalidation_sl_long(self):
        result = plan_stop_loss(
            side=PlanSide.LONG,
            entry_price=2650.00,
            invalidation_level=2640.00,
            instrument="XAU/USD",
        )
        assert result.sl_type.value == "invalidation"
        assert result.sl_price < 2650.00
        assert result.sl_distance_pips > 0
        assert result.risk_per_lot > 0

    def test_invalidation_sl_short(self):
        result = plan_stop_loss(
            side=PlanSide.SHORT,
            entry_price=2650.00,
            invalidation_level=2660.00,
            instrument="XAU/USD",
        )
        assert result.sl_type.value == "invalidation"
        assert result.sl_price > 2650.00

    def test_atr_sl_long(self):
        result = plan_stop_loss(
            side=PlanSide.LONG,
            entry_price=2650.00,
            atr_value=10.0,
            instrument="XAU/USD",
        )
        assert result.sl_type.value == "atr"
        assert result.sl_price < 2650.00
        assert result.atr_multiple == 1.5  # default

    def test_atr_sl_short(self):
        result = plan_stop_loss(
            side=PlanSide.SHORT,
            entry_price=2650.00,
            atr_value=10.0,
            instrument="XAU/USD",
        )
        assert result.sl_price > 2650.00

    def test_structure_sl(self):
        result = plan_stop_loss(
            side=PlanSide.LONG,
            entry_price=2650.00,
            structure_level=2640.00,
            instrument="XAU/USD",
        )
        assert result.sl_type.value == "structure"

    def test_fallback_sl(self):
        result = plan_stop_loss(
            side=PlanSide.LONG,
            entry_price=2650.00,
            instrument="XAU/USD",
        )
        assert result.sl_type.value == "fixed"
        assert result.sl_distance_pips >= 5.0  # min distance

    def test_volatility_expand(self):
        result = plan_stop_loss(
            side=PlanSide.LONG,
            entry_price=2650.00,
            atr_value=10.0,
            volatility_adjustment=VolatilityAdjustment.EXPAND,
            instrument="XAU/USD",
        )
        assert result.atr_multiple == 2.0  # expanded

    def test_volatility_contract(self):
        result = plan_stop_loss(
            side=PlanSide.LONG,
            entry_price=2650.00,
            atr_value=10.0,
            volatility_adjustment=VolatilityAdjustment.CONTRACT,
            instrument="XAU/USD",
        )
        assert result.atr_multiple == 1.0  # contracted

    def test_min_distance_enforced(self):
        result = plan_stop_loss(
            side=PlanSide.LONG,
            entry_price=2650.00,
            invalidation_level=2649.99,  # Very close
            instrument="XAU/USD",
        )
        assert result.sl_distance_pips >= 5.0


# ===========================================================================
# Take-Profit Tests
# ===========================================================================

from app.modules.trade_planning.take_profit import plan_take_profit


class TestTakeProfit:
    def test_tp_long(self):
        result = plan_take_profit(
            side=PlanSide.LONG,
            entry_price=2650.00,
            sl_price=2640.00,
            sl_distance_price=10.0,
            instrument="XAU/USD",
        )
        assert len(result.targets) == 2
        tp1 = result.targets[0]
        tp2 = result.targets[1]
        assert tp1.target == TPTarget.TP1
        assert tp2.target == TPTarget.TP2
        assert tp1.tp_price > 2650.00
        assert tp2.tp_price > tp1.tp_price
        assert tp1.risk_reward_ratio >= 1.5
        assert tp2.risk_reward_ratio >= 2.5

    def test_tp_short(self):
        result = plan_take_profit(
            side=PlanSide.SHORT,
            entry_price=2650.00,
            sl_price=2660.00,
            sl_distance_price=10.0,
            instrument="XAU/USD",
        )
        tp1 = result.targets[0]
        assert tp1.tp_price < 2650.00

    def test_partial_close_pct(self):
        result = plan_take_profit(
            side=PlanSide.LONG,
            entry_price=2650.00,
            sl_price=2640.00,
            sl_distance_price=10.0,
            instrument="XAU/USD",
        )
        tp1 = result.targets[0]
        assert tp1.partial_close_pct == 0.5  # default

    def test_tp2_no_partial_close(self):
        result = plan_take_profit(
            side=PlanSide.LONG,
            entry_price=2650.00,
            sl_price=2640.00,
            sl_distance_price=10.0,
            instrument="XAU/USD",
        )
        tp2 = result.targets[1]
        assert tp2.partial_close_pct is None

    def test_structure_targets(self):
        result = plan_take_profit(
            side=PlanSide.LONG,
            entry_price=2650.00,
            sl_price=2640.00,
            sl_distance_price=10.0,
            structure_targets=[2655.00, 2660.00, 2670.00],
            instrument="XAU/USD",
        )
        assert len(result.targets) == 2


# ===========================================================================
# Position Sizing Tests
# ===========================================================================

from app.modules.trade_planning.position_sizing import calculate_position_size, calculate_risk


class TestPositionSizing:
    def test_basic_sizing(self):
        result = calculate_position_size(
            account_balance=10000.0,
            risk_per_trade_pct=1.0,
            sl_distance_price=10.0,
            instrument="XAU/USD",
        )
        assert result.lots > 0
        assert result.risk_amount > 0
        assert result.risk_amount <= 100.0  # 1% of 10000

    def test_lots_rounded_to_step(self):
        result = calculate_position_size(
            account_balance=10000.0,
            risk_per_trade_pct=1.0,
            sl_distance_price=10.0,
            instrument="XAU/USD",
        )
        # lot_step is 0.01
        assert result.lots == round(result.lots, 2)

    def test_lots_clamped_to_min(self):
        result = calculate_position_size(
            account_balance=100.0,  # very small
            risk_per_trade_pct=1.0,
            sl_distance_price=1000.0,  # very wide SL
            instrument="XAU/USD",
        )
        assert result.lots >= 0.01  # min_lot

    def test_zero_sl_distance(self):
        result = calculate_position_size(
            account_balance=10000.0,
            risk_per_trade_pct=1.0,
            sl_distance_price=0.0,
            instrument="XAU/USD",
        )
        # When sl_distance is 0, raw_lots is 0 but min_lot clamp kicks in
        assert result.lots >= 0.0

    def test_risk_calculation(self):
        result = calculate_risk(
            account_balance=10000.0,
            risk_per_trade_pct=1.0,
            sl_distance_price=10.0,
            instrument="XAU/USD",
        )
        assert result.position_size.lots > 0
        assert result.within_risk_limits is True
        assert result.within_drawdown_limit is True
        assert result.within_daily_loss_limit is True

    def test_daily_loss_limit(self):
        result = calculate_risk(
            account_balance=10000.0,
            risk_per_trade_pct=1.0,
            sl_distance_price=10.0,
            instrument="XAU/USD",
            current_daily_loss=280.0,  # 2.8% of 10000
        )
        # 1% risk = 100, remaining daily = 300 - 280 = 20
        assert result.within_daily_loss_limit is False

    def test_max_positions(self):
        result = calculate_risk(
            account_balance=10000.0,
            risk_per_trade_pct=1.0,
            sl_distance_price=10.0,
            instrument="XAU/USD",
            current_open_positions=3,  # max is 3
        )
        assert result.within_risk_limits is False


# ===========================================================================
# Risk Guardrails Tests
# ===========================================================================

from app.modules.trade_planning.risk_guardrails import validate_risk_guardrails


class TestRiskGuardrails:
    def _make_risk(self, **kwargs) -> RiskCalculation:
        defaults = dict(
            position_size=PositionSizeResult(
                lots=0.1, risk_amount=100.0, risk_pct_actual=1.0,
                margin_required=500.0, margin_pct=5.0,
                exposure=1000.0, exposure_pct=10.0,
            ),
            risk_parameters=RiskParameters(
                account_balance=10000.0, risk_per_trade_pct=1.0,
                max_positions=3, current_open_positions=0,
            ),
            within_risk_limits=True,
            within_drawdown_limit=True,
            within_daily_loss_limit=True,
            daily_loss_remaining=200.0,
            max_drawdown_remaining=800.0,
        )
        defaults.update(kwargs)
        return RiskCalculation(**defaults)

    def test_pass(self):
        risk = self._make_risk()
        passed, rejections = validate_risk_guardrails(risk)
        assert passed is True
        assert len(rejections) == 0

    def test_daily_loss_exceeded(self):
        risk = self._make_risk(within_daily_loss_limit=False)
        passed, rejections = validate_risk_guardrails(risk)
        assert passed is False
        assert any("Daily loss" in r for r in rejections)

    def test_drawdown_exceeded(self):
        risk = self._make_risk(within_drawdown_limit=False)
        passed, rejections = validate_risk_guardrails(risk)
        assert passed is False
        assert any("Drawdown" in r for r in rejections)

    def test_risk_exceeded(self):
        risk = self._make_risk(within_risk_limits=False)
        passed, rejections = validate_risk_guardrails(risk)
        assert passed is False


# ===========================================================================
# Risk-Reward Tests
# ===========================================================================

from app.modules.trade_planning.risk_reward import validate_risk_reward


class TestRiskReward:
    def test_valid_rr(self):
        tp = TakeProfitPlan(targets=[
            TakeProfitTarget(target=TPTarget.TP1, tp_price=2665.0, tp_distance_pips=15.0,
                             tp_distance_price=15.0, reward_per_lot=1500.0, risk_reward_ratio=1.5),
        ])
        valid, reason = validate_risk_reward(tp, sl_distance_price=10.0)
        assert valid is True

    def test_low_rr(self):
        tp = TakeProfitPlan(targets=[
            TakeProfitTarget(target=TPTarget.TP1, tp_price=2655.0, tp_distance_pips=5.0,
                             tp_distance_price=5.0, reward_per_lot=500.0, risk_reward_ratio=0.5),
        ])
        valid, reason = validate_risk_reward(tp, sl_distance_price=10.0)
        assert valid is False
        assert "below minimum" in reason

    def test_no_targets(self):
        tp = TakeProfitPlan(targets=[])
        valid, reason = validate_risk_reward(tp, sl_distance_price=10.0)
        assert valid is False
        assert "No take-profit" in reason

    def test_zero_sl_distance(self):
        tp = TakeProfitPlan(targets=[
            TakeProfitTarget(target=TPTarget.TP1, tp_price=2665.0, tp_distance_pips=15.0,
                             tp_distance_price=15.0, reward_per_lot=1500.0, risk_reward_ratio=1.5),
        ])
        valid, reason = validate_risk_reward(tp, sl_distance_price=0.0)
        assert valid is False


# ===========================================================================
# Freshness Tests
# ===========================================================================

from app.modules.trade_planning.freshness import check_data_freshness


class TestFreshness:
    def test_fresh_data(self):
        ts = datetime.now(timezone.utc) - timedelta(seconds=10)
        result = check_data_freshness(latest_timestamp=ts)
        assert result.is_fresh is True
        assert result.age_seconds < 15

    def test_stale_data(self):
        ts = datetime.now(timezone.utc) - timedelta(seconds=120)
        result = check_data_freshness(latest_timestamp=ts)
        assert result.is_fresh is False
        assert result.age_seconds > 100

    def test_none_timestamp(self):
        result = check_data_freshness(latest_timestamp=None)
        assert result.is_fresh is False

    def test_naive_timestamp(self):
        ts = datetime.utcnow() - timedelta(seconds=5)
        result = check_data_freshness(latest_timestamp=ts)
        assert result.is_fresh is True


# ===========================================================================
# Price Validation Tests
# ===========================================================================

from app.modules.trade_planning.price_validation import validate_price


class TestPriceValidation:
    def test_valid_price(self):
        result = validate_price(
            current_price=2650.00,
            instrument="XAU/USD",
        )
        assert result.is_valid is True
        assert result.tick_aligned is True

    def test_negative_price(self):
        result = validate_price(
            current_price=-100.0,
            instrument="XAU/USD",
        )
        assert result.is_valid is False
        assert result.current_price == 0.0  # clamped to 0 for error case

    def test_zero_price(self):
        result = validate_price(
            current_price=0.0,
            instrument="XAU/USD",
        )
        assert result.is_valid is False

    def test_with_bid_ask(self):
        result = validate_price(
            current_price=2650.00,
            bid=2649.90,
            ask=2650.10,
            instrument="XAU/USD",
        )
        assert result.is_valid is True
        assert result.spread_pips is not None
        assert result.spread_pips > 0

    def test_ask_less_than_bid(self):
        result = validate_price(
            current_price=2650.00,
            bid=2651.00,
            ask=2649.00,
            instrument="XAU/USD",
        )
        assert result.is_valid is False

    def test_stale_price(self):
        ts = datetime.now(timezone.utc) - timedelta(seconds=120)
        result = validate_price(
            current_price=2650.00,
            timestamp=ts,
            instrument="XAU/USD",
        )
        assert result.is_valid is False


# ===========================================================================
# Cost Validation Tests
# ===========================================================================

from app.modules.trade_planning.cost_validation import estimate_cost


class TestCostValidation:
    def test_low_cost(self):
        result = estimate_cost(
            lots=0.1,
            spread_pips=3.0,
            instrument="XAU/USD",
            risk_amount=100.0,
        )
        assert result.within_tolerance is True
        assert result.total_cost > 0

    def test_high_cost(self):
        result = estimate_cost(
            lots=0.1,
            spread_pips=100.0,  # very wide
            instrument="XAU/USD",
            risk_amount=10.0,  # very small risk
        )
        assert result.within_tolerance is False

    def test_zero_risk(self):
        result = estimate_cost(
            lots=0.1,
            spread_pips=3.0,
            instrument="XAU/USD",
            risk_amount=0.0,
        )
        assert result.total_cost >= 0


# ===========================================================================
# Validation Helpers Tests
# ===========================================================================

from app.modules.trade_planning.validation import (
    validate_instrument,
    validate_account_balance,
    validate_risk_pct,
    validate_price as validate_price_input,
)


class TestValidationHelpers:
    def test_valid_instrument(self):
        assert validate_instrument("XAU/USD") == "XAU/USD"

    def test_instrument_normalized(self):
        assert validate_instrument("  xau/usd  ") == "XAU/USD"

    def test_empty_instrument(self):
        with pytest.raises(ValueError, match="empty"):
            validate_instrument("")

    def test_unsupported_instrument(self):
        with pytest.raises(ValueError, match="Unsupported"):
            validate_instrument("SHIBA/USD")

    def test_valid_balance(self):
        assert validate_account_balance(10000.0) == 10000.0

    def test_zero_balance(self):
        with pytest.raises(ValueError, match="positive"):
            validate_account_balance(0.0)

    def test_valid_risk_pct(self):
        assert validate_risk_pct(1.0) == 1.0

    def test_zero_risk_pct(self):
        with pytest.raises(ValueError, match="positive"):
            validate_risk_pct(0.0)

    def test_over_100_risk_pct(self):
        with pytest.raises(ValueError, match="exceed"):
            validate_risk_pct(150.0)

    def test_valid_price(self):
        assert validate_price_input(2650.0) == 2650.0

    def test_invalid_price(self):
        with pytest.raises(ValueError, match="positive"):
            validate_price_input(-10.0)


# ===========================================================================
# Service Orchestrator Tests (unit tests with mocks)
# ===========================================================================

from app.modules.trade_planning.service import TradePlanningService


class TestTradePlanningService:
    def test_history_starts_empty(self):
        service = TradePlanningService()
        assert len(service._history) == 0

    def test_get_plan_by_id_not_found(self):
        service = TradePlanningService()
        assert service.get_plan_by_id("nonexistent") is None

    def test_get_plan_history_empty(self):
        service = TradePlanningService()
        assert service.get_plan_history() == []

    def test_get_approved_plans_empty(self):
        service = TradePlanningService()
        assert service.get_approved_plans() == []

    @pytest.mark.asyncio
    async def test_generate_plan_no_trade_signal(self):
        """NO_TRADE signal should be rejected."""
        service = TradePlanningService()
        signal = _make_signal(decision=DecisionType.NO_TRADE)
        plan = await service.generate_plan(signal)
        assert plan.state == PlanState.REJECTED
        assert plan.rejection_reason == PlanRejectionReason.SIGNAL_NOT_ELIGIBLE

    @pytest.mark.asyncio
    async def test_generate_plan_unsupported_instrument(self):
        """Unsupported instrument should be rejected."""
        service = TradePlanningService()
        signal = _make_signal(instrument="XXXX/ZZZZ")
        plan = await service.generate_plan(signal)
        assert plan.state == PlanState.REJECTED

    @pytest.mark.asyncio
    async def test_health_check(self):
        service = TradePlanningService()
        health = await service.health_check()
        assert health["status"] == "healthy"
        assert health["module"] == "trade_planning"

    @pytest.mark.asyncio
    async def test_capabilities(self):
        service = TradePlanningService()
        caps = await service.get_capabilities()
        assert caps["module"] == "trade_planning"
        assert "eligibility_gate" in caps["features"]
        assert "stop_loss_engine" in caps["features"]
        assert "take_profit_engine" in caps["features"]
        assert "position_sizing" in caps["features"]
