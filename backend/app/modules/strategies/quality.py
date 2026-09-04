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

    breakdown: list[QualityScoreBreakdown] = []
    total_score = 0
    total_max = 0

    for weight in strategy.quality_weights:
        category = weight.category
        max_pts = weight.max_points

        # Get conditions in this category
        category_conditions = category_map.get(category, [])

        # Filter results for this category
        cat_results = [
            r for r in condition_results
            if r.condition_id in category_conditions
        ]

        if not cat_results:
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

        passed_count = sum(1 for r in cat_results if r.status == ConditionStatus.PASSED)
        total_count = len(cat_results)

        # Calculate points
        if total_count > 0:
            ratio = passed_count / total_count
            awarded = int(max_pts * ratio)
        else:
            awarded = 0

        # If required conditions failed in this category, cap at 50%
        cat_required_failed = any(
            r.status == ConditionStatus.FAILED
            and r.criticality in (ConditionCriticality.CRITICAL, ConditionCriticality.REQUIRED)
            for r in cat_results
        )
        if cat_required_failed:
            awarded = min(awarded, max_pts // 2)

        reason_parts = []
        if passed_count == total_count:
            reason_parts.append(f"All {total_count} conditions passed")
        else:
            reason_parts.append(f"{passed_count}/{total_count} conditions passed")
        if cat_required_failed:
            reason_parts.append("required condition(s) failed — capped")

        breakdown.append(QualityScoreBreakdown(
            category=category,
            points_awarded=awarded,
            max_points=max_pts,
            reason="; ".join(reason_parts),
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
