"use client";

import { useEffect, useState } from "react";
import {
  fetchStrategiesEvaluateAll,
  type StrategyEvaluationResponse,
  type EvaluateAllResponse,
} from "@/lib/strategiesApi";

type Status = "loading" | "ok" | "error";

export default function StrategyEvaluationStatus() {
  const [data, setData] = useState<EvaluateAllResponse | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const res = await fetchStrategiesEvaluateAll("XAU/USD", ["1m", "5m", "15m"], 300);
      if (cancelled) return;

      if (res.ok && res.data) {
        setData(res.data);
        setStatus("ok");
      } else {
        setError(res.error || "Failed to evaluate strategies");
        setStatus("error");
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  const statusColor = (s: string) =>
    s === "qualified" ? "var(--color-accent)" :
    s === "not_qualified" ? "var(--color-warning)" :
    s === "not_applicable" ? "var(--color-text-muted)" :
    s === "invalidated" ? "var(--color-error)" :
    "var(--color-checking)";

  const directionColor = (d: string) =>
    d === "bullish" ? "var(--color-accent)" :
    d === "bearish" ? "var(--color-error)" :
    "var(--color-text-muted)";

  const conditionStatusColor = (s: string) =>
    s === "passed" ? "var(--color-accent)" :
    s === "failed" ? "var(--color-error)" :
    "var(--color-checking)";

  const critBadge = (c: string) =>
    c === "critical" ? "crit" :
    c === "required" ? "req" :
    "opt";

  const critBadgeColor = (c: string) =>
    c === "critical" ? "var(--color-error)" :
    c === "required" ? "var(--color-warning)" :
    "var(--color-text-muted)";

  return (
    <div className="tf-card">
      <h2 className="tf-title">Strategy Evaluation Engine</h2>

      {status === "loading" && (
        <div className="tf-loading">Evaluating strategies...</div>
      )}

      {error && (
        <div className="tf-error">
          <span className="tf-error-key">Error</span>
          <span className="tf-error-value">{error}</span>
        </div>
      )}

      {data && (
        <div className="tf-grid">
          <div className="tf-row">
            <span className="tf-key">Strategies Evaluated</span>
            <span className="tf-value">{data.count}</span>
          </div>

          {data.evaluations.map((ev) => (
            <StrategyCard
              key={ev.evaluation_id}
              evaluation={ev}
              statusColor={statusColor}
              directionColor={directionColor}
              conditionStatusColor={conditionStatusColor}
              critBadge={critBadge}
              critBadgeColor={critBadgeColor}
            />
          ))}
        </div>
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
        .tf-reason {
          padding: 0.4rem 0;
        }
        .tf-reason-text {
          font-size: 0.75rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .tf-divider {
          height: 1px;
          background: var(--color-border);
          margin: 0.3rem 0;
        }
        .tf-section {
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--color-text-muted);
          padding: 0.2rem 0;
        }
        .tf-warning {
          font-size: 0.7rem;
          color: var(--color-warning);
          font-family: var(--font-mono);
          padding: 0.2rem 0;
        }
      `}</style>
    </div>
  );
}

function StrategyCard({
  evaluation: ev,
  statusColor,
  directionColor,
  conditionStatusColor,
  critBadge,
  critBadgeColor,
}: {
  evaluation: StrategyEvaluationResponse;
  statusColor: (s: string) => string;
  directionColor: (d: string) => string;
  conditionStatusColor: (s: string) => string;
  critBadge: (c: string) => string;
  critBadgeColor: (c: string) => string;
}) {
  return (
    <div className="strat-card">
      <div className="tf-divider" />
      <div className="tf-row">
        <span className="tf-key">{ev.strategy_name}</span>
        <span className="tf-value" style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}>
          v{ev.strategy_version}
        </span>
      </div>

      <div className="tf-row">
        <span className="tf-key">Status</span>
        <span className="tf-value" style={{ color: statusColor(ev.status) }}>
          {ev.status.toUpperCase().replace("_", " ")}
        </span>
      </div>

      <div className="tf-row">
        <span className="tf-key">Direction</span>
        <span className="tf-value" style={{ color: directionColor(ev.direction) }}>
          {ev.direction.toUpperCase()}
        </span>
      </div>

      {ev.market_regime && (
        <div className="tf-row">
          <span className="tf-key">Regime</span>
          <span className="tf-value">{ev.market_regime}</span>
        </div>
      )}

      {ev.source_types_used && ev.source_types_used.length > 0 && (
        <div className="tf-row">
          <span className="tf-key">Source</span>
          <span className="tf-value">{ev.source_types_used.join(", ")}</span>
        </div>
      )}

      {ev.quality_score && (
        <div className="tf-row">
          <span className="tf-key">Quality</span>
          <span className="tf-value">
            {ev.quality_score.score}/{ev.quality_score.max_score}
            <span style={{ color: "var(--color-text-muted)", fontSize: "0.7rem" }}>
              {" "}({(ev.quality_score.normalized_score * 100).toFixed(0)}%)
            </span>
          </span>
        </div>
      )}

      {ev.eligibility && !ev.eligibility.eligible && (
        <div className="tf-reason">
          <span className="tf-reason-text">
            Blocked: {ev.eligibility.blocked_by}
          </span>
        </div>
      )}

      {ev.condition_results && ev.condition_results.length > 0 && (
        <>
          <div className="tf-section">Conditions</div>
          {ev.condition_results.map((cr) => (
            <div key={cr.condition_id} className="tf-row" style={{ gap: "0.5rem" }}>
              <span className="tf-key" style={{ flex: 1, fontSize: "0.7rem" }}>
                {cr.condition_name}
                <span style={{ color: critBadgeColor(cr.criticality), marginLeft: "0.3rem", fontSize: "0.6rem" }}>
                  [{critBadge(cr.criticality)}]
                </span>
              </span>
              <span className="tf-value" style={{ color: conditionStatusColor(cr.status), fontSize: "0.75rem" }}>
                {cr.status}
              </span>
            </div>
          ))}
        </>
      )}

      {ev.invalidation_results && ev.invalidation_results.some((ir) => ir.triggered) && (
        <>
          <div className="tf-section">Invalidation</div>
          {ev.invalidation_results.filter((ir) => ir.triggered).map((ir) => (
            <div key={ir.rule_id} className="tf-warning">
              {ir.rule_name}: {ir.reason}
            </div>
          ))}
        </>
      )}

      {ev.reason && (
        <div className="tf-reason">
          <span className="tf-reason-text">{ev.reason}</span>
        </div>
      )}

      <style jsx>{`
        .strat-card {
          padding: 0.5rem 0;
        }
        .tf-divider {
          height: 1px;
          background: var(--color-border);
          margin: 0.3rem 0;
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
        .tf-reason {
          padding: 0.4rem 0;
        }
        .tf-reason-text {
          font-size: 0.75rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .tf-section {
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--color-text-muted);
          padding: 0.2rem 0;
        }
        .tf-warning {
          font-size: 0.7rem;
          color: var(--color-error);
          font-family: var(--font-mono);
          padding: 0.2rem 0;
        }
      `}</style>
    </div>
  );
}
