"""
Scalping Arise — Result Versioning

Deterministic run IDs, version tracking, and result comparison
for backtest runs. Enables reproducibility and audit trails.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.modules.backtesting.config import BacktestingSettings, get_backtesting_settings
from app.modules.backtesting.models import BacktestResult, RunMetadata

logger = logging.getLogger(__name__)


class ResultVersionManager:
    """
    Manages backtest result versioning and comparison.

    Provides:
    - Deterministic run ID generation
    - Config hashing for reproducibility tracking
    - Result storage and retrieval
    - Run comparison
    """

    def __init__(
        self,
        settings: Optional[BacktestingSettings] = None,
    ) -> None:
        self._settings = settings or get_backtesting_settings()
        self._results: dict[str, BacktestResult] = {}
        self._metadata: dict[str, RunMetadata] = {}

    def create_metadata(
        self,
        config: dict[str, Any],
        description: str = "",
        tags: Optional[list[str]] = None,
        parent_run_id: Optional[str] = None,
        created_by: str = "system",
    ) -> RunMetadata:
        """Create run metadata with deterministic config hash."""
        metadata = RunMetadata(
            description=description,
            tags=tags or [],
            parent_run_id=parent_run_id,
            created_by=created_by,
        )
        metadata.config_hash = metadata.compute_config_hash(config)
        return metadata

    def store_result(
        self,
        result: BacktestResult,
        metadata: Optional[RunMetadata] = None,
    ) -> str:
        """Store a backtest result. Returns the run_id."""
        self._results[result.run_id] = result
        if metadata:
            self._metadata[result.run_id] = metadata
        else:
            self._metadata[result.run_id] = RunMetadata(
                run_id=result.run_id,
                config_hash=self._hash_config(result.config.model_dump()),
            )

        logger.info(
            "Result stored: run_id=%s status=%s trades=%d",
            result.run_id,
            result.status.value,
            len(result.trades),
        )
        return result.run_id

    def get_result(self, run_id: str) -> Optional[BacktestResult]:
        """Get a backtest result by run ID."""
        return self._results.get(run_id)

    def get_metadata(self, run_id: str) -> Optional[RunMetadata]:
        """Get run metadata by run ID."""
        return self._metadata.get(run_id)

    def list_runs(
        self,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> list[dict]:
        """List recent backtest runs."""
        runs = []
        for run_id, result in self._results.items():
            if status and result.status.value != status:
                continue
            meta = self._metadata.get(run_id)
            runs.append({
                "run_id": run_id,
                "status": result.status.value,
                "trades": len(result.trades),
                "created_at": meta.created_at.isoformat() if meta else None,
                "config_hash": meta.config_hash if meta else None,
                "description": meta.description if meta else "",
                "tags": meta.tags if meta else [],
                "net_profit": result.metrics.net_profit if result.metrics else None,
            })

        # Sort by created_at descending
        runs.sort(
            key=lambda r: r["created_at"] or "1970-01-01",
            reverse=True,
        )
        return runs[:limit]

    def compare_runs(
        self,
        run_id_a: str,
        run_id_b: str,
    ) -> Optional[dict]:
        """Compare two backtest runs."""
        result_a = self._results.get(run_id_a)
        result_b = self._results.get(run_id_b)

        if result_a is None or result_b is None:
            return None

        metrics_a = result_a.metrics
        metrics_b = result_b.metrics

        if metrics_a is None or metrics_b is None:
            return {
                "run_a": run_id_a,
                "run_b": run_id_b,
                "comparison": "incomplete",
            }

        return {
            "run_a": run_id_a,
            "run_b": run_id_b,
            "comparison": {
                "trades": {
                    "a": metrics_a.trade_stats.total_trades,
                    "b": metrics_b.trade_stats.total_trades,
                    "delta": metrics_b.trade_stats.total_trades - metrics_a.trade_stats.total_trades,
                },
                "win_rate": {
                    "a": metrics_a.trade_stats.win_rate,
                    "b": metrics_b.trade_stats.win_rate,
                    "delta": metrics_b.trade_stats.win_rate - metrics_a.trade_stats.win_rate,
                },
                "net_profit": {
                    "a": metrics_a.net_profit,
                    "b": metrics_b.net_profit,
                    "delta": metrics_b.net_profit - metrics_a.net_profit,
                },
                "sharpe_ratio": {
                    "a": metrics_a.risk_metrics.sharpe_ratio,
                    "b": metrics_b.risk_metrics.sharpe_ratio,
                    "delta": metrics_b.risk_metrics.sharpe_ratio - metrics_a.risk_metrics.sharpe_ratio,
                },
                "max_drawdown_pct": {
                    "a": metrics_a.risk_metrics.max_drawdown_pct,
                    "b": metrics_b.risk_metrics.max_drawdown_pct,
                    "delta": metrics_b.risk_metrics.max_drawdown_pct - metrics_a.risk_metrics.max_drawdown_pct,
                },
                "profit_factor": {
                    "a": metrics_a.trade_stats.profit_factor,
                    "b": metrics_b.trade_stats.profit_factor,
                    "delta": metrics_b.trade_stats.profit_factor - metrics_a.trade_stats.profit_factor,
                },
            },
        }

    def delete_result(self, run_id: str) -> bool:
        """Delete a stored result."""
        if run_id in self._results:
            del self._results[run_id]
            self._metadata.pop(run_id, None)
            return True
        return False

    def clear_old_results(self, max_age_seconds: Optional[int] = None) -> int:
        """Clear results older than max_age_seconds. Returns count deleted."""
        ttl = max_age_seconds or self._settings.result_ttl_seconds
        now = datetime.now(timezone.utc)
        to_delete: list[str] = []

        for run_id, meta in self._metadata.items():
            age = (now - meta.created_at).total_seconds()
            if age > ttl:
                to_delete.append(run_id)

        for run_id in to_delete:
            self.delete_result(run_id)

        return len(to_delete)

    @property
    def total_stored(self) -> int:
        return len(self._results)

    def summary(self) -> dict:
        """Return summary of version manager state."""
        return {
            "total_stored": self.total_stored,
            "runs": self.list_runs(limit=10),
        }

    @staticmethod
    def _hash_config(config: dict[str, Any]) -> str:
        """Compute deterministic hash of configuration."""
        config_str = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]
