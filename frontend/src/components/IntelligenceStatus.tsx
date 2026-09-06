"use client";

/**
 * Scalping Arise — Intelligence Status Component
 *
 * Displays Phase 8 intelligence state: event risk, strategy performance,
 * and unified decision. Inline styles with CSS variables — no Tailwind dependency.
 */

import { useEffect, useState } from "react";
import {
  evaluateIntelligence,
  getStrategyState,
  getMetrics,
  type IntelligenceEvaluation,
  type StrategyState,
  type StrategyMetrics,
} from "@/lib/intelligenceApi";

interface IntelligenceStatusProps {
  instrument: string;
  strategyId?: string;
}

export default function IntelligenceStatus({
  instrument,
  strategyId,
}: IntelligenceStatusProps) {
  const [evaluation, setEvaluation] = useState<IntelligenceEvaluation | null>(null);
  const [strategyState, setStrategyState] = useState<StrategyState | null>(null);
  const [metrics, setMetrics] = useState<StrategyMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        setLoading(true);
        setError(null);

        const evalResult = await evaluateIntelligence(instrument, undefined, strategyId);
        if (!cancelled) setEvaluation(evalResult);

        if (strategyId) {
          const [stateResult, metricsResult] = await Promise.all([
            getStrategyState(strategyId),
            getMetrics(strategyId),
          ]);
          if (!cancelled) {
            setStrategyState(stateResult);
            setMetrics(metricsResult);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to fetch intelligence");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    const interval = setInterval(fetchData, 30_000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [instrument, strategyId]);

  const decisionColor =
    evaluation?.overall_decision === "allow"
      ? "var(--color-accent)"
      : evaluation?.overall_decision === "restrict"
        ? "var(--color-warning)"
        : "var(--color-error)";

  const decisionBg =
    evaluation?.overall_decision === "allow"
      ? "rgba(34,197,94,0.08)"
      : evaluation?.overall_decision === "restrict"
        ? "rgba(234,179,8,0.08)"
        : "rgba(239,68,68,0.08)";

  const strategyStateColor = (s: string) =>
    s === "active" ? "var(--color-accent)"
      : s === "monitored" ? "var(--color-warning)"
        : s === "restricted" ? "#fb923c"
          : "var(--color-error)";

  return (
    <div className="intel-card">
      {loading && !evaluation && (
        <div className="intel-loading">
          <span className="intel-loading-dot" />
          <span>Loading intelligence...</span>
        </div>
      )}

      {error && (
        <div className="intel-error">
          <span style={{ color: "var(--color-error)", fontSize: "0.85rem" }}>
            Error: {error}
          </span>
        </div>
      )}

      {evaluation && (
        <>
          {/* Header */}
          <div className="intel-header">
            <span className="intel-title">Intelligence</span>
            <span className="intel-instrument">{instrument}</span>
          </div>

          {/* Decision Badge */}
          <div
            className="intel-decision"
            style={{ background: decisionBg, borderColor: decisionColor }}
          >
            <span className="intel-decision-text" style={{ color: decisionColor }}>
              {evaluation.overall_decision.toUpperCase()}
            </span>
            {evaluation.overall_decision !== "allow" && (
              <span className="intel-decision-count">
                ({evaluation.reasons.length} reason{evaluation.reasons.length !== 1 ? "s" : ""})
              </span>
            )}
          </div>

          {/* Event Summary */}
          {evaluation.event_context_summary && (
            <div className="intel-grid-3">
              <div className="intel-stat">
                <span className="intel-stat-label">Events</span>
                <span className="intel-stat-value">
                  {evaluation.event_context_summary.total_events}
                </span>
              </div>
              <div className="intel-stat">
                <span className="intel-stat-label">Relevant</span>
                <span className="intel-stat-value">
                  {evaluation.event_context_summary.relevant_events}
                </span>
              </div>
              <div className="intel-stat">
                <span className="intel-stat-label">High Impact</span>
                <span className="intel-stat-value">
                  {evaluation.event_context_summary.high_impact_events}
                </span>
              </div>
            </div>
          )}

          {/* Strategy State */}
          {strategyState && (
            <div className="intel-section">
              <div className="intel-row">
                <span className="intel-key">Strategy State</span>
                <span
                  className="intel-value"
                  style={{ color: strategyStateColor(strategyState.state), fontWeight: 600 }}
                >
                  {strategyState.state.toUpperCase()}
                </span>
              </div>
              <div className="intel-row">
                <span className="intel-key">Sample Size</span>
                <span className="intel-value">{strategyState.sample_size}</span>
              </div>
              {strategyState.state_reasons.length > 0 && (
                <div className="intel-reasons">
                  {strategyState.state_reasons.slice(0, 2).map((reason, i) => (
                    <div key={i} className="intel-reason-row">
                      <span className="intel-reason-bullet">&middot;</span>
                      <span>{reason}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Performance Metrics */}
          {metrics && metrics.total_trades > 0 && (
            <div className="intel-section">
              <div className="intel-grid-2">
                <div className="intel-row">
                  <span className="intel-key">Win Rate</span>
                  <span className="intel-value">
                    {(metrics.win_rate * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="intel-row">
                  <span className="intel-key">Net P&amp;L</span>
                  <span
                    className="intel-value"
                    style={{ color: metrics.net_pnl >= 0 ? "var(--color-accent)" : "var(--color-error)" }}
                  >
                    {metrics.net_pnl.toFixed(2)}
                  </span>
                </div>
                <div className="intel-row">
                  <span className="intel-key">Profit Factor</span>
                  <span className="intel-value">{metrics.profit_factor.toFixed(2)}</span>
                </div>
                <div className="intel-row">
                  <span className="intel-key">Max Drawdown</span>
                  <span className="intel-value">{metrics.max_drawdown.toFixed(1)}%</span>
                </div>
              </div>
            </div>
          )}

          {/* Restrictions */}
          {evaluation.restrictions.length > 0 && (
            <div className="intel-section">
              {evaluation.restrictions.map((restriction, i) => (
                <div key={i} className="intel-restriction">
                  <span>&#9888;</span>
                  <span>{restriction}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <style jsx>{`
        .intel-card {
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: 12px;
          padding: 1.5rem;
          width: 100%;
          max-width: 520px;
        }
        .intel-loading {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          color: var(--color-text-muted);
          font-size: 0.85rem;
          padding: 1rem 0;
        }
        .intel-loading-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--color-text-muted);
          animation: pulse 1.5s ease-in-out infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
        .intel-error {
          padding: 0.5rem 0;
        }
        .intel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 1rem;
        }
        .intel-title {
          font-size: 1rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--color-text);
        }
        .intel-instrument {
          font-size: 0.75rem;
          color: var(--color-text-muted);
        }
        .intel-decision {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.6rem 0.75rem;
          border-radius: 8px;
          border: 1px solid;
          margin-bottom: 0.75rem;
        }
        .intel-decision-text {
          font-size: 1.1rem;
          font-weight: 700;
          text-transform: uppercase;
        }
        .intel-decision-count {
          font-size: 0.75rem;
          color: var(--color-text-muted);
        }
        .intel-grid-3 {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 0.5rem;
          text-align: center;
        }
        .intel-grid-2 {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 0.5rem;
        }
        .intel-stat {
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
        }
        .intel-stat-label {
          font-size: 0.75rem;
          color: var(--color-text-muted);
        }
        .intel-stat-value {
          font-size: 0.85rem;
          font-weight: 600;
          font-family: var(--font-mono);
          color: var(--color-text);
        }
        .intel-section {
          border-top: 1px solid var(--color-border);
          padding-top: 0.75rem;
          margin-top: 0.75rem;
        }
        .intel-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.15rem 0;
        }
        .intel-key {
          font-size: 0.75rem;
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .intel-value {
          font-size: 0.85rem;
          font-family: var(--font-mono);
          color: var(--color-text);
        }
        .intel-reasons {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
          margin-top: 0.5rem;
        }
        .intel-reason-row {
          display: flex;
          align-items: flex-start;
          gap: 0.25rem;
          font-size: 0.75rem;
          color: var(--color-text-muted);
        }
        .intel-reason-bullet {
          color: var(--color-border);
        }
        .intel-restriction {
          display: flex;
          align-items: flex-start;
          gap: 0.35rem;
          font-size: 0.75rem;
          color: var(--color-warning);
          padding: 0.15rem 0;
        }
      `}</style>
    </div>
  );
}
