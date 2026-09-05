"use client";

import { useEffect, useState } from "react";
import {
  generateTradePlan,
  fetchTradePlanningHealth,
  type TradePlan,
  type TradePlanningHealthResponse,
} from "@/lib/tradePlanningApi";

type Status = "loading" | "ok" | "error" | "no_trade" | "rejected";

export default function TradePlanStatus() {
  const [plan, setPlan] = useState<TradePlan | null>(null);
  const [health, setHealth] = useState<TradePlanningHealthResponse | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      // Fetch health first
      const hRes = await fetchTradePlanningHealth();
      if (!cancelled && hRes.ok && hRes.data) {
        setHealth(hRes.data);
      }

      // Generate a plan from the latest signal
      const pRes = await generateTradePlan({
        instrument: "XAU/USD",
        timeframes: ["1m", "5m", "15m"],
        limit: 300,
      });

      if (cancelled) return;

      if (pRes.ok && pRes.data) {
        const p = pRes.data;
        setPlan(p);
        if (p.state === "approved") setStatus("ok");
        else if (p.state === "rejected") setStatus("rejected");
        else if (p.rejection_reason?.includes("no_trade")) setStatus("no_trade");
        else setStatus("ok");
      } else {
        setError(pRes.error || "Failed to generate trade plan");
        setStatus("error");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const stateColor = (s: string) =>
    s === "approved"
      ? "var(--color-accent)"
      : s === "rejected" || s === "invalidated"
        ? "var(--color-error)"
        : s === "expired"
          ? "var(--color-warning)"
          : s === "validated"
            ? "#60a5fa"
            : "var(--color-text-muted)";

  const sideColor = (s: string) =>
    s === "long" ? "var(--color-accent)" : s === "short" ? "var(--color-error)" : "var(--color-text-muted)";

  const entryColor = (s: string) =>
    s === "entry_ready" ? "var(--color-accent)" : s === "wait_for_entry" ? "var(--color-warning)" : "var(--color-text-muted)";

  return (
    <div className="tf-card">
      <h2 className="tf-title">Trade Planning</h2>

      {status === "loading" && (
        <div className="tf-loading">Generating trade plan...</div>
      )}

      {error && (
        <div className="tf-error">
          <span className="tf-error-key">Error</span>
          <span className="tf-error-value">{error}</span>
        </div>
      )}

      {/* No-trade signal */}
      {status === "no_trade" && !error && (
        <div className="tf-grid">
          <div className="tf-row">
            <span className="tf-key">Status</span>
            <span className="tf-value" style={{ color: "var(--color-warning)" }}>
              NO TRADE
            </span>
          </div>
          <div className="tf-reason">
            <span className="tf-reason-text">
              Signal engine returned NO_TRADE — no plan generated.
            </span>
          </div>
        </div>
      )}

      {/* Rejected plan */}
      {plan && status === "rejected" && (
        <div className="tf-grid">
          <div className="tf-row">
            <span className="tf-key">Status</span>
            <span className="tf-value" style={{ color: stateColor(plan.state) }}>
              {plan.state.toUpperCase()}
            </span>
          </div>
          <div className="tf-row">
            <span className="tf-key">Instrument</span>
            <span className="tf-value">{plan.instrument}</span>
          </div>
          <div className="tf-row">
            <span className="tf-key">Side</span>
            <span className="tf-value" style={{ color: sideColor(plan.side) }}>
              {plan.side.toUpperCase()}
            </span>
          </div>
          {plan.rejection_reason && (
            <div className="tf-reason">
              <span className="tf-reason-text">{plan.rejection_reason}</span>
            </div>
          )}
        </div>
      )}

      {/* Approved plan */}
      {plan && status === "ok" && (
        <div className="tf-grid">
          {/* State & Side */}
          <div className="tf-row">
            <span className="tf-key">State</span>
            <span className="tf-value" style={{ color: stateColor(plan.state) }}>
              {plan.state.toUpperCase()}
            </span>
          </div>
          <div className="tf-row">
            <span className="tf-key">Side</span>
            <span className="tf-value" style={{ color: sideColor(plan.side) }}>
              {plan.side.toUpperCase()}
            </span>
          </div>
          <div className="tf-row">
            <span className="tf-key">Instrument</span>
            <span className="tf-value">{plan.instrument}</span>
          </div>

          {/* Entry */}
          {plan.entry && (
            <>
              <div className="tf-section">Entry</div>
              <div className="tf-row">
                <span className="tf-key">Type</span>
                <span className="tf-value">{plan.entry.type.toUpperCase()}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">State</span>
                <span
                  className="tf-value"
                  style={{ color: entryColor(plan.entry.state) }}
                >
                  {plan.entry.state.replace(/_/g, " ").toUpperCase()}
                </span>
              </div>
              {plan.entry.price != null && (
                <div className="tf-row">
                  <span className="tf-key">Price</span>
                  <span className="tf-value">{plan.entry.price.toFixed(2)}</span>
                </div>
              )}
              {plan.entry.spread_pips != null && (
                <div className="tf-row">
                  <span className="tf-key">Spread</span>
                  <span className="tf-value">{plan.entry.spread_pips.toFixed(1)} pips</span>
                </div>
              )}
              <div className="tf-row">
                <span className="tf-key">Reason</span>
                <span className="tf-value" style={{ fontSize: "0.7rem" }}>
                  {plan.entry.reason}
                </span>
              </div>
            </>
          )}

          {/* Stop Loss */}
          {plan.stop_loss && (
            <>
              <div className="tf-section">Stop Loss</div>
              <div className="tf-row">
                <span className="tf-key">Type</span>
                <span className="tf-value">{plan.stop_loss.type.toUpperCase()}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Price</span>
                <span className="tf-value">{plan.stop_loss.price.toFixed(2)}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Distance</span>
                <span className="tf-value">
                  {plan.stop_loss.distance_pips.toFixed(1)} pips
                </span>
              </div>
              {plan.stop_loss.atr_multiple != null && (
                <div className="tf-row">
                  <span className="tf-key">ATR ×</span>
                  <span className="tf-value">{plan.stop_loss.atr_multiple.toFixed(1)}</span>
                </div>
              )}
            </>
          )}

          {/* Take Profit */}
          {plan.take_profit && plan.take_profit.targets.length > 0 && (
            <>
              <div className="tf-section">
                Take Profit ({plan.take_profit.targets.length} targets)
              </div>
              {plan.take_profit.targets.map((t) => (
                <div key={t.label} className="tf-row">
                  <span className="tf-key" style={{ fontSize: "0.7rem" }}>
                    {t.label} ({t.rr_ratio.toFixed(1)}R)
                  </span>
                  <span className="tf-value" style={{ fontSize: "0.75rem" }}>
                    {t.distance_pips.toFixed(1)} pips
                    {t.partial_close_pct < 100 ? ` (${t.partial_close_pct}%)` : ""}
                  </span>
                </div>
              ))}
            </>
          )}

          {/* Risk & Position */}
          {plan.risk && (
            <>
              <div className="tf-section">Risk</div>
              <div className="tf-row">
                <span className="tf-key">Risk</span>
                <span className="tf-value">
                  {plan.risk.risk_pct.toFixed(2)}% (${plan.risk.risk_amount.toFixed(2)})
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">R:R</span>
                <span className="tf-value">
                  {plan.risk.risk_reward_ratio != null
                    ? `${plan.risk.risk_reward_ratio.toFixed(1)}:1`
                    : "—"}
                </span>
              </div>
              {plan.position_size && (
                <div className="tf-row">
                  <span className="tf-key">Size</span>
                  <span className="tf-value">
                    {plan.position_size.lots.toFixed(2)} lots
                    {plan.position_size.capped ? " (capped)" : ""}
                  </span>
                </div>
              )}
            </>
          )}

          {/* Cost */}
          {plan.cost && (
            <>
              <div className="tf-section">Cost</div>
              <div className="tf-row">
                <span className="tf-key">Total</span>
                <span className="tf-value">
                  ${plan.cost.total_cost.toFixed(2)} ({plan.cost.cost_pct_of_risk.toFixed(1)}% of risk)
                </span>
              </div>
            </>
          )}

          {/* Freshness & Price */}
          {plan.freshness && (
            <div className="tf-row">
              <span className="tf-key">Data Age</span>
              <span className="tf-value" style={{ color: plan.freshness.is_fresh ? "var(--color-accent)" : "var(--color-error)" }}>
                {plan.freshness.data_age_seconds.toFixed(0)}s
                {plan.freshness.is_fresh ? " ✓" : " stale"}
              </span>
            </div>
          )}

          {plan.price_tick && (
            <div className="tf-row">
              <span className="tf-key">Price</span>
              <span className="tf-value" style={{ color: plan.price_tick.valid ? "var(--color-accent)" : "var(--color-error)" }}>
                {plan.price_tick.valid ? "Valid" : "Invalid"}
                {plan.price_tick.stale ? " (stale)" : ""}
              </span>
            </div>
          )}

          {/* Rejection reason */}
          {plan.rejection_reason && (
            <div className="tf-reason">
              <span className="tf-reason-text">{plan.rejection_reason}</span>
            </div>
          )}
        </div>
      )}

      {/* Module health */}
      {health && (
        <div className="tf-health">
          <span className="tf-health-dot" style={{ background: health.status === "healthy" ? "var(--color-accent)" : "var(--color-warning)" }} />
          <span className="tf-health-text">
            {health.module} — {health.pipeline_steps.length} steps
          </span>
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
        .tf-section {
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--color-text-muted);
          padding: 0.2rem 0;
        }
        .tf-health {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          margin-top: 1rem;
          padding-top: 0.75rem;
          border-top: 1px solid var(--color-border);
        }
        .tf-health-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }
        .tf-health-text {
          font-size: 0.65rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
      `}</style>
    </div>
  );
}
