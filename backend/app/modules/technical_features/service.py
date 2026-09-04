"""
Scalping Arise — Technical Feature Service

Orchestrates all feature calculations. Validates data, runs each
indicator, aggregates availability, and returns a complete FeatureResult.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.market_data.models import CandlesResponse
from app.modules.market_data.service import MarketDataService
from app.modules.technical_features.config import TechnicalFeaturesSettings, get_technical_features_settings
from app.modules.technical_features.validation import validate_feature_context, build_feature_metadata
from app.modules.technical_features.ema import calculate_ema_features
from app.modules.technical_features.rsi import calculate_rsi
from app.modules.technical_features.macd import calculate_macd
from app.modules.technical_features.atr import calculate_atr
from app.modules.technical_features.bollinger import calculate_bollinger_bands
from app.modules.technical_features.volume import calculate_volume_features
from app.modules.technical_features.price_features import calculate_price_features
from app.modules.technical_features.models import (
    FeatureAvailability,
    FeatureAvailabilityItem,
    FeatureResult,
    FeatureSetStatus,
    MultiTimeframeResult,
    TimeframeFeatureResult,
    VolatilityClassification,
    VolumeState,
)

logger = logging.getLogger(__name__)


class TechnicalFeatureService:
    """
    Orchestrates technical feature calculation.

    Consumes normalized data from MarketDataService and produces
    a complete FeatureResult with all approved indicators.
    """

    def __init__(
        self,
        market_data_service: MarketDataService,
        settings: Optional[TechnicalFeaturesSettings] = None,
    ) -> None:
        self._market_data_service = market_data_service
        self._settings = settings or get_technical_features_settings()

    async def get_features(
        self,
        timeframe: str = "1h",
        limit: int = 300,
    ) -> FeatureResult:
        """
        Calculate all technical features for the given timeframe.

        Args:
            timeframe: Candle timeframe.
            limit: Number of candles to request.

        Returns:
            FeatureResult with all features and availability status.
        """
        cfg = self._settings

        # Fetch candles from Phase 2
        try:
            candles_response = await self._market_data_service.get_candles(
                timeframe=timeframe,
                limit=limit,
            )
        except Exception as e:
            logger.error("Failed to fetch candles: %s", e)
            return FeatureResult(
                status=FeatureAvailability.UNAVAILABLE,
                reason=f"Failed to fetch candle data: {e}",
            )

        # Validate data context
        is_valid, validation_reason = validate_feature_context(candles_response, cfg)
        if not is_valid:
            return FeatureResult(
                status=FeatureAvailability.INSUFFICIENT_DATA,
                reason=validation_reason,
            )

        # Build metadata
        metadata = build_feature_metadata(candles_response)

        # Extract candles for calculation
        candles = candles_response.candles

        # Calculate each feature category independently
        availability: list[FeatureAvailabilityItem] = []
        warnings: list[str] = []

        # Trend (EMA)
        try:
            ema_result = calculate_ema_features(candles, cfg)
            trend_availability = _assess_ema_availability(ema_result)
            availability.append(trend_availability)
        except Exception as e:
            logger.error("EMA calculation failed: %s", e)
            ema_result = None
            availability.append(FeatureAvailabilityItem(
                name="trend",
                status=FeatureAvailability.UNAVAILABLE,
                reason=f"EMA calculation error: {e}",
            ))
            warnings.append("EMA feature unavailable due to calculation error")

        # Momentum (RSI + MACD)
        try:
            rsi_result = calculate_rsi(candles, cfg.rsi_period, cfg)
            rsi_availability = FeatureAvailabilityItem(
                name="rsi",
                status=rsi_result.availability,
                reason=f"RSI({cfg.rsi_period}) = {rsi_result.value}" if rsi_result.value else "Insufficient data",
            )
            availability.append(rsi_availability)
        except Exception as e:
            logger.error("RSI calculation failed: %s", e)
            rsi_result = None
            availability.append(FeatureAvailabilityItem(
                name="rsi",
                status=FeatureAvailability.UNAVAILABLE,
                reason=f"RSI calculation error: {e}",
            ))
            warnings.append("RSI feature unavailable due to calculation error")

        try:
            macd_result = calculate_macd(
                candles,
                cfg.macd_fast_period,
                cfg.macd_slow_period,
                cfg.macd_signal_period,
                cfg,
            )
            macd_availability = _assess_macd_availability(macd_result)
            availability.append(macd_availability)
        except Exception as e:
            logger.error("MACD calculation failed: %s", e)
            macd_result = None
            availability.append(FeatureAvailabilityItem(
                name="macd",
                status=FeatureAvailability.UNAVAILABLE,
                reason=f"MACD calculation error: {e}",
            ))
            warnings.append("MACD feature unavailable due to calculation error")

        momentum = {}
        if rsi_result:
            momentum["rsi"] = rsi_result
        if macd_result:
            momentum["macd"] = macd_result

        # Volatility (ATR + Bollinger)
        try:
            atr_result = calculate_atr(candles, cfg.atr_period, cfg)
            atr_availability = FeatureAvailabilityItem(
                name="atr",
                status=atr_result.availability,
                reason=f"ATR({cfg.atr_period}) = {atr_result.value}" if atr_result.value else "Insufficient data",
            )
            availability.append(atr_availability)
        except Exception as e:
            logger.error("ATR calculation failed: %s", e)
            atr_result = None
            availability.append(FeatureAvailabilityItem(
                name="atr",
                status=FeatureAvailability.UNAVAILABLE,
                reason=f"ATR calculation error: {e}",
            ))
            warnings.append("ATR feature unavailable due to calculation error")

        try:
            bb_result = calculate_bollinger_bands(
                candles,
                cfg.bb_period,
                cfg.bb_std_dev,
                cfg,
            )
            bb_availability = FeatureAvailabilityItem(
                name="bollinger_bands",
                status=bb_result.availability,
                reason=f"Bollinger position: {bb_result.price_position.value}" if bb_result.middle_band else "Insufficient data",
            )
            availability.append(bb_availability)
        except Exception as e:
            logger.error("Bollinger calculation failed: %s", e)
            bb_result = None
            availability.append(FeatureAvailabilityItem(
                name="bollinger_bands",
                status=FeatureAvailability.UNAVAILABLE,
                reason=f"Bollinger calculation error: {e}",
            ))
            warnings.append("Bollinger Bands feature unavailable due to calculation error")

        volatility = {}
        if atr_result:
            volatility["atr"] = atr_result
        if bb_result:
            volatility["bollinger_bands"] = bb_result

        # Volume (optional — must not fail others)
        try:
            volume_result = calculate_volume_features(candles, cfg.volume_sma_period, cfg)
            volume_availability = FeatureAvailabilityItem(
                name="volume",
                status=volume_result.availability,
                reason=f"Volume state: {volume_result.state.value}" if volume_result.state != VolumeState.UNAVAILABLE else "Volume data not available",
            )
            availability.append(volume_availability)
        except Exception as e:
            logger.error("Volume calculation failed: %s", e)
            volume_result = None
            availability.append(FeatureAvailabilityItem(
                name="volume",
                status=FeatureAvailability.UNAVAILABLE,
                reason=f"Volume calculation error: {e}",
            ))
            warnings.append("Volume feature unavailable due to calculation error")

        # Price features
        try:
            price_result = calculate_price_features(candles, cfg.price_lookback, cfg)
            price_availability = FeatureAvailabilityItem(
                name="price",
                status=price_result.availability,
                reason=f"Price: {price_result.current_price}" if price_result.current_price else "Insufficient data",
            )
            availability.append(price_availability)
        except Exception as e:
            logger.error("Price feature calculation failed: %s", e)
            price_result = None
            availability.append(FeatureAvailabilityItem(
                name="price",
                status=FeatureAvailability.UNAVAILABLE,
                reason=f"Price calculation error: {e}",
            ))
            warnings.append("Price features unavailable due to calculation error")

        # Determine overall status
        statuses = [a.status for a in availability]
        if all(s == FeatureAvailability.AVAILABLE for s in statuses):
            overall_status = FeatureAvailability.AVAILABLE
            overall_reason = "All features calculated successfully"
        elif any(s == FeatureAvailability.AVAILABLE for s in statuses):
            overall_status = FeatureAvailability.AVAILABLE
            available_count = sum(1 for s in statuses if s == FeatureAvailability.AVAILABLE)
            overall_reason = f"{available_count}/{len(statuses)} features available"
        elif any(s == FeatureAvailability.INSUFFICIENT_DATA for s in statuses):
            overall_status = FeatureAvailability.INSUFFICIENT_DATA
            overall_reason = "Insufficient data for most features"
        else:
            overall_status = FeatureAvailability.UNAVAILABLE
            overall_reason = "No features could be calculated"

        # Extended volatility classification
        vol_class, vol_class_reason = _classify_volatility(atr_result, cfg)

        # Feature-set status
        fs_status, fs_reason = _assess_feature_set_status(availability)

        return FeatureResult(
            status=overall_status,
            reason=overall_reason,
            feature_set_status=fs_status,
            feature_set_reason=fs_reason,
            volatility_classification=vol_class,
            volatility_classification_reason=vol_class_reason,
            metadata=metadata,
            trend=ema_result,
            momentum=momentum if momentum else None,
            volatility=volatility if volatility else None,
            volume=volume_result,
            price=price_result,
            availability=availability,
            warnings=warnings,
        )

    async def get_features_multi_timeframe(
        self,
        timeframes: list[str],
        limit: int = 300,
    ) -> MultiTimeframeResult:
        """
        Calculate technical features for multiple timeframes independently.

        Each timeframe is calculated from its own candle series.
        A single timeframe failing does not affect other timeframes.

        Args:
            timeframes: List of timeframe strings (e.g. ["1m", "5m", "15m"]).
            limit: Number of candles per timeframe.

        Returns:
            MultiTimeframeResult with per-timeframe FeatureResult objects.
        """
        results: list[TimeframeFeatureResult] = []
        all_warnings: list[str] = []

        for tf in timeframes:
            try:
                result = await self.get_features(timeframe=tf, limit=limit)
                results.append(TimeframeFeatureResult(timeframe=tf, result=result))
                if result.warnings:
                    all_warnings.extend(
                        [f"[{tf}] {w}" for w in result.warnings]
                    )
                elif result.status == FeatureAvailability.UNAVAILABLE:
                    all_warnings.append(
                        f"[{tf}] {result.reason}"
                    )
            except Exception as e:
                logger.error("Multi-timeframe calculation failed for %s: %s", tf, e)
                results.append(TimeframeFeatureResult(
                    timeframe=tf,
                    result=FeatureResult(
                        status=FeatureAvailability.UNAVAILABLE,
                        reason=f"Calculation failed: {e}",
                    ),
                ))
                all_warnings.append(f"[{tf}] Calculation failed: {e}")

        # Aggregate feature-set status across timeframes
        fs_statuses = [r.result.feature_set_status for r in results]
        if not fs_statuses:
            agg_status = FeatureSetStatus.UNAVAILABLE
            agg_reason = "No timeframes provided"
        elif all(s == FeatureSetStatus.READY for s in fs_statuses):
            agg_status = FeatureSetStatus.READY
            agg_reason = "All timeframes ready"
        elif any(s in (FeatureSetStatus.READY, FeatureSetStatus.WARMING_UP) for s in fs_statuses):
            agg_status = FeatureSetStatus.WARMING_UP
            ready_tfs = [
                r.timeframe for r in results
                if r.result.feature_set_status == FeatureSetStatus.READY
            ]
            warming_tfs = [
                r.timeframe for r in results
                if r.result.feature_set_status == FeatureSetStatus.WARMING_UP
            ]
            parts = []
            if ready_tfs:
                parts.append(f"ready: {', '.join(ready_tfs)}")
            if warming_tfs:
                parts.append(f"warming: {', '.join(warming_tfs)}")
            agg_reason = f"Partial readiness ({'; '.join(parts)})"
        else:
            agg_status = FeatureSetStatus.UNAVAILABLE
            agg_reason = "All timeframes unavailable"

        return MultiTimeframeResult(
            timeframes=results,
            feature_set_status=agg_status,
            feature_set_reason=agg_reason,
            warnings=all_warnings,
        )

    async def health_check(self) -> dict:
        """Check if the feature service is operational."""
        try:
            settings = self._settings
            return {
                "status": "healthy",
                "module": "technical_features",
                "configuration": {
                    "ema_periods": [settings.ema_fast_period, settings.ema_medium_period, settings.ema_slow_period],
                    "rsi_period": settings.rsi_period,
                    "macd_periods": [settings.macd_fast_period, settings.macd_slow_period, settings.macd_signal_period],
                    "atr_period": settings.atr_period,
                    "atr_thresholds": {
                        "low_pct": settings.atr_low_threshold_pct,
                        "high_pct": settings.atr_high_threshold_pct,
                        "extreme_pct": settings.atr_extreme_threshold_pct,
                    },
                    "bollinger": {"period": settings.bb_period, "std_dev": settings.bb_std_dev},
                    "volume_sma_period": settings.volume_sma_period,
                    "price_lookback": settings.price_lookback,
                },
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "module": "technical_features",
                "error": str(e),
            }

    async def get_capabilities(self) -> dict:
        """Return feature capabilities and configuration."""
        settings = self._settings
        return {
            "module": "technical_features",
            "status": "active",
            "features": {
                "trend": {
                    "ema": {
                        "periods": [settings.ema_fast_period, settings.ema_medium_period, settings.ema_slow_period],
                        "capabilities": ["alignment", "direction", "price_relative"],
                    },
                },
                "momentum": {
                    "rsi": {
                        "period": settings.rsi_period,
                        "thresholds": {
                            "oversold": settings.rsi_oversold_threshold,
                            "weak": settings.rsi_weak_threshold,
                            "strong": settings.rsi_strong_threshold,
                            "overbought": settings.rsi_overbought_threshold,
                        },
                    },
                    "macd": {
                        "fast": settings.macd_fast_period,
                        "slow": settings.macd_slow_period,
                        "signal": settings.macd_signal_period,
                    },
                },
                "volatility": {
                    "atr": {
                        "period": settings.atr_period,
                        "thresholds": {
                            "low_pct": settings.atr_low_threshold_pct,
                            "high_pct": settings.atr_high_threshold_pct,
                            "extreme_pct": settings.atr_extreme_threshold_pct,
                        },
                    },
                    "bollinger_bands": {
                        "period": settings.bb_period,
                        "std_dev": settings.bb_std_dev,
                    },
                },
                "volume": {
                    "sma_period": settings.volume_sma_period,
                    "thresholds": {
                        "high": settings.volume_high_threshold,
                        "low": settings.volume_low_threshold,
                    },
                },
                "price": {
                    "lookback": settings.price_lookback,
                },
            },
            "minimum_candles_required": settings.ema_slow_period + settings.macd_signal_period,
        }


def _assess_ema_availability(ema_result) -> FeatureAvailabilityItem:
    """Assess overall EMA availability from EMAResult.

    Reports per-EMA availability in the reason string and determines
    the top-level status based on the slowest available component.
    """
    fast_ok = ema_result.fast.availability == FeatureAvailability.AVAILABLE
    medium_ok = ema_result.medium.availability == FeatureAvailability.AVAILABLE
    slow_ok = ema_result.slow.availability == FeatureAvailability.AVAILABLE

    parts = []
    if fast_ok:
        parts.append(f"EMA{ema_result.fast.period}=available")
    else:
        parts.append(f"EMA{ema_result.fast.period}=insufficient_data")
    if medium_ok:
        parts.append(f"EMA{ema_result.medium.period}=available")
    else:
        parts.append(f"EMA{ema_result.medium.period}=insufficient_data")
    if slow_ok:
        parts.append(f"EMA{ema_result.slow.period}=available")
    else:
        parts.append(f"EMA{ema_result.slow.period}=insufficient_data")

    reason = ", ".join(parts)

    if fast_ok and medium_ok and slow_ok:
        status = FeatureAvailability.AVAILABLE
        reason = f"EMA alignment: {ema_result.alignment.value} ({reason})"
    elif fast_ok or medium_ok:
        status = FeatureAvailability.INSUFFICIENT_DATA
        reason = f"Partial EMA warm-up ({reason})"
    else:
        status = FeatureAvailability.INSUFFICIENT_DATA
        reason = f"Insufficient data for EMA ({reason})"

    return FeatureAvailabilityItem(
        name="trend",
        status=status,
        reason=reason,
    )


def _assess_macd_availability(macd_result) -> FeatureAvailabilityItem:
    """Assess MACD availability with per-component detail."""
    ml = macd_result.macd_line_availability.value
    sl = macd_result.signal_line_availability.value
    hist = macd_result.histogram_availability.value

    reason = f"MACD line={ml}, signal={sl}, histogram={hist}"

    if macd_result.availability == FeatureAvailability.AVAILABLE:
        reason = f"MACD context: {macd_result.context.value} ({reason})"
    elif macd_result.macd_line_availability == FeatureAvailability.AVAILABLE:
        reason = f"MACD warming up ({reason})"
    else:
        reason = f"MACD insufficient data ({reason})"

    return FeatureAvailabilityItem(
        name="macd",
        status=macd_result.availability,
        reason=reason,
    )


def _classify_volatility(
    atr_result,
    cfg: TechnicalFeaturesSettings,
) -> tuple[VolatilityClassification, str]:
    """
    Classify volatility into extended 4-level scale.

    Uses ATR percentage against configurable thresholds:
    - EXTREME: ATR% >= atr_extreme_threshold_pct (default 3.0%)
    - HIGH: ATR% >= atr_high_threshold_pct (default 1.5%)
    - NORMAL: ATR% between low and high thresholds
    - LOW: ATR% <= atr_low_threshold_pct (default 0.3%)

    Returns:
        Tuple of (classification, reason_string).
    """
    if atr_result is None or atr_result.percentage is None:
        return VolatilityClassification.NORMAL, "ATR unavailable — defaulting to normal"

    atr_pct = atr_result.percentage

    if atr_pct >= cfg.atr_extreme_threshold_pct:
        classification = VolatilityClassification.EXTREME
        reason = (
            f"ATR% {atr_pct:.3f}% >= extreme threshold {cfg.atr_extreme_threshold_pct}%"
        )
    elif atr_pct >= cfg.atr_high_threshold_pct:
        classification = VolatilityClassification.HIGH
        reason = (
            f"ATR% {atr_pct:.3f}% >= high threshold {cfg.atr_high_threshold_pct}%"
        )
    elif atr_pct <= cfg.atr_low_threshold_pct:
        classification = VolatilityClassification.LOW
        reason = (
            f"ATR% {atr_pct:.3f}% <= low threshold {cfg.atr_low_threshold_pct}%"
        )
    else:
        classification = VolatilityClassification.NORMAL
        reason = (
            f"ATR% {atr_pct:.3f}% between low ({cfg.atr_low_threshold_pct}%) "
            f"and high ({cfg.atr_high_threshold_pct}%) thresholds"
        )

    return classification, reason


def _assess_feature_set_status(
    availability: list[FeatureAvailabilityItem],
) -> tuple[FeatureSetStatus, str]:
    """
    Assess overall feature-set readiness.

    Rules:
    - READY: All core features (trend, rsi, macd, atr, bollinger, price) are AVAILABLE.
      Volume is optional — its absence does not prevent READY.
    - WARMING_UP: Market data exists but core features are still warming up.
      At least one core feature is AVAILABLE or INSUFFICIENT_DATA.
    - UNAVAILABLE: Data fetch failed, service error, or all features UNAVAILABLE.

    Returns:
        Tuple of (feature_set_status, reason_string).
    """
    core_features = {"trend", "rsi", "macd", "atr", "bollinger_bands", "price"}
    core_statuses = {a.name: a.status for a in availability if a.name in core_features}

    if not core_statuses:
        return FeatureSetStatus.UNAVAILABLE, "No core features computed"

    # Check if we have any data at all
    has_data = any(
        s in (FeatureAvailability.AVAILABLE, FeatureAvailability.INSUFFICIENT_DATA)
        for s in core_statuses.values()
    )
    if not has_data:
        return FeatureSetStatus.UNAVAILABLE, "All core features unavailable — no data"

    # READY: all core features AVAILABLE
    all_available = all(
        s == FeatureAvailability.AVAILABLE for s in core_statuses.values()
    )
    if all_available:
        available_names = list(core_statuses.keys())
        return FeatureSetStatus.READY, (
            f"All core features ready: {', '.join(available_names)}"
        )

    # WARMING_UP: at least one core feature available or insufficient_data
    any_usable = any(
        s in (FeatureAvailability.AVAILABLE, FeatureAvailability.INSUFFICIENT_DATA)
        for s in core_statuses.values()
    )
    if any_usable:
        available = [
            n for n, s in core_statuses.items()
            if s == FeatureAvailability.AVAILABLE
        ]
        warming = [
            n for n, s in core_statuses.items()
            if s == FeatureAvailability.INSUFFICIENT_DATA
        ]
        parts = []
        if available:
            parts.append(f"available: {', '.join(available)}")
        if warming:
            parts.append(f"warming up: {', '.join(warming)}")
        return FeatureSetStatus.WARMING_UP, f"Feature set warming up ({'; '.join(parts)})"

    return FeatureSetStatus.UNAVAILABLE, "All core features unavailable"


