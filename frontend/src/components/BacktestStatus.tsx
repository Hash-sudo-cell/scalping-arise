"use client";

import { useEffect, useState } from "react";
import {
  fetchBacktestHealth,
  listBacktestRuns,
  type BacktestHealthResponse,
  type RunSummary,
} from "@/lib/backtestingApi";

type Status = "loading" | "ok" | "error";

export default function BacktestStatus() {
  const [health, setHealth] = useState<BacktestHealthResponse | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const hRes = await fetchBacktestHealth();
      if (!cancelled && hRes.ok && hRes.data) {
        setHealth(hRes.data);
      }

      const rRes = await listBacktestRuns(5);
      if (!cancelled && rRes.ok && rRes.data) {
        setRuns(rRes.data);
      }

      if (!cancelled) {
        if (hRes.ok) setStatus("ok");
        else {
          setError(hRes.error || "Failed to fetch backtest health");
          setStatus("error");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const statusColor = (s: string) =>
    s === "completed"
      ? "var(--color-accent)"
      : s === "failed"
        ? "var(--color-error)"
        : s === "running"
          ? "var(--color-checking)"
          : "var(--color-text-muted)";

  const formatPnl = (pnl: number | null) => {
    if (pnl === null) return "—";
    return pnl >= 0 ? `+$${pnl.toFixed(2)}` : `-$${Math.abs(pnl).toFixed(2)}`;
  };

  const pnlColor = (pnl: number | null) =>
    pnl === null
      ? "var(--color-text-muted)"
      : pnl >= 0
        ? "var(--color-accent)"
        : "var(--color-error)";

  return (
    <div className="tf-card">
      <h2 className="tf-title">Backtesting</h2>

      {status === "loading" && (
        <div className="tf-loading">Loading backtest status...</div>
      )}

      {error && (
        <div className="tf-error">
          <span className="tf-error-key">Error</span>
          <span className="tf-error-value">{error}</span>
        </div>
      )}

      {health && (
        <>
          {/* Health status */}
          <div className="tf-grid">
            <div className="tf-row">
              <span className="tf-key">Status</span>
              <span
                className="tf-value"
                style={{
                  color:
                    health.status === "healthy"
                      ? "var(--color-accent)"
                      : "var(--color-warning)",
                }}
              >
                {health.status.toUpperCase()}
              </span>
            </div>
            <div className="tf-row">
              <span className="tf-key">Results Stored</span>
              <span className="tf-value">{health.results_stored}</span>
            </div>
            <div className="tf-row">
              <span className="tf-key">Paper Sessions</span>
              <span className="tf-value">{health.paper_sessions}</span>
            </div>
            <div className="tf-row">
              <span className="tf-key">Determinism</span>
              <span
                className="tf-value"
                style={{
                  color: health.configuration.enforce_determinism
                    ? "var(--color-accent)"
                    : "var(--color-warning)",
                }}
              >
                {health.configuration.enforce_determinism ? "ENFORCED" : "OPTIONAL"}
              </span>
            </div>
            <div className="tf-row">
              <span className="tf-key">Look-Ahead</span>
              <span
                className="tf-value"
                style={{
                  color: health.configuration.strict_lookahead
                    ? "var(--color-accent)"
                    : "var(--color-warning)",
                }}
              >
                {health.configuration.strict_lookahead ? "STRICT" : "LENIENT"}
              </span>
            </div>
          </div>

          {/* Recent runs */}
          {runs.length > 0 && (
            <>
              <div className="tf-section">Recent Runs</div>
              <div className="tf-runs">
                {runs.map((run) => (
                  <div key={run.run_id} className="tf-run-row">
                    <div className="tf-run-header">
                      <span className="tf-run-instrument">
                        {run.instrument} {run.timeframe}
                      </span>
                      <span
                        className="tf-run-status"
                        style={{ color: statusColor(run.status) }}
                      >
                        {run.status.toUpperCase()}
                      </span>
                    </div>
                    <div className="tf-run-details">
                      <span className="tf-run-detail">
                        {run.candles_loaded} candles
                      </span>
                      <span className="tf-run-detail">
                        {run.trades_count} trades
                      </span>
                      {run.net_profit !== null && (
                        <span
                          className="tf-run-detail"
                          style={{ color: pnlColor(run.net_profit) }}
                        >
                          {formatPnl(run.net_profit)}
                        </span>
                      )}
                      {run.sharpe_ratio !== null && (
                        <span className="tf-run-detail">
                          Sharpe: {run.sharpe_ratio.toFixed(2)}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {runs.length === 0 && status === "ok" && (
            <div className="tf-empty">
              <span className="tf-empty-text">
                No backtest runs yet. Use the API to run a backtest.
              </span>
            </div>
          )}
        </>
      )}

      <style jsx>{`
        .tf-card {
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: 12px;
          padding: 1.5rem;
          width: 100%;
          max-width: 520px;
        }
        .tf-title {
          font-size: 1rem;
          font-weight: 600;
          margin-bottom: 1.25rem;
          color: var(--color-text);
        }
        .tf-loading {
          color: var(--color-text-muted);
          font-size: 0.85rem;
          padding: 1rem 0;
        }
        .tf-error {
          display: flex;
          justify-content: space-between;
          padding: 0.5rem 0;
        }
        .tf-error-key {
          font-size: 0.8rem;
          color: var(--color-error);
          text-transform: uppercase;
        }
        .tf-error-value {
          font-size: 0.8rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .tf-grid {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .tf-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .tf-key {
          font-size: 0.75rem;
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .tf-value {
          font-size: 0.85rem;
          font-family: var(--font-mono);
          color: var(--color-text);
        }
        .tf-section {
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--color-text-muted);
          padding: 0.75rem 0 0.25rem;
          border-top: 1px solid var(--color-border);
          margin-top: 0.75rem;
        }
        .tf-runs {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .tf-run-row {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid var(--color-border);
          border-radius: 8px;
          padding: 0.6rem 0.75rem;
        }
        .tf-run-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.3rem;
        }
        .tf-run-instrument {
          font-size: 0.8rem;
          font-weight: 600;
          color: var(--color-text);
          font-family: var(--font-mono);
        }
        .tf-run-status {
          font-size: 0.7rem;
          font-family: var(--font-mono);
          font-weight: 600;
        }
        .tf-run-details {
          display: flex;
          gap: 0.75rem;
          flex-wrap: wrap;
        }
        .tf-run-detail {
          font-size: 0.7rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .tf-empty {
          padding: 1rem 0;
          text-align: center;
        }
        .tf-empty-text {
          font-size: 0.8rem;
          color: var(--color-text-muted);
        }
      `}</style>
    </div>
  );
}
