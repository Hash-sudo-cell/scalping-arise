"use client";

/**
 * Scalping Arise — Intelligence Status Component
 *
 * Displays Phase 8 intelligence state: event risk, strategy performance,
 * and unified decision. Minimal, scannable, consistent with other status cards.
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

  if (loading && !evaluation) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="flex items-center gap-2 text-gray-400">
          <div className="h-3 w-3 rounded-full bg-gray-600 animate-pulse" />
          <span className="text-sm">Loading intelligence...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900 border border-red-900 rounded-lg p-4">
        <div className="text-red-400 text-sm">Error: {error}</div>
      </div>
    );
  }

  if (!evaluation) return null;

  const decisionColor =
    evaluation.overall_decision === "allow"
      ? "text-green-400"
      : evaluation.overall_decision === "restrict"
        ? "text-yellow-400"
        : "text-red-400";

  const decisionBg =
    evaluation.overall_decision === "allow"
      ? "bg-green-900/20 border-green-800"
      : evaluation.overall_decision === "restrict"
        ? "bg-yellow-900/20 border-yellow-800"
        : "bg-red-900/20 border-red-800";

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Intelligence
        </h3>
        <span className="text-xs text-gray-500">{instrument}</span>
      </div>

      {/* Decision Badge */}
      <div className={`flex items-center gap-2 px-3 py-2 rounded border ${decisionBg}`}>
        <span className={`text-lg font-bold uppercase ${decisionColor}`}>
          {evaluation.overall_decision}
        </span>
        {evaluation.overall_decision !== "allow" && (
          <span className="text-xs text-gray-400">
            ({evaluation.reasons.length} reason{evaluation.reasons.length !== 1 ? "s" : ""})
          </span>
        )}
      </div>

      {/* Event Summary */}
      {evaluation.event_context_summary && (
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="text-center">
            <div className="text-gray-500">Events</div>
            <div className="text-gray-300 font-medium">
              {evaluation.event_context_summary.total_events}
            </div>
          </div>
          <div className="text-center">
            <div className="text-gray-500">Relevant</div>
            <div className="text-gray-300 font-medium">
              {evaluation.event_context_summary.relevant_events}
            </div>
          </div>
          <div className="text-center">
            <div className="text-gray-500">High Impact</div>
            <div className="text-gray-300 font-medium">
              {evaluation.event_context_summary.high_impact_events}
            </div>
          </div>
        </div>
      )}

      {/* Strategy State */}
      {strategyState && (
        <div className="border-t border-gray-800 pt-3 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Strategy State</span>
            <span className={`font-medium ${
              strategyState.state === "active"
                ? "text-green-400"
                : strategyState.state === "monitored"
                  ? "text-yellow-400"
                  : strategyState.state === "restricted"
                    ? "text-orange-400"
                    : "text-red-400"
            }`}>
              {strategyState.state.toUpperCase()}
            </span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Sample Size</span>
            <span className="text-gray-300">{strategyState.sample_size}</span>
          </div>
          {strategyState.state_reasons.length > 0 && (
            <div className="text-xs text-gray-400 space-y-1">
              {strategyState.state_reasons.slice(0, 2).map((reason, i) => (
                <div key={i} className="flex items-start gap-1">
                  <span className="text-gray-600">·</span>
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Performance Metrics */}
      {metrics && metrics.total_trades > 0 && (
        <div className="border-t border-gray-800 pt-3 grid grid-cols-2 gap-2 text-xs">
          <div>
            <span className="text-gray-500">Win Rate</span>
            <span className="ml-2 text-gray-300 font-medium">
              {(metrics.win_rate * 100).toFixed(1)}%
            </span>
          </div>
          <div>
            <span className="text-gray-500">Net P&L</span>
            <span className={`ml-2 font-medium ${metrics.net_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
              {metrics.net_pnl.toFixed(2)}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Profit Factor</span>
            <span className="ml-2 text-gray-300 font-medium">
              {metrics.profit_factor.toFixed(2)}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Max Drawdown</span>
            <span className="ml-2 text-gray-300 font-medium">
              {metrics.max_drawdown.toFixed(1)}%
            </span>
          </div>
        </div>
      )}

      {/* Restrictions */}
      {evaluation.restrictions.length > 0 && (
        <div className="border-t border-gray-800 pt-3 space-y-1">
          {evaluation.restrictions.map((restriction, i) => (
            <div key={i} className="text-xs text-yellow-400/80 flex items-start gap-1">
              <span>⚠</span>
              <span>{restriction}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
