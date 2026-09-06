"use client";

import { useEffect, useState } from "react";
import {
  getHealth,
  getActiveDecisions,
  getCounters,
  getEmergencyStatus,
  toggleEmergency,
  type FinalDecision,
  type DecisionSummary,
  type MonitoringCounters,
  type EmergencyStatus,
} from "@/lib/decisionApi";

type Status = "loading" | "ok" | "error";

export default function DecisionStatus() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [active, setActive] = useState<DecisionSummary[]>([]);
  const [counters, setCounters] = useState<MonitoringCounters | null>(null);
  const [emergency, setEmergency] = useState<EmergencyStatus | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const hRes = await getHealth();
        if (!cancelled) setHealth(hRes);

        const aRes = await getActiveDecisions();
        if (!cancelled) setActive(aRes.decisions);

        const cRes = await getCounters();
        if (!cancelled) setCounters(cRes);

        const eRes = await getEmergencyStatus();
        if (!cancelled) setEmergency(eRes);

        if (!cancelled) setStatus("ok");
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.message || "Failed to fetch decision engine status");
          setStatus("error");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleEmergencyToggle = async () => {
    if (!emergency) return;
    try {
      const res = await toggleEmergency(
        !emergency.disabled,
        "Manual toggle from dashboard",
      );
      setEmergency({
        disabled: res.emergency_disable,
        toggled_at: res.toggled_at || new Date().toISOString(),
        toggle_count: (emergency?.toggle_count || 0) + 1,
        last_reason: "Manual toggle from dashboard",
      });
    } catch (e) {
      console.error("Emergency toggle failed:", e);
    }
  };

  const stateColor = (s: string) =>
    s === "actionable"
      ? "var(--color-accent)"
      : s === "blocked"
        ? "var(--color-error)"
        : s === "no_trade"
          ? "var(--color-text-muted)"
          : s === "expired" || s === "invalidated"
            ? "var(--color-checking)"
            : "var(--color-text-muted)";

  return (
    <div className="tf-card">
      <h2 className="tf-title">Decision Engine</h2>

      {status === "loading" && (
        <div className="tf-loading">Loading decision engine status...</div>
      )}

      {error && (
        <div className="tf-error">
          <span className="tf-error-key">Error</span>
          <span className="tf-error-value">{error}</span>
        </div>
      )}

      {status === "ok" && health && (
        <>
          {/* Health summary */}
          <div className="tf-row">
            <span className="tf-label">Module</span>
            <span className="tf-value">{(health as any).module || "decision_engine"}</span>
          </div>
          <div className="tf-row">
            <span className="tf-label">Version</span>
            <span className="tf-value">{(health as any).version || "10.0.0"}</span>
          </div>
          <div className="tf-row">
            <span className="tf-label">Status</span>
            <span
              className="tf-value"
              style={{ color: (health as any).status === "healthy" ? "var(--color-accent)" : "var(--color-error)" }}
            >
              {(health as any).status || "unknown"}
            </span>
          </div>
          <div className="tf-row">
            <span className="tf-label">History</span>
            <span className="tf-value">{(health as any).history_size || 0} entries</span>
          </div>
          <div className="tf-row">
            <span className="tf-label">Active</span>
            <span className="tf-value">{(health as any).active_size || 0} decisions</span>
          </div>
          <div className="tf-row">
            <span className="tf-label">Audit Trail</span>
            <span className="tf-value">{(health as any).audit_size || 0} entries</span>
          </div>

          {/* Emergency control */}
          {emergency && (
            <div className="tf-section">
              <h3 className="tf-subtitle">Emergency Control</h3>
              <div className="tf-row">
                <span className="tf-label">State</span>
                <span
                  className="tf-value"
                  style={{ color: emergency.disabled ? "var(--color-error)" : "var(--color-accent)" }}
                >
                  {emergency.disabled ? "DISABLED" : "ACTIVE"}
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-label">Toggles</span>
                <span className="tf-value">{emergency.toggle_count}</span>
              </div>
              {emergency.toggled_at && (
                <div className="tf-row">
                  <span className="tf-label">Last Toggle</span>
                  <span className="tf-value">
                    {new Date(emergency.toggled_at).toLocaleTimeString()}
                  </span>
                </div>
              )}
              <button
                className="tf-button"
                onClick={handleEmergencyToggle}
                style={{
                  backgroundColor: emergency.disabled ? "var(--color-accent)" : "var(--color-error)",
                  color: "white",
                  border: "none",
                  padding: "6px 12px",
                  borderRadius: "4px",
                  cursor: "pointer",
                  marginTop: "8px",
                }}
              >
                {emergency.disabled ? "Enable Trading" : "Emergency Disable"}
              </button>
            </div>
          )}

          {/* Monitoring counters */}
          {counters && (
            <div className="tf-section">
              <h3 className="tf-subtitle">Monitoring</h3>
              <div className="tf-row">
                <span className="tf-label">Total Evaluations</span>
                <span className="tf-value">{counters.total_evaluations}</span>
              </div>
              <div className="tf-row">
                <span className="tf-label">Actionable</span>
                <span className="tf-value" style={{ color: "var(--color-accent)" }}>
                  {counters.actionable_decisions}
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-label">No Trade</span>
                <span className="tf-value">{counters.no_trade_decisions}</span>
              </div>
              <div className="tf-row">
                <span className="tf-label">Blocked</span>
                <span className="tf-value" style={{ color: "var(--color-error)" }}>
                  {counters.blocked_decisions}
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-label">Avg Eval Time</span>
                <span className="tf-value">{counters.avg_evaluation_ms.toFixed(1)}ms</span>
              </div>
              <div className="tf-row">
                <span className="tf-label">Idempotency Hits</span>
                <span className="tf-value">{counters.idempotency_cache_hits}</span>
              </div>
            </div>
          )}

          {/* Active decisions */}
          {active.length > 0 && (
            <div className="tf-section">
              <h3 className="tf-subtitle">Active Decisions</h3>
              {active.map((d) => (
                <div
                  key={d.decision_id}
                  className="tf-row"
                  style={{ borderBottom: "1px solid var(--color-border)", paddingBottom: "4px", marginBottom: "4px" }}
                >
                  <span className="tf-label">
                    {d.signal_id ? d.signal_id.slice(0, 8) : d.decision_id.slice(0, 8)}
                  </span>
                  <span className="tf-value" style={{ color: stateColor(d.state) }}>
                    {d.state.toUpperCase()} {d.direction !== "none" ? `(${d.direction.toUpperCase()})` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <footer className="tf-footer">
        Phase 10 — Final Decision, Explainability & Production Readiness
      </footer>
    </div>
  );
}
