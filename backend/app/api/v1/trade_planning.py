"""
Scalping Arise — Trade Planning API Endpoints

Phase 7 API for trade plan generation, querying, and health checks.
Plans are never executed — they are output for downstream consumption.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.modules.market_data.models import Instrument
from app.modules.signal_engine.service import SignalEngineService
from app.modules.trade_planning.config import get_trade_planning_settings
from app.modules.trade_planning.instrument_specs import get_spec, list_instruments
from app.modules.trade_planning.service import TradePlanningService

router = APIRouter(prefix="/trade-planning", tags=["trade-planning"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GeneratePlanRequest(BaseModel):
    """Request to generate a trade plan from a signal."""

    instrument: str = Field(default="XAU/USD", description="Instrument to trade")
    account_balance: float | None = Field(default=None, gt=0, description="Override account balance")
    current_daily_loss: float = Field(default=0.0, ge=0, description="Current daily loss amount")
    peak_balance: float | None = Field(default=None, gt=0, description="Peak account balance for drawdown calc")
    current_open_positions: int = Field(default=0, ge=0, description="Current open position count")


class PlanSummary(BaseModel):
    """Compact plan summary for list responses."""

    plan_id: str
    instrument: str
    side: str
    state: str
    entry_price: float | None = None
    sl_price: float | None = None
    tp1_price: float | None = None
    lots: float | None = None
    risk_reward: float | None = None
    rejection_reason: str | None = None
    created_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate", summary="Generate trade plan from latest signal")
async def generate_plan(request: GeneratePlanRequest) -> dict:
    """
    Generate a trade plan from the latest active signal for the given instrument.

    Runs the full Phase 7 pipeline: eligibility → freshness → price → entry →
    SL → TP → sizing → risk → R:R → cost → approve/reject.
    """
    settings = get_trade_planning_settings()
    if not settings.is_enabled:
        raise HTTPException(status_code=503, detail="Trade planning engine is disabled")

    # Get latest signal from signal engine
    signal_service = SignalEngineService()
    active_signals = signal_service.get_active_signals()

    # Find matching signal
    signal = None
    for s in active_signals:
        if s.instrument == request.instrument:
            signal = s
            break

    if signal is None:
        # Try to run signal evaluation to get a fresh signal
        try:
            result = await signal_service.evaluate_signal(instrument=request.instrument)
            if result.signal_record and result.signal_record.is_active:
                signal = result.signal_record
        except Exception:
            pass

    if signal is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active signal found for {request.instrument}",
        )

    # Generate plan
    planning_service = TradePlanningService()
    plan = await planning_service.generate_plan(
        signal=signal,
        account_balance=request.account_balance,
        current_daily_loss=request.current_daily_loss,
        peak_balance=request.peak_balance,
        current_open_positions=request.current_open_positions,
    )

    return _plan_to_dict(plan)


@router.get("/history", summary="Get trade plan history")
async def get_plan_history(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    """Get recent trade plan history, most recent first."""
    service = TradePlanningService()
    plans = service.get_plan_history(limit=limit)
    return [_plan_to_dict(p) for p in plans]


@router.get("/approved", summary="Get approved trade plans")
async def get_approved_plans() -> list[dict]:
    """Get all currently approved trade plans."""
    service = TradePlanningService()
    plans = service.get_approved_plans()
    return [_plan_to_dict(p) for p in plans]


@router.get("/plans/{plan_id}", summary="Get plan by ID")
async def get_plan(plan_id: str) -> dict:
    """Get a specific trade plan by its ID."""
    service = TradePlanningService()
    plan = service.get_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return _plan_to_dict(plan)


@router.get("/instruments", summary="List supported instruments")
async def list_supported_instruments() -> dict:
    """List all instruments with registered specifications."""
    instruments = list_instruments()
    specs = {}
    for inst in instruments:
        spec = get_spec(inst)
        if spec:
            specs[inst] = {
                "tick_size": spec.tick_size,
                "contract_size": spec.contract_size,
                "min_lot": spec.min_lot,
                "max_lot": spec.max_lot,
                "typical_spread_pips": spec.typical_spread_pips,
            }
    return {"instruments": instruments, "specs": specs}


@router.get("/health", summary="Trade planning health check")
async def health_check() -> dict:
    """Check if the trade planning engine is operational."""
    service = TradePlanningService()
    return await service.health_check()


@router.get("/capabilities", summary="Trade planning capabilities")
async def capabilities() -> dict:
    """Return trade planning engine capabilities."""
    service = TradePlanningService()
    return await service.get_capabilities()


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _plan_to_dict(plan: "TradePlan") -> dict:
    """Convert a TradePlan to a JSON-serializable dict."""
    return {
        "plan_id": plan.plan_id,
        "instrument": plan.instrument,
        "side": plan.side.value,
        "state": plan.state.value,
        "signal_id": plan.signal_id,
        "signal_confidence": plan.signal_confidence,
        "signal_quality": plan.signal_quality,
        "entry": {
            "state": plan.entry.state.value if plan.entry else None,
            "entry_type": plan.entry.entry_type.value if plan.entry else None,
            "entry_price": plan.entry.entry_price if plan.entry else None,
        } if plan.entry else None,
        "stop_loss": {
            "sl_type": plan.stop_loss.sl_type.value if plan.stop_loss else None,
            "sl_price": plan.stop_loss.sl_price if plan.stop_loss else None,
            "sl_distance_pips": plan.stop_loss.sl_distance_pips if plan.stop_loss else None,
            "risk_per_lot": plan.stop_loss.risk_per_lot if plan.stop_loss else None,
        } if plan.stop_loss else None,
        "take_profit": {
            "targets": [
                {
                    "target": t.target.value,
                    "tp_price": t.tp_price,
                    "tp_distance_pips": t.tp_distance_pips,
                    "risk_reward_ratio": t.risk_reward_ratio,
                    "partial_close_pct": t.partial_close_pct,
                }
                for t in plan.take_profit.targets
            ] if plan.take_profit else [],
        } if plan.take_profit else None,
        "risk": {
            "lots": plan.risk.position_size.lots if plan.risk else None,
            "risk_amount": plan.risk.position_size.risk_amount if plan.risk else None,
            "risk_pct": plan.risk.position_size.risk_pct_actual if plan.risk else None,
            "margin_required": plan.risk.position_size.margin_required if plan.risk else None,
            "within_risk_limits": plan.risk.within_risk_limits if plan.risk else None,
            "daily_loss_remaining": plan.risk.daily_loss_remaining if plan.risk else None,
            "max_drawdown_remaining": plan.risk.max_drawdown_remaining if plan.risk else None,
            "warnings": plan.risk.warnings if plan.risk else [],
            "rejections": plan.risk.rejections if plan.risk else [],
        } if plan.risk else None,
        "cost": {
            "spread_cost": plan.cost.spread_cost if plan.cost else None,
            "total_cost": plan.cost.total_cost if plan.cost else None,
            "cost_pct_of_risk": plan.cost.cost_pct_of_risk if plan.cost else None,
            "within_tolerance": plan.cost.within_tolerance if plan.cost else None,
        } if plan.cost else None,
        "volatility_adjustment": plan.volatility_adjustment.value,
        "rejection_reason": plan.rejection_reason.value if plan.rejection_reason else None,
        "rejection_detail": plan.rejection_detail,
        "reason": plan.reason,
        "created_at": plan.created_at.isoformat(),
        "ttl_seconds": plan.ttl_seconds,
        "state_history": [
            {
                "from_state": t.from_state.value,
                "to_state": t.to_state.value,
                "reason": t.reason,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in plan.state_history
        ],
    }
