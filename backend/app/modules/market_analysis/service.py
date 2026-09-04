"""
Scalping Arise — Market Analysis Service

Central orchestration layer for the analysis engine.
Consumes data from MarketDataService, runs all analysis components,
and produces a structured AnalysisResult.

Future phases must not call individual detectors directly —
they go through this service.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.modules.market_analysis.bos_choch import detect_bos, detect_choch
from app.modules.market_analysis.config import MarketAnalysisSettings, get_market_analysis_settings
from app.modules.market_analysis.models import (
    AnalysisContext,
    AnalysisResult,
    AnalysisStatus,
    MarketSession,
    StructurePoint,
    SwingPoint,
    TrendResult,
    TrendState,
)
from app.modules.market_analysis.regime import classify_regime
from app.modules.market_analysis.sessions import classify_session
from app.modules.market_analysis.structure import classify_structure
from app.modules.market_analysis.support_resistance import detect_zones
from app.modules.market_analysis.swing_detection import detect_swings
from app.modules.market_analysis.trend import classify_trend
from app.modules.market_analysis.validation import (
    build_analysis_context,
    validate_analysis_context,
)
from app.modules.market_data.models import (
    CandlesResponse,
    Instrument,
    NormalizedCandle,
    Timeframe,
)
from app.modules.market_data.service import MarketDataService

logger = logging.getLogger(__name__)


class MarketAnalysisService:
    """
    Central analysis orchestration service.

    Flow:
        MarketDataService
            -> Data Context Validation
            -> Swing Detection
            -> Market Structure Classification
            -> Trend Classification
            -> BOS / CHOCH Detection
            -> Support / Resistance
            -> Session Classification
            -> Market Regime Detection
            -> Structured Analysis Result
    """

    def __init__(
        self,
        market_data_service: Optional[MarketDataService] = None,
        settings: Optional[MarketAnalysisSettings] = None,
    ) -> None:
        self._market_data = market_data_service or MarketDataService()
        self._settings = settings or get_market_analysis_settings()

    async def analyze(
        self,
        instrument: Instrument = Instrument.XAU_USD,
        timeframe: Timeframe = Timeframe.H1,
        limit: int = 200,
    ) -> AnalysisResult:
        """
        Run the full analysis pipeline for an instrument and timeframe.

        Args:
            instrument: Canonical instrument to analyze.
            timeframe: Candle timeframe to analyze.
            limit: Number of candles to fetch.

        Returns:
            AnalysisResult with all analysis outputs or UNAVAILABLE status.
        """
        analysis_ts = datetime.now(timezone.utc)

        # Step 1: Fetch data from Phase 2
        try:
            candles_response = await self._market_data.fetch_candles(
                instrument=instrument,
                timeframe=timeframe,
                limit=limit,
            )
        except Exception as e:
            logger.error("Failed to fetch candles: %s", e)
            return AnalysisResult(
                status=AnalysisStatus.UNAVAILABLE,
                reason=f"Market data unavailable: {e}",
                analysis_timestamp=analysis_ts,
            )

        # Step 2: Validate data context
        is_valid, reason = validate_analysis_context(candles_response, self._settings)
        if not is_valid:
            return AnalysisResult(
                status=AnalysisStatus.UNAVAILABLE,
                reason=reason,
                analysis_timestamp=analysis_ts,
            )

        # Step 3: Build context
        context = build_analysis_context(candles_response)
        candles = candles_response.candles

        # Step 4: Swing detection
        swings = detect_swings(candles, lookback=self._settings.swing_lookback)

        # Step 5: Market structure classification
        structure_points = classify_structure(swings)

        # Step 6: Trend classification
        trend = classify_trend(
            structure_points,
            min_consecutive=2,
        )

        # Step 7: BOS detection
        bos_events = detect_bos(
            candles=candles,
            structure_points=structure_points,
            current_trend=trend.state,
            confirmation_mode=self._settings.bos_confirmation_mode,
            min_break_pct=self._settings.bos_min_break_pct,
        )

        # Step 8: CHOCH detection
        choch_events = detect_choch(
            candles=candles,
            structure_points=structure_points,
            current_trend=trend.state,
            confirmation_mode=self._settings.bos_confirmation_mode,
            min_break_pct=self._settings.bos_min_break_pct,
        )

        # Step 9: Support / Resistance
        support_zones, resistance_zones = detect_zones(
            structure_points=structure_points,
            tolerance_pct=self._settings.sr_zone_tolerance_pct,
            min_swings=self._settings.sr_min_swings,
            timeframe=timeframe.value,
        )

        # Step 10: Session classification
        session = classify_session(analysis_ts, self._settings)

        # Step 11: Market regime
        latest_price = candles[-1].close if candles else None
        regime = classify_regime(
            trend_state=trend.state,
            structure_points=structure_points,
            bos_events=bos_events,
            choch_events=choch_events,
            latest_price=latest_price,
            settings=self._settings,
        )

        # Build structure result
        from app.modules.market_analysis.models import EventsResult, RegimeResult, StructureResult, ZonesResult, TrendResult as TrendResultModel, ZonesResult as ZonesResultModel

        structure_result = StructureResult(
            points=structure_points,
            latest_labels=[sp.label for sp in structure_points[-8:]],
        )

        events_result = EventsResult(
            bos=bos_events,
            choch=choch_events,
        )

        zones_result = ZonesResult(
            support=support_zones,
            resistance=resistance_zones,
        )

        return AnalysisResult(
            status=AnalysisStatus.AVAILABLE,
            reason=f"Analysis complete: {len(structure_points)} structure points, "
                   f"{len(bos_events)} BOS, {len(choch_events)} CHOCH, "
                   f"{len(support_zones)} support zones, {len(resistance_zones)} resistance zones",
            context=context,
            trend=trend,
            structure=structure_result,
            events=events_result,
            zones=zones_result,
            session=session,
            regime=regime,
            analysis_timestamp=analysis_ts,
        )
