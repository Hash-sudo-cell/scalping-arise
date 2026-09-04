"use client";

import { useEffect, useState } from "react";
import {
  fetchMarketDataHealth,
  fetchCapabilities,
  type MarketDataHealthResponse,
  type CapabilitiesResponse,
} from "@/lib/api";

type Status = "loading" | "ok" | "error";

export default function MarketDataStatus() {
  const [health, setHealth] = useState<MarketDataHealthResponse | null>(null);
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [healthRes, capsRes] = await Promise.all([
        fetchMarketDataHealth(),
        fetchCapabilities(),
      ]);

      if (cancelled) return;

      if (healthRes.ok && healthRes.data) {
        setHealth(healthRes.data);
        setStatus("ok");
      } else {
        setError(healthRes.error || "Failed to load market data status");
        setStatus("error");
      }

      if (capsRes.ok && capsRes.data) {
        setCaps(capsRes.data);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  const statusColor = (s: string) =>
    s === "healthy" ? "var(--color-accent)" :
    s === "degraded" ? "var(--color-warning)" :
    "var(--color-error)";

  const statusLabel = (s: string) =>
    s === "healthy" ? "Healthy" :
    s === "degraded" ? "Degraded" :
    "Unavailable";

  const capLabel = (c: string) =>
    c === "native" ? "Native" :
    c === "derived" ? "Derived" :
    "Unsupported";

  const capColor = (c: string) =>
    c === "native" ? "var(--color-accent)" :
    c === "derived" ? "var(--color-checking)" :
    "var(--color-text-muted)";

  return (
    <div className="md-card">
      <h2 className="md-title">Market Data System</h2>

      {status === "loading" && (
        <div className="md-loading">Loading market data status...</div>
      )}

      {error && (
        <div className="health-error">
          <span className="health-error-key">Error</span>
          <span className="health-error-value">{error}</span>
        </div>
      )}

      {health && (
        <div className="md-grid">
          {/* Overall Status */}
          <div className="md-row">
            <span className="md-key">Status</span>
            <span className="md-value" style={{ color: statusColor(health.status) }}>
              {statusLabel(health.status)}
            </span>
          </div>

          {/* Active Source */}
          <div className="md-row">
            <span className="md-key">Active Source</span>
            <span className="md-value">{health.active_source || "None"}</span>
          </div>

          {/* Source Identity — show when fallback is active */}
          {health.active_source === "yfinance" && caps?.fallback && (
            <div className="md-source-identity">
              <div className="md-row">
                <span className="md-key">Requested Market</span>
                <span className="md-value">{caps.fallback.canonical_instrument}</span>
              </div>
              <div className="md-row">
                <span className="md-key">Actual Data Source</span>
                <span className="md-value">{caps.fallback.provider_instrument}</span>
              </div>
              <div className="md-row">
                <span className="md-key">Source Type</span>
                <span className="md-value md-futures">Gold Futures Proxy</span>
              </div>
            </div>
          )}

          {/* Source Identity — show when primary is active */}
          {health.active_source === "twelve_data" && caps?.primary && (
            <div className="md-source-identity">
              <div className="md-row">
                <span className="md-key">Requested Market</span>
                <span className="md-value">{caps.primary.canonical_instrument}</span>
              </div>
              <div className="md-row">
                <span className="md-key">Actual Data Source</span>
                <span className="md-value">{caps.primary.provider_instrument}</span>
              </div>
              <div className="md-row">
                <span className="md-key">Source Type</span>
                <span className="md-value md-spot">Spot</span>
              </div>
            </div>
          )}

          {/* Primary Provider */}
          <div className="md-provider">
            <div className="md-row">
              <span className="md-key">Primary Provider</span>
              <span className="md-value" style={{ color: statusColor(health.primary.status) }}>
                {statusLabel(health.primary.status)}
              </span>
            </div>
            {health.primary.message && (
              <div className="md-sub">
                <span className="md-sub-text">{health.primary.message}</span>
                {health.primary.latency_ms != null && (
                  <span className="md-sub-text"> ({Math.round(health.primary.latency_ms)}ms)</span>
                )}
              </div>
            )}
          </div>

          {/* Fallback Provider */}
          {health.fallback && (
            <div className="md-provider">
              <div className="md-row">
                <span className="md-key">Fallback Provider</span>
                <span className="md-value" style={{ color: statusColor(health.fallback.status) }}>
                  {statusLabel(health.fallback.status)}
                </span>
              </div>
              {health.fallback.message && (
                <div className="md-sub">
                  <span className="md-sub-text">{health.fallback.message}</span>
                </div>
              )}
            </div>
          )}

          {/* Instruments */}
          {caps && (
            <>
              <div className="md-divider" />
              <div className="md-row">
                <span className="md-key">Instruments</span>
                <span className="md-value">{caps.instruments.join(", ")}</span>
              </div>

              {/* Timeframes */}
              <div className="md-row md-timeframes-header">
                <span className="md-key">Timeframes</span>
              </div>
              <div className="md-timeframe-grid">
                {Object.entries(caps.timeframes).map(([tf, info]) => (
                  <div key={tf} className="md-timeframe-item">
                    <span className="md-tf-label">{tf}</span>
                    <span className="md-tf-cap" style={{ color: capColor(info.capability) }}>
                      {capLabel(info.capability)}
                    </span>
                    {info.source && (
                      <span className="md-tf-source">({info.source})</span>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <style jsx>{`
        .md-card {
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: 12px;
          padding: 1.5rem;
          width: 100%;
          max-width: 480px;
        }
        .md-title {
          font-size: 1rem;
          font-weight: 600;
          margin-bottom: 1.25rem;
          color: var(--color-text);
        }
        .md-loading {
          color: var(--color-text-muted);
          font-size: 0.85rem;
          padding: 1rem 0;
        }
        .md-grid {
          display: flex;
          flex-direction: column;
          gap: 0.6rem;
        }
        .md-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .md-key {
          font-size: 0.8rem;
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .md-value {
          font-size: 0.85rem;
          font-family: var(--font-mono);
          color: var(--color-text);
        }
        .md-provider {
          padding: 0.5rem 0;
        }
        .md-sub {
          padding-left: 0.5rem;
          margin-top: 0.25rem;
        }
        .md-sub-text {
          font-size: 0.75rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .md-divider {
          height: 1px;
          background: var(--color-border);
          margin: 0.5rem 0;
        }
        .md-source-identity {
          padding: 0.5rem 0;
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
          border-left: 2px solid var(--color-border);
          padding-left: 0.75rem;
          margin: 0.25rem 0;
        }
        .md-spot {
          color: var(--color-accent);
        }
        .md-futures {
          color: var(--color-checking);
        }
        .md-timeframes-header {
          margin-top: 0.25rem;
        }
        .md-timeframe-grid {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 0.4rem;
        }
        .md-timeframe-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 0.35rem 0.25rem;
          background: var(--color-bg);
          border-radius: 6px;
          border: 1px solid var(--color-border);
        }
        .md-tf-label {
          font-size: 0.75rem;
          font-family: var(--font-mono);
          font-weight: 600;
          color: var(--color-text);
          margin-bottom: 0.15rem;
        }
        .md-tf-cap {
          font-size: 0.6rem;
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }
        .md-tf-source {
          font-size: 0.55rem;
          color: var(--color-text-muted);
        }
      `}</style>
    </div>
  );
}
