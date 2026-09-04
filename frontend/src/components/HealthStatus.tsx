"use client";

import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "@/lib/api";

type Status = "checking" | "connected" | "error";

export default function HealthStatus() {
  const [status, setStatus] = useState<Status>("checking");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      const result = await fetchHealth();
      if (cancelled) return;

      if (result.ok && result.data) {
        setHealth(result.data);
        setStatus("connected");
      } else {
        setErrorMessage(result.error || "Connection failed");
        setStatus("error");
      }
    }

    check();
    return () => {
      cancelled = true;
    };
  }, []);

  const statusColor =
    status === "connected"
      ? "var(--color-accent)"
      : status === "error"
        ? "var(--color-error)"
        : "var(--color-checking)";

  const statusLabel =
    status === "connected"
      ? "Connected"
      : status === "error"
        ? "Unavailable"
        : "Checking...";

  return (
    <div className="health-card">
      <div className="health-status-row">
        <span
          className="health-status-dot"
          style={{ backgroundColor: statusColor }}
        />
        <span className="health-status-label">Backend: {statusLabel}</span>
      </div>

      {health && (
        <div className="health-details">
          <div className="health-detail-row">
            <span className="health-detail-key">Service</span>
            <span className="health-detail-value">{health.service}</span>
          </div>
          <div className="health-detail-row">
            <span className="health-detail-key">Version</span>
            <span className="health-detail-value">{health.version}</span>
          </div>
          <div className="health-detail-row">
            <span className="health-detail-key">Environment</span>
            <span className="health-detail-value">{health.environment}</span>
          </div>
          <div className="health-detail-row">
            <span className="health-detail-key">Timestamp</span>
            <span className="health-detail-value">
              {new Date(health.timestamp).toLocaleTimeString()}
            </span>
          </div>
        </div>
      )}

      {errorMessage && (
        <div className="health-error">
          <span className="health-error-key">Error</span>
          <span className="health-error-value">{errorMessage}</span>
        </div>
      )}
    </div>
  );
}
