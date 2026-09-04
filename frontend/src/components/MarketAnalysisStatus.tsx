"use client";

import { useEffect, useState } from "react";
import {
  fetchMarketAnalysis,
  type MarketAnalysisResponse,
} from "@/lib/analysisApi";

type Status = "loading" | "ok" | "error";

export default function MarketAnalysisStatus() {
  const [analysis, setAnalysis] = useState<MarketAnalysisResponse | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const res = await fetchMarketAnalysis("XAU/USD", "1h", 200);
      if (cancelled) return;

      if (res.ok && res.data) {
        setAnalysis(res.data);
        setStatus("ok");
      } else {
        setError(res.error || "Failed to load analysis");
        setStatus("error");
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  const statusColor = (s: string) =>
    s === "available" ? "var(--color-accent)" :
    s === "unavailable" ? "var(--color-warning)" :
    "var(--color-text-muted)";

  const trendColor = (s: string) =>
    s === "bullish" ? "var(--color-accent)" :
    s === "bearish" ? "var(--color-error)" :
    "var(--color-text-muted)";

  const regimeColor = (s: string) =>
    s === "trending_up" ? "var(--color-accent)" :
    s === "trending_down" ? "var(--color-error)" :
    s === "ranging" ? "var(--color-checking)" :
    s === "volatile" ? "var(--color-warning)" :
    "var(--color-text-muted)";

  const sessionLabel = (s: string) =>
    s === "asian" ? "Asian" :
    s === "london" ? "London" :
    s === "new_york" ? "New York" :
    s === "overlap" ? "London/NY Overlap" :
    "Off Session";

  return (
    <div className="ma-card">
      <h2 className="ma-title">Market Analysis Engine</h2>

      {status === "loading" && (
        <div className="ma-loading">Running analysis pipeline...</div>
      )}

      {error && (
        <div className="ma-error">
          <span className="ma-error-key">Error</span>
          <span className="ma-error-value">{error}</span>
        </div>
      )}

      {analysis && (
        <div className="ma-grid">
          {/* Status */}
          <div className="ma-row">
            <span className="ma-key">Status</span>
            <span className="ma-value" style={{ color: statusColor(analysis.status) }}>
              {analysis.status === "available" ? "Available" : "Unavailable"}
            </span>
          </div>

          {/* Reason */}
          {analysis.reason && (
            <div className="ma-reason">
              <span className="ma-reason-text">{analysis.reason}</span>
            </div>
          )}

          {/* Source Context */}
          {analysis.context && (
            <>
              <div className="ma-divider" />
              <div className="ma-row">
                <span className="ma-key">Source</span>
                <span className="ma-value">{analysis.context.provider}</span>
              </div>
              <div className="ma-row">
                <span className="ma-key">Source Type</span>
                <span className={`ma-value ${analysis.context.source_type === "spot" ? "ma-spot" : "ma-futures"}`}>
                  {analysis.context.source_type === "spot" ? "Spot" : "Gold Futures Proxy"}
                </span>
              </div>
              <div className="ma-row">
                <span className="ma-key">Instrument</span>
                <span className="ma-value">{analysis.context.canonical_instrument}</span>
              </div>
              <div className="ma-row">
                <span className="ma-key">Timeframe</span>
                <span className="ma-value">{analysis.context.timeframe}</span>
              </div>
              <div className="ma-row">
                <span className="ma-key">Candles</span>
                <span className="ma-value">{analysis.context.candle_count}</span>
              </div>
            </>
          )}

          {/* Trend */}
          {analysis.trend && (
            <>
              <div className="ma-divider" />
              <div className="ma-row">
                <span className="ma-key">Trend</span>
                <span className="ma-value" style={{ color: trendColor(analysis.trend.state) }}>
                  {analysis.trend.state.toUpperCase()}
                </span>
              </div>
              {analysis.trend.reason && (
                <div className="ma-evidence">
                  <span className="ma-evidence-text">{analysis.trend.reason}</span>
                </div>
              )}
            </>
          )}

          {/* Structure */}
          {analysis.structure && (
            <>
              <div className="ma-row">
                <span className="ma-key">Structure</span>
                <span className="ma-value">
                  {analysis.structure.latest_labels.join(" -> ")}
                </span>
              </div>
              <div className="ma-row">
                <span className="ma-key">Points</span>
                <span className="ma-value">{analysis.structure.point_count}</span>
              </div>
            </>
          )}

          {/* Events */}
          {analysis.events && (
            <>
              <div className="ma-divider" />
              <div className="ma-row">
                <span className="ma-key">BOS Events</span>
                <span className="ma-value">{analysis.events.bos.length}</span>
              </div>
              {analysis.events.bos.map((e, i) => (
                <div key={`bos-${i}`} className="ma-event">
                  <span className={`ma-event-type ${e.direction === "bullish_bos" ? "ma-bull" : "ma-bear"}`}>
                    {e.direction === "bullish_bos" ? "BULL BOS" : "BEAR BOS"}
                  </span>
                  <span className="ma-event-detail">
                    Level: {e.broken_level.toFixed(2)} | Broke: {e.break_price.toFixed(2)}
                  </span>
                </div>
              ))}
              <div className="ma-row">
                <span className="ma-key">CHOCH Events</span>
                <span className="ma-value">{analysis.events.choch.length}</span>
              </div>
              {analysis.events.choch.map((e, i) => (
                <div key={`choch-${i}`} className="ma-event">
                  <span className={`ma-event-type ${e.direction === "bullish_choch" ? "ma-bull" : "ma-bear"}`}>
                    {e.direction === "bullish_choch" ? "BULL CHOCH" : "BEAR CHOCH"}
                  </span>
                  <span className="ma-event-detail">
                    Level: {e.broken_level.toFixed(2)} | Broke: {e.break_price.toFixed(2)}
                  </span>
                </div>
              ))}
            </>
          )}

          {/* Zones */}
          {analysis.zones && (
            <>
              <div className="ma-divider" />
              <div className="ma-row">
                <span className="ma-key">Support Zones</span>
                <span className="ma-value">{analysis.zones.support.length}</span>
              </div>
              {analysis.zones.support.map((z, i) => (
                <div key={`sup-${i}`} className="ma-zone">
                  <span className="ma-zone-type ma-support">SUPPORT</span>
                  <span className="ma-zone-detail">
                    {z.lower_bound.toFixed(2)} - {z.upper_bound.toFixed(2)} ({z.strength} tests)
                  </span>
                </div>
              ))}
              <div className="ma-row">
                <span className="ma-key">Resistance Zones</span>
                <span className="ma-value">{analysis.zones.resistance.length}</span>
              </div>
              {analysis.zones.resistance.map((z, i) => (
                <div key={`res-${i}`} className="ma-zone">
                  <span className="ma-zone-type ma-resistance">RESISTANCE</span>
                  <span className="ma-zone-detail">
                    {z.lower_bound.toFixed(2)} - {z.upper_bound.toFixed(2)} ({z.strength} tests)
                  </span>
                </div>
              ))}
            </>
          )}

          {/* Session */}
          {analysis.session && (
            <>
              <div className="ma-divider" />
              <div className="ma-row">
                <span className="ma-key">Session</span>
                <span className="ma-value">{sessionLabel(analysis.session)}</span>
              </div>
            </>
          )}

          {/* Regime */}
          {analysis.regime && (
            <>
              <div className="ma-row">
                <span className="ma-key">Regime</span>
                <span className="ma-value" style={{ color: regimeColor(analysis.regime.state) }}>
                  {analysis.regime.state.replace("_", " ").toUpperCase()}
                </span>
              </div>
              {analysis.regime.evidence.map((e, i) => (
                <div key={`ev-${i}`} className="ma-evidence">
                  <span className="ma-evidence-text">{e}</span>
                </div>
              ))}
            </>
          )}

          {/* Liquidity */}
          {analysis.liquidity && (
            <>
              <div className="ma-divider" />
              <div className="ma-row">
                <span className="ma-key">Liquidity</span>
                <span className="ma-value" style={{
                  color: analysis.liquidity.status === "available" ? "var(--color-accent)" : "var(--color-text-muted)"
                }}>
                  {analysis.liquidity.status === "available" ? "Available" : "Unavailable"}
                </span>
              </div>
              {analysis.liquidity.status === "available" && (
                <>
                  <div className="ma-row">
                    <span className="ma-key">Active Pools</span>
                    <span className="ma-value">{analysis.liquidity.active_pool_count}</span>
                  </div>
                  <div className="ma-row">
                    <span className="ma-key">Swept Pools</span>
                    <span className="ma-value">{analysis.liquidity.swept_pool_count}</span>
                  </div>
                  <div className="ma-row">
                    <span className="ma-key">Sweep Events</span>
                    <span className="ma-value">{analysis.liquidity.sweep_count}</span>
                  </div>
                  {analysis.liquidity.distance_to_buy_side !== null && (
                    <div className="ma-row">
                      <span className="ma-key">Nearest Buy-Side</span>
                      <span className="ma-value ma-bull">
                        {analysis.liquidity.distance_to_buy_side.toFixed(2)} ({analysis.liquidity.distance_to_buy_side_pct?.toFixed(3)}%)
                      </span>
                    </div>
                  )}
                  {analysis.liquidity.distance_to_sell_side !== null && (
                    <div className="ma-row">
                      <span className="ma-key">Nearest Sell-Side</span>
                      <span className="ma-value ma-bear">
                        {analysis.liquidity.distance_to_sell_side.toFixed(2)} ({analysis.liquidity.distance_to_sell_side_pct?.toFixed(3)}%)
                      </span>
                    </div>
                  )}
                  {analysis.liquidity.nearest_buy_side_pool && (
                    <div className="ma-evidence">
                      <span className="ma-evidence-text">
                        Buy-side: {analysis.liquidity.nearest_buy_side_pool.pool_type.replace("_", " ")} @ {analysis.liquidity.nearest_buy_side_pool.price_level.toFixed(2)} ({analysis.liquidity.nearest_buy_side_pool.strength})
                      </span>
                    </div>
                  )}
                  {analysis.liquidity.nearest_sell_side_pool && (
                    <div className="ma-evidence">
                      <span className="ma-evidence-text">
                        Sell-side: {analysis.liquidity.nearest_sell_side_pool.pool_type.replace("_", " ")} @ {analysis.liquidity.nearest_sell_side_pool.price_level.toFixed(2)} ({analysis.liquidity.nearest_sell_side_pool.strength})
                      </span>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}

      <style jsx>{`
        .ma-card {
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: 12px;
          padding: 1.5rem;
          width: 100%;
          max-width: 480px;
        }
        .ma-title {
          font-size: 1rem;
          font-weight: 600;
          margin-bottom: 1.25rem;
          color: var(--color-text);
        }
        .ma-loading {
          color: var(--color-text-muted);
          font-size: 0.85rem;
          padding: 1rem 0;
        }
        .ma-error {
          display: flex;
          justify-content: space-between;
          padding: 0.5rem 0;
        }
        .ma-error-key {
          font-size: 0.8rem;
          color: var(--color-error);
          text-transform: uppercase;
        }
        .ma-error-value {
          font-size: 0.8rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .ma-grid {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .ma-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .ma-key {
          font-size: 0.75rem;
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .ma-value {
          font-size: 0.85rem;
          font-family: var(--font-mono);
          color: var(--color-text);
        }
        .ma-spot { color: var(--color-accent); }
        .ma-futures { color: var(--color-checking); }
        .ma-reason {
          padding: 0.4rem 0;
        }
        .ma-reason-text {
          font-size: 0.75rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .ma-divider {
          height: 1px;
          background: var(--color-border);
          margin: 0.3rem 0;
        }
        .ma-evidence {
          padding-left: 0.5rem;
        }
        .ma-evidence-text {
          font-size: 0.7rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .ma-event {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding-left: 0.5rem;
        }
        .ma-event-type {
          font-size: 0.65rem;
          font-weight: 700;
          font-family: var(--font-mono);
          text-transform: uppercase;
        }
        .ma-bull { color: var(--color-accent); }
        .ma-bear { color: var(--color-error); }
        .ma-event-detail {
          font-size: 0.7rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .ma-zone {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding-left: 0.5rem;
        }
        .ma-zone-type {
          font-size: 0.6rem;
          font-weight: 700;
          font-family: var(--font-mono);
          text-transform: uppercase;
          padding: 0.1rem 0.3rem;
          border-radius: 3px;
        }
        .ma-support {
          background: rgba(0, 200, 150, 0.15);
          color: var(--color-accent);
        }
        .ma-resistance {
          background: rgba(255, 80, 80, 0.15);
          color: var(--color-error);
        }
        .ma-zone-detail {
          font-size: 0.7rem;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
      `}</style>
    </div>
  );
}
