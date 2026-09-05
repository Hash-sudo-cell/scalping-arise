/**
 * Scalping Arise — Trade Planning API Client
 *
 * Types and fetch functions for the Phase 7 trade planning & risk engine.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PlanSide = "long" | "short";
export type PlanState =
  | "no_plan"
  | "draft"
  | "calculated"
  | "validated"
  | "approved"
  | "rejected"
  | "expired"
  | "invalidated";
export type EntryType = "market" | "limit" | "stop";
export type EntryState = "entry_ready" | "wait_for_entry" | "entry_unavailable";
export type SLType = "invalidation" | "atr" | "structure" | "fixed";
export type RiskUnit = "currency" | "pips" | "percent";

export interface TPTarget {
  label: string;
  rr_ratio: number;
  distance_price: number;
  distance_pips: number;
  partial_close_pct: number;
}

export interface EntryPlan {
  type: EntryType;
  state: EntryState;
  price: number | null;
  bid: number | null;
  ask: number | null;
  spread_pips: number | null;
  reason: string;
}

export interface StopLossPlan {
  type: SLType;
  price: number;
  distance_price: number;
  distance_pips: number;
  atr_multiple: number | null;
  risk_amount: number;
  risk_pct: number;
}

export interface TakeProfitPlan {
  targets: TPTarget[];
  primary_target: TPTarget | null;
  secondary_target: TPTarget | null;
  max_rr_ratio: number;
}

export interface PositionSizeResult {
  lots: number;
  raw_lots: number;
  contract_size: number;
  notional_value: number;
  margin_required: number;
  lot_step: number;
  lot_min: number;
  lot_max: number;
  capped: boolean;
}

export interface RiskCalculation {
  position_size: PositionSizeResult;
  risk_amount: number;
  risk_pct: number;
  sl_distance_price: number;
  sl_distance_pips: number;
  risk_currency: number;
  risk_reward_ratio: number | null;
  daily_loss_remaining_pct: number | null;
  within_daily_loss_limit: boolean;
  within_max_drawdown: boolean;
  within_position_limit: boolean;
}

export interface CostEstimate {
  spread_cost: number;
  commission: number;
  total_cost: number;
  cost_pct_of_risk: number;
}

export interface FreshnessCheck {
  is_fresh: boolean;
  data_age_seconds: number;
  max_age_seconds: number;
}

export interface PriceTickCheck {
  valid: boolean;
  current_price: number;
  bid: number | null;
  ask: number | null;
  spread_pips: number | null;
  tick_aligned: boolean;
  stale: boolean;
}

export interface EligibilityCheck {
  eligible: boolean;
  rejection_reason: string | null;
  confidence: number | null;
  quality: number | null;
  instrument_supported: boolean;
}

export interface PlanTransition {
  from_state: PlanState;
  to_state: PlanState;
  reason: string;
  timestamp: string;
}

export interface TradePlan {
  plan_id: string;
  signal_id: string;
  signal_timestamp: string;
  instrument: string;
  side: PlanSide;
  state: PlanState;
  confidence: number;
  quality_score: number;
  entry: EntryPlan;
  stop_loss: StopLossPlan | null;
  take_profit: TakeProfitPlan | null;
  position_size: PositionSizeResult | null;
  risk: RiskCalculation | null;
  cost: CostEstimate | null;
  freshness: FreshnessCheck | null;
  price_tick: PriceTickCheck | null;
  eligibility: EligibilityCheck | null;
  transitions: PlanTransition[];
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  rejection_reason: string | null;
}

export interface TradePlanningHealthResponse {
  status: string;
  module: string;
  pipeline_steps: string[];
  plan_states: string[];
}

export interface TradePlanningCapabilitiesResponse {
  module: string;
  status: string;
  features: Record<string, boolean>;
  thresholds: Record<string, number>;
  instruments: string[];
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function tpFetch<T>(
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

async function tpPost<T>(
  path: string,
  body: Record<string, unknown>,
  timeoutMs: number = 60000,
): Promise<{ data: T | null; error: string | null; ok: boolean }> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
 * Generate a trade plan from a signal evaluation.
 */
export async function generateTradePlan(params: {
  instrument?: string;
  timeframes?: string[];
  limit?: number;
  strategy_ids?: string[];
}) {
  const body: Record<string, unknown> = {};
  if (params.instrument) body.instrument = params.instrument;
  if (params.timeframes) body.timeframes = params.timeframes;
  if (params.limit) body.limit = params.limit;
  if (params.strategy_ids) body.strategy_ids = params.strategy_ids;

  return tpPost<TradePlan>("/api/v1/trade-planning/generate", body);
}

/**
 * Fetch trade planning health status.
 */
export async function fetchTradePlanningHealth() {
  return tpFetch<TradePlanningHealthResponse>(
    "/api/v1/trade-planning/health",
  );
}

/**
 * Fetch trade planning capabilities.
 */
export async function fetchTradePlanningCapabilities() {
  return tpFetch<TradePlanningCapabilitiesResponse>(
    "/api/v1/trade-planning/capabilities",
  );
}

/**
 * Fetch the trade plan history.
 */
export async function fetchTradePlanHistory(limit: number = 10) {
  return tpFetch<TradePlan[]>(
    `/api/v1/trade-planning/history?limit=${limit}`,
  );
}

/**
 * Fetch only approved trade plans.
 */
export async function fetchApprovedTradePlans() {
  return tpFetch<TradePlan[]>(
    "/api/v1/trade-planning/approved",
  );
}

/**
 * Fetch a specific trade plan by ID.
 */
export async function fetchTradePlan(planId: string) {
  return tpFetch<TradePlan>(
    `/api/v1/trade-planning/plans/${encodeURIComponent(planId)}`,
  );
}

/**
 * Fetch supported instruments.
 */
export async function fetchSupportedInstruments() {
  return tpFetch<{ instruments: string[]; count: number }>(
    "/api/v1/trade-planning/instruments",
  );
}
