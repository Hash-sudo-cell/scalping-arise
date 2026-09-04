/**
 * Scalping Arise — Strategy Engine API Client
 *
 * Types and fetch functions for the Phase 5 strategy evaluation engine.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TimeframeContext {
  timeframe: string;
  source_type: string;
  provider: string;
  provider_instrument: string;
  candle_count: number;
}

export interface EligibilityCheck {
  check_name: string;
  expected_state: string;
  actual_state: string;
  status: "passed" | "failed" | "unavailable";
  reason: string;
}

export interface EligibilityResult {
  eligible: boolean;
  checks: EligibilityCheck[];
  blocked_by: string | null;
}

export interface ConditionResult {
  condition_id: string;
  condition_name: string;
  description: string;
  criticality: "critical" | "required" | "optional";
  expected_value: string;
  actual_value: string;
  status: "passed" | "failed" | "unavailable";
  reason: string;
  evidence: string[];
}

export interface InvalidationResult {
  rule_id: string;
  rule_name: string;
  description: string;
  triggered: boolean;
  reason: string;
  evidence: string[];
}

export interface QualityScoreBreakdown {
  category: string;
  points_awarded: number;
  max_points: number;
  reason: string;
}

export interface QualityScore {
  score: number;
  max_score: number;
  scoring_model_version: string;
  breakdown: QualityScoreBreakdown[];
  normalized_score: number;
}

// ---------------------------------------------------------------------------
// Liquidity Types
// ---------------------------------------------------------------------------

export interface LiquidityConditionResult {
  condition_id: string;
  condition_name: string;
  description: string;
  policy: "required" | "optional" | "not_used";
  status: "passed" | "failed" | "unavailable";
  expected_value: string;
  actual_value: string;
  reason: string;
  evidence: string[];
}

export interface LiquidityAvailabilityStatus {
  status: "available" | "unavailable" | "not_evaluated";
  reason: string;
}

export interface LiquidityConditionSummary {
  available: boolean;
  availability_status: LiquidityAvailabilityStatus;
  condition_results: LiquidityConditionResult[];
  required_passed: number;
  required_failed: number;
  required_unavailable: number;
  optional_passed: number;
  optional_failed: number;
  optional_unavailable: number;
  any_required_failed: boolean;
}

export interface StrategyEvaluationResponse {
  evaluation_id: string;
  evaluation_timestamp: string;
  strategy_id: string;
  strategy_version: string;
  strategy_name: string;
  instrument: string;
  status: "not_applicable" | "insufficient_data" | "not_qualified" | "qualified" | "invalidated" | "unavailable";
  direction: "bullish" | "bearish" | "neutral" | "none";
  reason: string;
  timeframe_contexts?: TimeframeContext[];
  source_types_used?: string[];
  market_regime?: string;
  market_structure_summary?: string;
  eligibility?: EligibilityResult;
  condition_results?: ConditionResult[];
  invalidation_results?: InvalidationResult[];
  quality_score?: QualityScore;
  liquidity_context_used?: boolean;
  liquidity_summary?: LiquidityConditionSummary;
}

export interface StrategyCapability {
  strategy_id: string;
  strategy_version: string;
  strategy_name: string;
  enabled: boolean;
  applicable_market_regimes: string[];
  required_timeframes: string[];
  source_compatibility_policy: string;
  description: string;
}

export interface StrategyCapabilitiesResponse {
  module: string;
  status: string;
  strategies: StrategyCapability[];
}

export interface StrategyDefinitionResponse {
  strategy_id: string;
  strategy_version: string;
  strategy_name: string;
  description: string;
  enabled: boolean;
  applicable_market_regimes: string[];
  required_timeframes: { timeframe: string; role: string }[];
  source_compatibility_policy: string;
  scoring_model_version: string;
}

export interface StrategyListResponse {
  strategies: StrategyDefinitionResponse[];
  count: number;
}

export interface EvaluateAllResponse {
  evaluations: StrategyEvaluationResponse[];
  count: number;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function strategiesFetch<T>(
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
 * Fetch strategy engine health.
 */
export async function fetchStrategiesHealth() {
  return strategiesFetch<{ status: string; module: string; configuration: Record<string, unknown>; strategies_registered: number; strategies_enabled: number }>(
    "/api/v1/strategies/health",
  );
}

/**
 * Fetch strategy engine capabilities.
 */
export async function fetchStrategiesCapabilities() {
  return strategiesFetch<StrategyCapabilitiesResponse>(
    "/api/v1/strategies/capabilities",
  );
}

/**
 * List all strategy definitions.
 */
export async function fetchStrategiesList() {
  return strategiesFetch<StrategyListResponse>(
    "/api/v1/strategies",
  );
}

/**
 * Evaluate a single strategy.
 */
export async function fetchStrategyEvaluate(
  strategyId: string,
  instrument: string = "XAU/USD",
  timeframes: string[] = ["1m", "5m", "15m"],
  limit: number = 300,
) {
  const tfParam = timeframes.join(",");
  return strategiesFetch<StrategyEvaluationResponse>(
    `/api/v1/strategies/evaluate?strategy_id=${encodeURIComponent(strategyId)}&instrument=${encodeURIComponent(instrument)}&timeframes=${encodeURIComponent(tfParam)}&limit=${limit}`,
  );
}

/**
 * Evaluate all enabled strategies.
 */
export async function fetchStrategiesEvaluateAll(
  instrument: string = "XAU/USD",
  timeframes: string[] = ["1m", "5m", "15m"],
  limit: number = 300,
) {
  const tfParam = timeframes.join(",");
  return strategiesFetch<EvaluateAllResponse>(
    `/api/v1/strategies/evaluate-all?instrument=${encodeURIComponent(instrument)}&timeframes=${encodeURIComponent(tfParam)}&limit=${limit}`,
  );
}
