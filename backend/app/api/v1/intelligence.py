"""
Scalping Arise — Intelligence API Endpoints

REST endpoints for Phase 8: News, Event & Performance Intelligence.

Provides:
  POST /intelligence/evaluate — Evaluate intelligence for an instrument
  GET  /intelligence/strategy-state/{strategy_id} — Get strategy performance state
  POST /intelligence/record-outcome — Record a trade outcome for tracking
  GET  /intelligence/metrics/{strategy_id} — Get strategy performance metrics
  DELETE /intelligence/clear — Clear all intelligence data
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.modules.news_intelligence.models import (
    EventDataStatus,
    EventDecision,
    IntelligenceDecision,
    OverallDecision,
    StrategyPerformanceMetrics,
    StrategyPerformanceState,
    StrategyStateRecord,
    TradeOutcome,
)
from app.modules.news_intelligence.service import NewsIntelligenceService

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

# Service singleton — same pattern as other modules
_service: Optional[NewsIntelligenceService] = None


def get_service() -> NewsIntelligenceService:
    """Get or create the intelligence service singleton."""
    global _service
    if _service is None:
        _service = NewsIntelligenceService()
    return _service


def reset_service() -> None:
    """Reset the service singleton (for testing)."""
    global _service
    _service = None


# ===================================================================
# Request / Response Models
# ===================================================================

class EvaluateRequest(BaseModel):
    """Request body for intelligence evaluation."""

    instrument: str = Field(description="Target instrument (e.g. XAU/USD)")
    signal_id: Optional[str] = Field(default=None, description="Signal ID for context")
    strategy_id: Optional[str] = Field(default=None, description="Strategy ID for performance context")


class EvaluateResponse(BaseModel):
    """Response from intelligence evaluation."""

    decision_id: str
    instrument: str
    overall_decision: str
    event_decision: str
    strategy_state: str
    event_data_status: str
    restrictions: list[str]
    reasons: list[str]
    event_context_summary: Optional[dict] = None
    strategy_performance_context: Optional[dict] = None
    timestamp: str


class RecordOutcomeRequest(BaseModel):
    """Request body for recording a trade outcome."""

    strategy_id: str
    instrument: str
    direction: str = Field(description="long or short")
    entry_price: float = Field(gt=0)
    exit_price: Optional[float] = Field(default=None, gt=0)
    pnl: float = Field(default=0.0)
    is_winner: bool = Field(default=False)


class RecordOutcomeResponse(BaseModel):
    """Response from recording a trade outcome."""

    success: bool
    strategy_id: str
    new_state: str
    sample_size: int


class StrategyStateResponse(BaseModel):
    """Response for strategy state query."""

    strategy_id: str
    state: str
    recovery_state: Optional[str]
    sample_size: int
    state_reasons: list[str]
    last_state_change: str
    last_evaluation: Optional[str]


class MetricsResponse(BaseModel):
    """Response for strategy metrics query."""

    strategy_id: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    net_pnl: float
    average_win: float
    average_loss: float
    profit_factor: float
    max_drawdown: float
    consecutive_losses: int
    recent_win_rate: float
    recent_trades: int


# ===================================================================
# Endpoints
# ===================================================================

@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_intelligence(request: EvaluateRequest) -> EvaluateResponse:
    """
    Evaluate intelligence for an instrument.

    Runs the full Phase 8 pipeline: event normalization → relevance →
    impact → risk → performance → unified decision.
    """
    service = get_service()

    decision = await service.get_intelligence_decision(
        instrument=request.instrument,
        signal_id=request.signal_id,
        strategy_id=request.strategy_id,
    )

    # Build event context summary
    event_summary = None
    if decision.event_context:
        event_summary = {
            "total_events": decision.event_context.total_events,
            "relevant_events": decision.event_context.relevant_events,
            "high_impact_events": decision.event_context.high_impact_events,
            "event_decision": decision.event_context.event_decision.value,
            "freshness_status": decision.event_context.freshness.status.value,
        }

    # Build strategy performance context
    strategy_perf = None
    if decision.strategy_performance_context:
        m = decision.strategy_performance_context
        strategy_perf = {
            "total_trades": m.total_trades,
            "win_rate": m.win_rate,
            "net_pnl": m.net_pnl,
            "profit_factor": m.profit_factor,
            "max_drawdown": m.max_drawdown,
            "consecutive_losses": m.consecutive_losses,
        }

    return EvaluateResponse(
        decision_id=decision.decision_id,
        instrument=decision.instrument,
        overall_decision=decision.overall_decision.value,
        event_decision=decision.event_decision.value,
        strategy_state=decision.strategy_state.value,
        event_data_status=decision.event_data_status.value,
        restrictions=decision.restrictions,
        reasons=decision.reasons,
        event_context_summary=event_summary,
        strategy_performance_context=strategy_perf,
        timestamp=decision.timestamp.isoformat(),
    )


@router.get("/strategy-state/{strategy_id}", response_model=StrategyStateResponse)
async def get_strategy_state(strategy_id: str) -> StrategyStateResponse:
    """Get the current performance state for a strategy."""
    service = get_service()
    state = service.get_strategy_state(strategy_id)

    return StrategyStateResponse(
        strategy_id=state.strategy_id,
        state=state.state.value,
        recovery_state=state.recovery_state.value if state.recovery_state else None,
        sample_size=state.sample_size,
        state_reasons=state.state_reasons,
        last_state_change=state.last_state_change.isoformat(),
        last_evaluation=state.last_evaluation.isoformat() if state.last_evaluation else None,
    )


@router.post("/record-outcome", response_model=RecordOutcomeResponse)
async def record_outcome(request: RecordOutcomeRequest) -> RecordOutcomeResponse:
    """
    Record a realized trade outcome for performance tracking.

    Triggers automatic strategy state re-evaluation.
    """
    service = get_service()

    outcome = TradeOutcome(
        strategy_id=request.strategy_id,
        instrument=request.instrument,
        direction=request.direction,
        entry_price=request.entry_price,
        exit_price=request.exit_price,
        pnl=request.pnl,
        is_winner=request.is_winner,
    )

    service.record_trade_outcome(outcome)
    state = service.get_strategy_state(request.strategy_id)

    return RecordOutcomeResponse(
        success=True,
        strategy_id=state.strategy_id,
        new_state=state.state.value,
        sample_size=state.sample_size,
    )


@router.get("/metrics/{strategy_id}", response_model=MetricsResponse)
async def get_metrics(strategy_id: str) -> MetricsResponse:
    """Get computed performance metrics for a strategy."""
    service = get_service()
    metrics = service.get_strategy_metrics(strategy_id)

    return MetricsResponse(
        strategy_id=metrics.strategy_id,
        total_trades=metrics.total_trades,
        winning_trades=metrics.winning_trades,
        losing_trades=metrics.losing_trades,
        win_rate=metrics.win_rate,
        net_pnl=metrics.net_pnl,
        average_win=metrics.average_win,
        average_loss=metrics.average_loss,
        profit_factor=metrics.profit_factor,
        max_drawdown=metrics.max_drawdown,
        consecutive_losses=metrics.consecutive_losses,
        recent_win_rate=metrics.recent_win_rate,
        recent_trades=metrics.recent_trades,
    )


@router.delete("/clear")
async def clear_intelligence(
    strategy_id: Optional[str] = Query(default=None, description="Strategy ID to clear, or all if omitted"),
) -> dict:
    """Clear all intelligence data (outcomes, states, events)."""
    service = get_service()
    service.clear_strategy_outcomes(strategy_id)
    service.clear_events()
    return {
        "success": True,
        "cleared_strategy_id": strategy_id,
        "message": f"Cleared intelligence data{'for ' + strategy_id if strategy_id else ' for all strategies'}",
    }
