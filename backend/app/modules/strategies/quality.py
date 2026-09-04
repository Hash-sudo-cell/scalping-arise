"""
Scalping Arise — Strategy Quality Scorer

Deterministic, configurable quality scoring for strategy evaluations.
Each strategy defines its own scoring weights. Scores are broken down
by category for full explainability.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.strategies.models import (
    ConditionCriticality,
    ConditionResult,
    ConditionStatus,
    LiquidityConditionPolicy,
    LiquidityConditionResult,
    LiquidityConditionSummary,
    QualityScore,
    QualityScoreBreakdown,
    QualityWeight,
    StrategyDefinition,
    StrategyDirection,
)

logger = logging.getLogger(__name__)


def calculate_quality_score(
    strategy: StrategyDefinition,
    condition_results: list[ConditionResult],
    direction: StrategyDirection,
    liquidity_summary: Optional[LiquidityConditionSummary] = None,
) -> QualityScore:
    """
    Calculate the quality score for a strategy evaluation.

    Scoring rules:
    - Each category has max_points defined in strategy quality_weights
    - Points are awarded based on how many conditions in that category pass
    - OPTIONAL conditions contribute to quality but cannot compensate for
      failed REQUIRED/CRITICAL conditions
    - A failed CRITICAL or REQUIRED condition means the strategy is NOT_QUALIFIED
      regardless of quality score
    - Quality score is informational — it does NOT override qualification status
    - Liquidity conditions contribute to the 'liquidity' category score
    """
    if not strategy.quality_weights:
        return QualityScore(
            score=0,
            max_score=0,
            scoring_model_version=strategy.scoring_model_version,
            breakdown=[],
            normalized_score=0.0,
        )

    # Separate required and optional condition results
    required_results = [
        r for r in condition_results
        if r.criticality in (ConditionCriticality.CRITICAL, ConditionCriticality.REQUIRED)
    ]
    optional_results = [
        r for r in condition_results
        if r.criticality == ConditionCriticality.OPTIONAL
    ]

    # Check if any required conditions failed — if so, quality score is informational only
    any_required_failed = any(r.status == ConditionStatus.FAILED for r in required_results)

    # Build category-to-conditions mapping based on condition IDs
    # Categories are inferred from condition_id prefixes
    category_map = _build_category_map(strategy)

    # Add liquidity condition results to the category map
    if liquidity_summary and liquidity_summary.condition_results:
        liq_cat = "liquidity"
        if liq_cat not in category_map:
            category_map[liq_cat] = []
        for lcond in liquidity_summary.condition_results:
            category_map[liq_cat].append(lcond.condition_id)

    breakdown: list[QualityScoreBreakdown] = []
    total_score = 0
    total_max = 0

    for weight in strategy.quality_weights:
        category = weight.category
        max_pts = weight.max_points

        # Get conditions in this category
        category_conditions = category_map.get(category, [])

        # Filter results for this category
        if category == "liquidity" and liquidity_summary:
            # Liquidity conditions have their own result model
            cat_liq_results = [
                r for r in liquidity_summary.condition_results
                if r.condition_id in category_conditions
            ]
            cat_results = []  # No regular ConditionResults for liquidity
        else:
            cat_liq_results = []
            cat_results = [
                r for r in condition_results
                if r.condition_id in category_conditions
            ]

        if not cat_results and not cat_liq_results:
            # No conditions in this category — award partial credit if no failures
            awarded = max_pts // 2  # Default: 50% for no data
            breakdown.append(QualityScoreBreakdown(
                category=category,
                points_awarded=awarded,
                max_points=max_pts,
                reason="No conditions in this category",
            ))
            total_score += awarded
            total_max += max_pts
            continue

        # Calculate regular condition points
        if cat_results:
            passed_count = sum(1 for r in cat_results if r.status == ConditionStatus.PASSED)
            total_count = len(cat_results)
            if total_count > 0:
                regular_ratio = passed_count / total_count
                regular_awarded = int(max_pts * regular_ratio)
            else:
                regular_awarded = 0
            cat_required_failed = any(
                r.status == ConditionStatus.FAILED
                and r.criticality in (ConditionCriticality.CRITICAL, ConditionCriticality.REQUIRED)
                for r in cat_results
            )
        else:
            regular_awarded = 0
            cat_required_failed = False
            passed_count = 0
            total_count = 0

        # Calculate liquidity condition points
        if cat_liq_results:
            liq_passed = sum(1 for r in cat_liq_results if r.status.value == "passed")
            liq_total = len(cat_liq_results)
            if liq_total > 0:
                liq_ratio = liq_passed / liq_total
                liq_awarded = int(max_pts * liq_ratio)
            else:
                liq_awarded = 0
            # Check if required liquidity conditions failed
            liq_required_failed = any(
                r.status.value == "failed" and r.policy == LiquidityConditionPolicy.REQUIRED
                for r in cat_liq_results
            )
            # Combine regular and liquidity scores
            awarded = regular_awarded + liq_awarded
            if cat_required_failed or liq_required_failed:
                awarded = min(awarded, max_pts // 2)
        else:
            liq_passed = 0
            liq_total = 0
            liq_required_failed = False
            awarded = regular_awarded
            if cat_required_failed:
                awarded = min(awarded, max_pts // 2)

        # Build reason string
        reason_parts = []
        if total_count > 0 and liq_total > 0:
            reason_parts.append(f"Regular: {passed_count}/{total_count} passed, Liquidity: {liq_passed}/{liq_total} passed")
        elif total_count > 0:
            reason_parts.append(f"{passed_count}/{total_count} conditions passed")
        elif liq_total > 0:
            reason_parts.append(f"Liquidity: {liq_passed}/{liq_total} conditions passed")
        if cat_required_failed:
            reason_parts.append("required condition(s) failed — capped")
        if liq_required_failed:
            reason_parts.append("required liquidity condition(s) failed — capped")

        breakdown.append(QualityScoreBreakdown(
            category=category,
            points_awarded=awarded,
            max_points=max_pts,
            reason="; ".join(reason_parts) if reason_parts else "No conditions",
        ))
        total_score += awarded
        total_max += max_pts

    normalized = total_score / total_max if total_max > 0 else 0.0

    return QualityScore(
        score=total_score,
        max_score=total_max,
        scoring_model_version=strategy.scoring_model_version,
        breakdown=breakdown,
        normalized_score=round(normalized, 4),
    )


def _build_category_map(strategy: StrategyDefinition) -> dict[str, list[str]]:
    """
    Build a mapping from category name to condition IDs.

    Categories are mapped based on condition_id prefixes:
    - tc_ = trend continuation (maps to structure, regime, multi_timeframe, technical_features, optional_confirmations)
    - pc_ = pullback continuation
    - rr_ = range reversal
    """
    # Map condition IDs to scoring categories based on naming convention
    category_mapping = {
        # Trend Continuation
        "tc_structure_supports_trend": "structure",
        "tc_regime_compatible": "regime",
        "tc_trend_alignment": "technical_features",
        "tc_momentum_confirms": "technical_features",
        "tc_macd_context": "optional_confirmations",
        "tc_volume_supports": "optional_confirmations",
        "tc_bb_position": "optional_confirmations",
        # Pullback Continuation
        "pc_underlying_trend": "structure",
        "pc_pullback_detected": "structure",
        "pc_price_near_support_resistance": "technical_features",
        "pc_momentum_recovering": "technical_features",
        "pc_ema_relationship": "technical_features",
        "pc_regime_compatible": "regime",
        "pc_macd_turning": "optional_confirmations",
        "pc_volume_confirmation": "optional_confirmations",
        # Range Reversal
        "rr_regime_ranging": "regime",
        "rr_price_at_boundary": "structure",
        "rr_rsi_extreme": "technical_features",
        "rr_bb_extreme": "technical_features",
        "rr_structure_supports_reversal": "structure",
        "rr_volume_spike": "optional_confirmations",
        "rr_macd_divergence": "optional_confirmations",
    }

    result: dict[str, list[str]] = {}
    all_conditions = strategy.required_conditions + strategy.optional_conditions
    for cond in all_conditions:
        cat = category_mapping.get(cond.condition_id, "technical_features")
        if cat not in result:
            result[cat] = []
        result[cat].append(cond.condition_id)

    return result
