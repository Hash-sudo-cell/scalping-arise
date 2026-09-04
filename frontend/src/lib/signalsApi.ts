/**
 * Scalping Arise — Signal Engine API Client
 *
 * Types and fetch functions for the Phase 6 signal evaluation engine.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ConfidenceBreakdown {
  factor: string;
  score: number;
  weight: number;
  contribution: number;
  description: string;
}

export interface ConfidenceScore {
  overall: number;
  strategy_alignment: number;
  mtf_confirmation: number;
  evidence_strength: number;
  regime_consistency: number;
  breakdown: ConfidenceBreakdown[];
}

export interface SignalCandidate {
  strategy_id: string;
  strategy_version: string;
  strategy_name: string;
  direction: "long" | "short" | "none";
  quality_score_normalized: number;
  quality_score_raw: number;
  quality_score_max: number;
  condition_pass_rate: number;
  invalidation_triggered: boolean;
  market_regime: string | null;
}

export interface TimeframeConfirmationResponse {
  timeframe: string;
  aligned: boolean;
  confirmation_level: "strong" | "moderate" | "weak" | "none";
  ema_alignment: string | null;
  trend_state: string | null;
}

export interface MTFConfirmationResponse {
  confirmed: boolean;
  confirmation_level: "strong" | "moderate" | "weak" | "none";
  aligned_count: number;
  total_count: number;
  confirmations: TimeframeConfirmationResponse[];
}

export interface DirectionalConflictResponse {
  conflict_type: string;
  description: string;
  involved_strategies: string[];
  severity: number;
}

export interface ConflictResolutionResponse {
  final_direction: "long" | "short" | "none";
  confidence: number;
  resolution_method: string;
  dropped_candidates: string[];
}

export interface SignalEvaluationResponse {
  evaluation_id: string;
  evaluation_timestamp: string;
  instrument: string;
  status: "qualified" | "rejected" | "conflict" | "insufficient_context";
  direction: "long" | "short" | "none";
  reason: string;
  confidence?: ConfidenceScore;
  candidates?: SignalCandidate[];
  mtf_confirmation?: MTFConfirmationResponse;
  conflicts?: DirectionalConflictResponse[];
  resolution?: ConflictResolutionResponse;
  source_types_used?: string[];
  timeframes_evaluated?: string[];
}

export interface SignalCapabilitiesResponse {
  module: string;
  status: string;
  features: Record<string, boolean>;
  thresholds: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function signalsFetch<T>(
  path: string,
  timeoutMs: number = 60000,
): Promise<{ data: T | null; error: string | null; ok: boolean }> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(timeoutMs),
    });

    if (!response.ok) {
      return {
        data: null,
        error: `Backend returned status ${response.status}`,
        ok: false,
      };
    }

    const data: T = await response.json();
    return { data, error: null, ok: true };
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Unknown error connecting to backend";
    return { data: null, error: message, ok: false };
  }
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Fetch signal engine health.
 */
export async function fetchSignalsHealth() {
  return signalsFetch<{ status: string; module: string; configuration: Record<string, unknown>; strategies_available: number }>(
    "/api/v1/signals/health",
  );
}

/**
 * Fetch signal engine capabilities.
 */
export async function fetchSignalsCapabilities() {
  return signalsFetch<SignalCapabilitiesResponse>(
    "/api/v1/signals/capabilities",
  );
}

/**
 * Run a complete signal evaluation.
 */
export async function fetchSignalsEvaluate(
  instrument: string = "XAU/USD",
  timeframes: string[] = ["1m", "5m", "15m"],
  limit: number = 300,
  strategyIds?: string[],
) {
  const tfParam = timeframes.join(",");
  let url = `/api/v1/signals/evaluate?instrument=${encodeURIComponent(instrument)}&timeframes=${encodeURIComponent(tfParam)}&limit=${limit}`;
  if (strategyIds && strategyIds.length > 0) {
    url += `&strategy_ids=${encodeURIComponent(strategyIds.join(","))}`;
  }
  return signalsFetch<SignalEvaluationResponse>(url);
}
