"use client";

import { useEffect, useState } from "react";
import {
  fetchTechnicalFeatures,
  type TechnicalFeaturesResponse,
} from "@/lib/featuresApi";

type Status = "loading" | "ok" | "error";

export default function TechnicalFeaturesStatus() {
  const [features, setFeatures] = useState<TechnicalFeaturesResponse | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const res = await fetchTechnicalFeatures("1h", 300);
      if (cancelled) return;

      if (res.ok && res.data) {
        setFeatures(res.data);
        setStatus("ok");
      } else {
        setError(res.error || "Failed to load features");
        setStatus("error");
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  const featureSetStatusColor = (s: string) =>
    s === "ready" ? "var(--color-accent)" :
    s === "warming_up" ? "var(--color-checking)" :
    "var(--color-warning)";

  const volClassColor = (s: string) =>
    s === "low" ? "var(--color-checking)" :
    s === "normal" ? "var(--color-accent)" :
    s === "high" ? "var(--color-warning)" :
    "var(--color-error)";

  const statusColor = (s: string) =>
    s === "available" ? "var(--color-accent)" :
    s === "insufficient_data" ? "var(--color-checking)" :
    "var(--color-warning)";

  const alignmentColor = (s: string) =>
    s === "bullish" ? "var(--color-accent)" :
    s === "bearish" ? "var(--color-error)" :
    "var(--color-text-muted)";

  const formatVal = (v: number | null, decimals: number = 2) =>
    v !== null ? v.toFixed(decimals) : "—";

  const availBadge = (s: string) => {
    if (s === "available") return null;
    const label = s === "insufficient_data" ? "warming up" : "n/a";
    return <span className="tf-avail-badge">{label}</span>;
  };

  return (
    <div className="tf-card">
      <h2 className="tf-title">Technical Features Engine</h2>

      {status === "loading" && (
        <div className="tf-loading">Calculating features...</div>
      )}

      {error && (
        <div className="tf-error">
          <span className="tf-error-key">Error</span>
          <span className="tf-error-value">{error}</span>
        </div>
      )}

      {features && (
        <div className="tf-grid">
          {/* Status */}
          <div className="tf-row">
            <span className="tf-key">Status</span>
            <span className="tf-value" style={{ color: statusColor(features.status) }}>
              {features.status}
            </span>
          </div>

          <div className="tf-reason">
            <span className="tf-reason-text">{features.reason}</span>
          </div>

          {/* Feature-Set Status */}
          <div className="tf-row">
            <span className="tf-key">Feature Set</span>
            <span className="tf-value" style={{ color: featureSetStatusColor(features.feature_set_status) }}>
              {features.feature_set_status.toUpperCase()}
            </span>
          </div>
          {features.feature_set_reason && (
            <div className="tf-reason">
              <span className="tf-reason-text">{features.feature_set_reason}</span>
            </div>
          )}

          {/* Volatility Classification */}
          {features.volatility_classification && (
            <>
              <div className="tf-row">
                <span className="tf-key">Volatility Class</span>
                <span className="tf-value" style={{ color: volClassColor(features.volatility_classification) }}>
                  {features.volatility_classification.toUpperCase()}
                </span>
              </div>
              {features.volatility_classification_reason && (
                <div className="tf-reason">
                  <span className="tf-reason-text">{features.volatility_classification_reason}</span>
                </div>
              )}
            </>
          )}

          {/* Source Context */}
          {features.metadata && (
            <>
              <div className="tf-divider" />
              <div className="tf-row">
                <span className="tf-key">Source</span>
                <span className="tf-value">
                  {features.metadata.provider} ({features.metadata.source_type})
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Candles</span>
                <span className="tf-value">{features.metadata.candle_count}</span>
              </div>
            </>
          )}

          {/* Trend (EMA) */}
          {features.trend && (
            <>
              <div className="tf-divider" />
              <div className="tf-section">Trend — EMA</div>
              <div className="tf-row">
                <span className="tf-key">EMA {features.trend.fast.period}</span>
                <span className="tf-value">
                  {formatVal(features.trend.fast.value)}
                  {availBadge(features.trend.fast.availability)}
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">EMA {features.trend.medium.period}</span>
                <span className="tf-value">
                  {formatVal(features.trend.medium.value)}
                  {availBadge(features.trend.medium.availability)}
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">EMA {features.trend.slow.period}</span>
                <span className="tf-value">
                  {formatVal(features.trend.slow.value)}
                  {availBadge(features.trend.slow.availability)}
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Alignment</span>
                <span className="tf-value" style={{ color: alignmentColor(features.trend.alignment) }}>
                  {features.trend.alignment.toUpperCase()}
                </span>
              </div>
            </>
          )}

          {/* Momentum */}
          {features.momentum?.rsi && (
            <>
              <div className="tf-divider" />
              <div className="tf-section">Momentum</div>
              <div className="tf-row">
                <span className="tf-key">RSI ({features.momentum.rsi.period})</span>
                <span className="tf-value">{formatVal(features.momentum.rsi.value)}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">RSI State</span>
                <span className="tf-value">{features.momentum.rsi.state}</span>
              </div>
            </>
          )}

          {features.momentum?.macd && (
            <>
              <div className="tf-row">
                <span className="tf-key">MACD</span>
                <span className="tf-value">
                  {formatVal(features.momentum.macd.macd_line, 4)}
                  {availBadge(features.momentum.macd.macd_line_availability)}
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Signal</span>
                <span className="tf-value">
                  {formatVal(features.momentum.macd.signal_line, 4)}
                  {availBadge(features.momentum.macd.signal_line_availability)}
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Histogram</span>
                <span className="tf-value">
                  {formatVal(features.momentum.macd.histogram, 4)}
                  {availBadge(features.momentum.macd.histogram_availability)}
                </span>
              </div>
              <div className="tf-row">
                <span className="tf-key">MACD Context</span>
                <span className="tf-value">{features.momentum.macd.context}</span>
              </div>
            </>
          )}

          {/* Volatility */}
          {features.volatility?.atr && (
            <>
              <div className="tf-divider" />
              <div className="tf-section">Volatility</div>
              <div className="tf-row">
                <span className="tf-key">ATR ({features.volatility.atr.period})</span>
                <span className="tf-value">{formatVal(features.volatility.atr.value, 4)}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">ATR %</span>
                <span className="tf-value">{formatVal(features.volatility.atr.percentage, 3)}%</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Volatility State</span>
                <span className="tf-value">{features.volatility.atr.state}</span>
              </div>
            </>
          )}

          {features.volatility?.bollinger_bands && (
            <>
              <div className="tf-row">
                <span className="tf-key">BB Upper</span>
                <span className="tf-value">{formatVal(features.volatility.bollinger_bands.upper_band)}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">BB Middle</span>
                <span className="tf-value">{formatVal(features.volatility.bollinger_bands.middle_band)}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">BB Lower</span>
                <span className="tf-value">{formatVal(features.volatility.bollinger_bands.lower_band)}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Price Position</span>
                <span className="tf-value">{features.volatility.bollinger_bands.price_position}</span>
              </div>
            </>
          )}

          {/* Volume */}
          {features.volume && (
            <>
              <div className="tf-divider" />
              <div className="tf-section">Volume</div>
              <div className="tf-row">
                <span className="tf-key">Relative</span>
                <span className="tf-value">{features.volume.relative_volume !== null ? `${features.volume.relative_volume.toFixed(2)}x` : "—"}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">State</span>
                <span className="tf-value">{features.volume.state}</span>
              </div>
            </>
          )}

          {/* Price */}
          {features.price && (
            <>
              <div className="tf-divider" />
              <div className="tf-section">Price</div>
              <div className="tf-row">
                <span className="tf-key">Price</span>
                <span className="tf-value">{formatVal(features.price.current_price)}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Change</span>
                <span className="tf-value">{features.price.percentage_change !== null ? `${features.price.percentage_change >= 0 ? "+" : ""}${features.price.percentage_change.toFixed(3)}%` : "—"}</span>
              </div>
              <div className="tf-row">
                <span className="tf-key">Range Position</span>
                <span className="tf-value">{features.price.position_in_range !== null ? `${(features.price.position_in_range * 100).toFixed(1)}%` : "—"}</span>
              </div>
            </>
          )}

          {/* Availability Summary */}
          {features.availability && features.availability.length > 0 && (
            <>
              <div className="tf-divider" />
              <div className="tf-section">Feature Availability</div>
              {features.availability.map((a, i) => (
                <div key={`avail-${i}`} className="tf-row">
                  <span className="tf-key">{a.name}</span>
                  <span className="tf-value" style={{ color: statusColor(a.status) }}>
                    {a.status}
                  </span>
                </div>
              ))}
            </>
          )}

          {/* Warnings */}
          {features.warnings && features.warnings.length > 0 && (
            <>
              <div className="tf-divider" />
              {features.warnings.map((w, i) => (
                <div key={`warn-${i}`} className="tf-warning">{w}</div>
              ))}
            </>
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
          max-width: 480px;
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
        .tf-avail-badge {
          display: inline-block;
          font-size: 0.6rem;
          font-family: var(--font-mono);
          color: var(--color-checking);
          background: rgba(255, 193, 7, 0.1);
          border: 1px solid rgba(255, 193, 7, 0.3);
          border-radius: 4px;
          padding: 0 0.3rem;
          margin-left: 0.4rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          vertical-align: middle;
        }
      `}</style>
    </div>
  );
}
