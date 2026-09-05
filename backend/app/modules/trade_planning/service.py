"""
Scalping Arise — Trade Planning & Risk Engine Service

Central orchestration layer for trade plan generation.
Receives Phase 6 BUY/SELL signals and converts them into
mathematically valid trade plans.

Phase 7 plans trades only — it never executes them.

Flow:
    Phase 6 Signal ──────────────┐
                                  │
    Trade Planning Config ───────┤
                                  │
    Instrument Specification ────┤
                                  ├──→ Trade Planning Service
    Market Data (freshness) ─────┘
                                      ↓
                              Eligibility Gate
                                      ↓
                              Freshness Check
                                      ↓
                              Price Validation
                                      ↓
                              Entry Planning
                                      ↓
                              Stop-Loss Engine
                                      ↓
                              Take-Profit Engine
                                      ↓
                              Position Sizing
                                      ↓
                              Risk Guardrails
                                      ↓
                              R:R Validation
                                      ↓
                              Cost Validation
                                      ↓
                              Volatility Adjustment
                                      ↓
                              Plan Lifecycle
                                      ↓
                              Trade Plan Result
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_data.models import Instrument
from app.modules.market_data.service import MarketDataService
from app.modules.signal_engine.models import (
    DecisionType,
    SignalRecord,
    SignalState,
)
from app.modules.trade_planning.config import TradePlanningSettings, get_trade_planning_settings
from app.modules.trade_planning.cost_validation import estimate_cost
from app.modules.trade_planning.eligibility import check_signal_eligibility
from app.modules.trade_planning.entry import plan_entry
from app.modules.trade_planning.freshness import check_data_freshness
from app.modules.trade_planning.instrument_specs import get_spec_or_raise, is_instrument_supported
from app.modules.trade_planning.models import (
    EligibilityResult,
    FreshnessCheck,
    PlanRejectionReason,
    PlanSide,
    PlanState,
    PlanTransition,
    PositionSizeResult,
    PriceTickCheck,
    RiskCalculation,
    TakeProfitPlan,
    TradePlan,
    VolatilityAdjustment,
    side_from_decision,
)
from app.modules.trade_planning.position_sizing import calculate_risk, calculate_position_size
from app.modules.trade_planning.price_validation import validate_price
from app.modules.trade_planning.risk_guardrails import validate_risk_guardrails
from app.modules.trade_planning.risk_reward import validate_risk_reward
from app.modules.trade_planning.stop_loss import plan_stop_loss
from app.modules.trade_planning.take_profit import plan_take_profit

logger = logging.getLogger(__name__)


class TradePlanningService:
    """
    Central trade planning & risk engine service.

    Consumes Phase 6 signals and produces mathematically valid trade plans.
    Plans are never executed — they are output for downstream consumption.
    """

    def __init__(
        self,
        market_data_service: Optional[MarketDataService] = None,
        settings: Optional[TradePlanningSettings] = None,
    ) -> None:
        self._market_data = market_data_service or MarketDataService()
        self._settings = settings or get_trade_planning_settings()

        # Plan history (bounded ring buffer)
        self._history: deque[TradePlan] = deque(
            maxlen=self._settings.plan_history_max_size,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_plan(
        self,
        signal: SignalRecord,
        *,
        account_balance: Optional[float] = None,
        current_daily_loss: float = 0.0,
        peak_balance: Optional[float] = None,
        current_open_positions: int = 0,
    ) -> TradePlan:
        """
        Generate a complete trade plan from a Phase 6 signal.

        This is the main orchestration method. It runs the full
        pipeline from eligibility through validation.
        """
        settings = self._settings
        balance = account_balance or settings.account_balance

        # Initialize plan
        plan = TradePlan(
            instrument=signal.instrument,
            side=PlanSide.LONG,  # Will be set from signal
            state=PlanState.NO_PLAN,
            signal_id=signal.signal_id,
            signal_confidence=signal.confidence.confidence_0_100 if signal.confidence else None,
            signal_quality=signal.quality.score if signal.quality else None,
            ttl_seconds=settings.plan_ttl_seconds,
        )

        # Determine side from signal
        side = side_from_decision(signal.decision.value)
        if side is None:
            return self._reject(
                plan, PlanRejectionReason.SIGNAL_NOT_ELIGIBLE,
                f"Signal decision {signal.decision.value} is not actionable",
            )
        plan.side = side

        # === Step 1: Eligibility Gate ===
        plan.state = PlanState.DRAFT
        plan.eligibility = check_signal_eligibility(signal, settings)

        if not plan.eligibility.eligible:
            return self._reject(
                plan, PlanRejectionReason.SIGNAL_NOT_ELIGIBLE,
                f"Signal not eligible: {plan.eligibility.blocked_by}",
            )

        self._transition(plan, PlanState.DRAFT, "Eligibility passed")

        # === Step 2: Freshness Check ===
        plan.freshness = await self._check_freshness(signal.instrument)

        if not plan.freshness.is_fresh:
            return self._reject(
                plan, PlanRejectionReason.DATA_STALE,
                f"Market data stale: {plan.freshness.reason}",
            )

        # === Step 3: Get current price & validate ===
        price_data = await self._get_price_data(signal.instrument)
        if price_data is None:
            return self._reject(
                plan, PlanRejectionReason.PRICE_INVALID,
                "Unable to retrieve current price data",
            )

        plan.price_check = validate_price(
            current_price=price_data["price"],
            bid=price_data.get("bid"),
            ask=price_data.get("ask"),
            timestamp=price_data.get("timestamp"),
            instrument=signal.instrument,
            settings=settings,
        )

        if not plan.price_check.is_valid:
            return self._reject(
                plan, PlanRejectionReason.PRICE_INVALID,
                f"Price validation failed: {plan.price_check.reason}",
            )

        current_price = price_data["price"]
        bid = price_data.get("bid")
        ask = price_data.get("ask")

        # === Step 4: Volatility assessment ===
        plan.atr_value, plan.volatility_state = await self._get_volatility(signal.instrument)
        plan.volatility_adjustment = self._assess_volatility(plan.volatility_state, plan.atr_value)

        # === Step 5: Entry Planning ===
        plan.entry = plan_entry(
            side=plan.side,
            current_price=current_price,
            bid=bid,
            ask=ask,
            price_check=plan.price_check,
            instrument=signal.instrument,
            settings=settings,
        )

        if plan.entry.state.value == "entry_unavailable":
            return self._reject(
                plan, PlanRejectionReason.PRICE_INVALID,
                f"Entry unavailable: {plan.entry.reason}",
            )

        entry_price = plan.entry.entry_price or current_price

        # === Step 6: Stop-Loss Engine ===
        invalidation_level = self._extract_invalidation_level(signal)
        structure_level = self._extract_structure_level(signal)

        plan.stop_loss = plan_stop_loss(
            side=plan.side,
            entry_price=entry_price,
            atr_value=plan.atr_value,
            invalidation_level=invalidation_level,
            structure_level=structure_level,
            volatility_adjustment=plan.volatility_adjustment,
            instrument=signal.instrument,
            settings=settings,
        )

        # === Step 7: Take-Profit Engine ===
        plan.take_profit = plan_take_profit(
            side=plan.side,
            entry_price=entry_price,
            sl_price=plan.stop_loss.sl_price,
            sl_distance_price=plan.stop_loss.sl_distance_price,
            atr_value=plan.atr_value,
            instrument=signal.instrument,
            settings=settings,
        )

        self._transition(plan, PlanState.CALCULATED, "SL and TP calculated")

        # === Step 8: Position Sizing ===
        plan.risk = calculate_risk(
            account_balance=balance,
            risk_per_trade_pct=settings.risk_per_trade_pct,
            sl_distance_price=plan.stop_loss.sl_distance_price,
            instrument=signal.instrument,
            current_open_positions=current_open_positions,
            current_daily_loss=current_daily_loss,
            peak_balance=peak_balance,
            settings=settings,
        )

        # === Step 9: Risk Guardrails ===
        guardrails_pass, guardrail_rejections = validate_risk_guardrails(plan.risk, settings)

        if not guardrails_pass:
            return self._reject(
                plan, PlanRejectionReason.RISK_EXCEEDED,
                "; ".join(guardrail_rejections),
            )

        self._transition(plan, PlanState.VALIDATED, "Risk guardrails passed")

        # === Step 10: R:R Validation ===
        rr_valid, rr_reason = validate_risk_reward(
            plan.take_profit,
            plan.stop_loss.sl_distance_price,
            settings,
        )

        if not rr_valid:
            return self._reject(
                plan, PlanRejectionReason.RR_BELOW_MINIMUM,
                rr_reason,
            )

        # === Step 11: Cost Validation ===
        spread_pips = plan.price_check.spread_pips
        plan.cost = estimate_cost(
            lots=plan.risk.position_size.lots,
            spread_pips=spread_pips,
            instrument=signal.instrument,
            risk_amount=plan.risk.position_size.risk_amount,
            settings=settings,
        )

        if not plan.cost.within_tolerance:
            return self._reject(
                plan, PlanRejectionReason.SPREAD_TOO_WIDE,
                f"Cost validation failed: {plan.cost.reason}",
            )

        # === Step 12: Approve ===
        self._transition(plan, PlanState.APPROVED, "All validations passed")
        plan.approved_at = datetime.now(timezone.utc)
        plan.reason = (
            f"Plan approved: {plan.side.value} {plan.instrument} "
            f"@ {entry_price} | SL {plan.stop_loss.sl_price} | "
            f"TP1 {plan.take_profit.targets[0].tp_price if plan.take_profit.targets else 'N/A'} | "
            f"R:R {plan.take_profit.targets[0].risk_reward_ratio if plan.take_profit.targets else 0}"
        )

        # Add to history
        self._history.append(plan)

        logger.info(
            "Trade plan generated: %s %s @ %.2f SL=%.2f lots=%.4f state=%s",
            plan.side.value,
            plan.instrument,
            entry_price,
            plan.stop_loss.sl_price,
            plan.risk.position_size.lots,
            plan.state.value,
        )

        return plan

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_plan_by_id(self, plan_id: str) -> Optional[TradePlan]:
        """Get a specific plan by ID."""
        for plan in self._history:
            if plan.plan_id == plan_id:
                return plan
        return None

    def get_plan_history(self, limit: int = 20) -> list[TradePlan]:
        """Get recent plan history (most recent first)."""
        return list(reversed(list(self._history)[-limit:]))

    def get_approved_plans(self) -> list[TradePlan]:
        """Get all approved plans."""
        return [p for p in self._history if p.state == PlanState.APPROVED]

    # ------------------------------------------------------------------
    # Health & Capabilities
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """Check if the trade planning engine is operational."""
        try:
            settings = self._settings
            return {
                "status": "healthy",
                "module": "trade_planning",
                "configuration": {
                    "enabled": settings.is_enabled,
                    "min_signal_confidence": settings.min_signal_confidence_0_100,
                    "min_signal_quality": settings.min_signal_quality_0_100,
                    "risk_per_trade_pct": settings.risk_per_trade_pct,
                    "max_daily_loss_pct": settings.max_daily_loss_pct,
                    "max_drawdown_pct": settings.max_drawdown_pct,
                    "min_risk_reward": settings.min_risk_reward_ratio,
                    "plan_ttl_seconds": settings.plan_ttl_seconds,
                },
                "plans_generated": len(self._history),
                "approved_plans": len(self.get_approved_plans()),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "module": "trade_planning",
                "error": str(e),
            }

    async def get_capabilities(self) -> dict:
        """Return trade planning capabilities."""
        settings = self._settings
        return {
            "module": "trade_planning",
            "status": "active" if settings.is_enabled else "disabled",
            "features": {
                "eligibility_gate": True,
                "entry_planning": True,
                "stop_loss_engine": True,
                "take_profit_engine": True,
                "position_sizing": True,
                "risk_guardrails": True,
                "risk_reward_validation": True,
                "cost_validation": True,
                "freshness_gate": True,
                "price_validation": True,
                "volatility_adjustment": True,
                "plan_lifecycle": True,
            },
            "instruments_supported": self._get_supported_instruments(),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _reject(
        self,
        plan: TradePlan,
        reason: PlanRejectionReason,
        detail: str,
    ) -> TradePlan:
        """Transition plan to REJECTED state with reason."""
        plan.rejection_reason = reason
        plan.rejection_detail = detail
        plan.reason = detail
        self._transition(plan, PlanState.REJECTED, detail)
        plan.rejected_at = datetime.now(timezone.utc)
        self._history.append(plan)

        logger.info(
            "Trade plan rejected: %s %s — %s",
            plan.side.value,
            plan.instrument,
            detail,
        )
        return plan

    def _transition(self, plan: TradePlan, to_state: PlanState, reason: str = "") -> None:
        """Record a state transition."""
        from_state = plan.state
        plan.state_history.append(PlanTransition(
            from_state=from_state,
            to_state=to_state,
            reason=reason,
        ))
        plan.state = to_state

        # Set timestamp for key states
        now = datetime.now(timezone.utc)
        if to_state == PlanState.CALCULATED:
            plan.calculated_at = now
        elif to_state == PlanState.VALIDATED:
            plan.validated_at = now

    async def _check_freshness(self, instrument: str) -> FreshnessCheck:
        """Check market data freshness for an instrument."""
        try:
            health = await self._market_data.health_check()
            return check_data_freshness(
                latest_timestamp=health.last_data_timestamp,
                source=health.active_source or "unknown",
                settings=self._settings,
            )
        except Exception as e:
            logger.error("Freshness check failed: %s", e)
            return FreshnessCheck(
                is_fresh=False,
                age_seconds=999999,
                max_age_seconds=self._settings.freshness_max_age_seconds,
                reason=f"Health check failed: {e}",
            )

    async def _get_price_data(self, instrument: str) -> Optional[dict]:
        """Get current price data from market data service."""
        try:
            from app.modules.market_data.models import Instrument as Inst
            inst = Inst(instrument)
            price = await self._market_data.fetch_latest_price(inst)
            return {
                "price": price.price,
                "bid": price.bid,
                "ask": price.ask,
                "timestamp": price.timestamp,
            }
        except Exception as e:
            logger.error("Price data fetch failed: %s", e)
            return None

    async def _get_volatility(self, instrument: str) -> tuple[Optional[float], Optional[str]]:
        """Get ATR value and volatility state from the latest features."""
        try:
            from app.modules.technical_features.service import TechnicalFeatureService
            feature_service = TechnicalFeatureService(market_data_service=self._market_data)
            features = await feature_service.get_features(timeframe="1h", limit=100)

            if features.volatility and "atr" in features.volatility:
                atr = features.volatility["atr"]
                return atr.value, atr.state.value if atr.state else None
            return None, None
        except Exception as e:
            logger.error("Volatility fetch failed: %s", e)
            return None, None

    def _assess_volatility(
        self,
        volatility_state: Optional[str],
        atr_value: Optional[float],
    ) -> VolatilityAdjustment:
        """Determine volatility adjustment from state."""
        if volatility_state == "high":
            return VolatilityAdjustment.EXPAND
        elif volatility_state == "low":
            return VolatilityAdjustment.CONTRACT
        return VolatilityAdjustment.NORMAL

    def _extract_invalidation_level(self, signal: SignalRecord) -> Optional[float]:
        """Extract invalidation level from signal evidence or analysis."""
        for ev in signal.evidence:
            desc = ev.description.lower() if hasattr(ev, "description") else str(ev).lower()
            if "invalidation" in desc or "invalid" in desc:
                # Try to extract a numeric level
                parts = desc.split()
                for part in parts:
                    try:
                        val = float(part.replace(",", ""))
                        if val > 0:
                            return val
                    except ValueError:
                        continue
        return None

    def _extract_structure_level(self, signal: SignalRecord) -> Optional[float]:
        """Extract structure level from signal evidence."""
        for ev in signal.evidence:
            desc = ev.description.lower() if hasattr(ev, "description") else str(ev).lower()
            if "support" in desc or "resistance" in desc or "structure" in desc:
                parts = desc.split()
                for part in parts:
                    try:
                        val = float(part.replace(",", ""))
                        if val > 0:
                            return val
                    except ValueError:
                        continue
        return None

    def _get_supported_instruments(self) -> list[str]:
        """Get list of supported instruments."""
        from app.modules.trade_planning.instrument_specs import list_instruments
        return list_instruments()
