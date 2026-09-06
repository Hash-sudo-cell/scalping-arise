"""
Scalping Arise — Provenance Tracking

Records which modules contributed to a decision, their versions,
and health state during evaluation.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.modules.decision.models import (
    FinalDecision,
    ModuleContribution,
    ProvenanceRecord,
    ProvenanceSource,
)

logger = logging.getLogger(__name__)

# Module version registry — update when modules change
_MODULE_VERSIONS: dict[ProvenanceSource, str] = {
    ProvenanceSource.MARKET_DATA: "2.0.0",
    ProvenanceSource.MARKET_ANALYSIS: "3.0.0",
    ProvenanceSource.TECHNICAL_FEATURES: "4.0.0",
    ProvenanceSource.STRATEGIES: "5.0.0",
    ProvenanceSource.SIGNAL_ENGINE: "6.0.0",
    ProvenanceSource.TRADE_PLANNING: "7.0.0",
    ProvenanceSource.NEWS_INTELLIGENCE: "8.0.0",
    ProvenanceSource.BACKTESTING: "9.0.0",
    ProvenanceSource.DECISION_ENGINE: "10.0.0",
}


def get_module_version(source: ProvenanceSource) -> str:
    """Get the registered version for a module."""
    return _MODULE_VERSIONS.get(source, "unknown")


def record_contribution(
    provenance: ProvenanceRecord,
    source: ProvenanceSource,
    *,
    data_provided: Optional[list[str]] = None,
    evaluation_time_ms: float = 0.0,
    healthy: bool = True,
) -> None:
    """
    Record a module's contribution to a decision.

    Args:
        provenance: The provenance record to update.
        source: Which module contributed.
        data_provided: What data fields were provided.
        evaluation_time_ms: How long the evaluation took.
        healthy: Whether the module was healthy.
    """
    contribution = ModuleContribution(
        source=source,
        module_version=get_module_version(source),
        data_provided=data_provided or [],
        evaluation_time_ms=evaluation_time_ms,
        healthy=healthy,
    )
    provenance.contributions.append(contribution)
    provenance.total_evaluation_ms += evaluation_time_ms

    if healthy:
        provenance.modules_healthy += 1
    provenance.modules_total += 1


def create_provenance(decision_id: str) -> ProvenanceRecord:
    """Create a fresh provenance record for a decision."""
    return ProvenanceRecord(
        decision_id=decision_id,
        contributions=[],
        total_evaluation_ms=0.0,
        modules_healthy=0,
        modules_total=0,
    )


def attach_provenance(decision: FinalDecision) -> ProvenanceRecord:
    """
    Create and attach a provenance record to a decision.

    Returns the record for further population.
    """
    provenance = create_provenance(decision.decision_id)
    decision.provenance = provenance
    return provenance


def get_health_ratio(provenance: ProvenanceRecord) -> float:
    """
    Get the fraction of healthy modules (0.0–1.0).

    Returns 1.0 if no modules were checked (avoid division by zero).
    """
    if provenance.modules_total == 0:
        return 1.0
    return provenance.modules_healthy / provenance.modules_total
