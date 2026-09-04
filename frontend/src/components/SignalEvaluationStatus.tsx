"use client";

import { useEffect, useState } from "react";
import {
  fetchSignalsEvaluate,
  type SignalEvaluationResponse,
} from "@/lib/signalsApi";

type Status = "loading" | "ok" | "error";

export default function SignalEvaluationStatus() {
  const [data, setData] = useState<SignalEvaluationResponse | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const res = await fetchSignalsEvaluate("XAU/USD", ["1m", "5m", "15m"], 300);
      if (cancelled) return;

      if (res.ok && res.data) {
        setData(res.data);
        setStatus("ok");
      } else {
        setError(res.error || "Failed to evaluate signal");
        setStatus("error");
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  const statusColor = (s: string) =>
    s === "qualified" ? "var(--color-accent)" :
    s === "rejected" ? "var(--color-error)" :
    s === "conflict" ? "var(--color-warning)" :
    "var(--color-text-muted)";

  const directionColor = (d: string) =>
    d === "long" ? "var(--color-accent)" :
    d === "short" ? "var(--color-error)" :
    "var(--color-text-muted)";

  const levelColor = (l: string) =>
    l === "strong" ? "var(--color-accent)" :
    l === "moderate" ? "var(--color-warning)" :
    l === "weak" ? "var(--color-text-muted)" :
    "var(--color-text-muted)";

  return (
    <div className="tf-card">
      <h2 className="tf-title">Signal Engine</h2>

      {status === "loading" && (
        <div className="tf-loading">Evaluating signal...</div>
      )}

      {error && (
        <div className="tf-error">
          <span className="tf-error-key">Error</span>
          <span className="tf-error-value">{error}</span>
        </div>
      )}

      {data && (
        <div className="tf-grid">
          {/* Status & Direction */}
          <div className="tf-row">
            <span className="tf-key">Status</span>
            <span className="tf-value" style={{ color: statusColor(data.status) }}>
              {data.status.toUpperCase().replace("_", " ")}
            </span>
          </div>

          <div className="tf-row">
            <span className="tf-key">Direction</span>
            <span className="tf-value" style={{ color: directionColor(data.direction) }}>
              {data.direction.toUpperCase()}
            </span>
          </div>

          {/* Confidence */}
          {data.confidence && (
            <>
              <div className="tf-section">Confidence</div>
              <div className="tf-row">
                <span className="tf-key">Overall</span>
                <span className="tf-value">
                  {(data.confidence.overall * 100).toFixed(0)}%
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Strategy</span>
                <span className="tf-value" style={{ fontSize: "0.75rem" }}>
                  {(data.confidence.strategy_alignment * 100).toFixed(0)}%
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">MTF</span>
                <span className="tf-value" style={{ fontSize: "0.75rem" }}>
                  {(data.confidence.mtf_confirmation * 100).toFixed(0)}%
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Evidence</span>
                <span className="tf-value" style={{ fontSize: "0.75rem" }}>
                  {(data.confidence.evidence_strength * 100).toFixed(0)}%
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Regime</span>
                <span className="tf-value" style={{ fontSize: "0.75rem" }}>
                  {(data.confidence.regime_consistency * 100).toFixed(0)}%
                </span>
              </div>
            </>
          )}

          {/* Candidates */}
          {data.candidates && data.candidates.length > 0 && (
            <>
              <div className="tf-section">Candidates ({data.candidates.length})</div>
              {data.candidates.map((c) => (
                <div key={c.strategy_id} className="tf-row">
                  <span className="tf-key" style={{ fontSize: "0.7rem" }}>
                    {c.strategy_name}
                  </span>
                  <span className="tf-value" style={{ color: directionColor(c.direction), fontSize: "0.7rem" }}>
                    {c.direction.toUpperCase()} ({(c.quality_score_normalized * 100).toFixed(0)}%)
                  </span>
                </div>
              ))}
            </>
          )}

          {/* MTF Confirmation */}
          {data.mtf_confirmation && (
            <>
              <div className="tf-section">MTF Confirmation</div>
              <div className="tf-row">
                <span className="tf-key">Confirmed</span>
                <span className="tf-value" style={{ color: data.mtf_confirmation.confirmed ? "var(--color-accent)" : "var(--color-error)" }}>
                  {data.mtf_confirmation.confirmed ? "YES" : "NO"} ({data.mtf_confirmation.aligned_count}/{data.mtf_confirmation.total_count})
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Level</span>
                <span className="tf-value" style={{ color: levelColor(data.mtf_confirmation.confirmation_level) }}>
                  {data.mtf_confirmation.confirmation_level.toUpperCase()}
                </span>
              </div>
            </>
          )}

          {/* Conflicts */}
          {data.conflicts && data.conflicts.length > 0 && (
            <>
              <div className="tf-section">Conflicts</div>
              {data.conflicts.map((c, i) => (
                <div key={i} className="tf-warning">
                  {c.description}
                </div>
              ))}
            </>
          )}

          {/* Reason */}
          {data.reason && (
            <div className="tf-reason">
              <span className="tf-reason-text">{data.reason}</span>
            </div>
          )}
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
