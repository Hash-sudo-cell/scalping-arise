/**
 * Scalping Arise — API Client Extensions
 *
 * Market Analysis API types and fetch functions.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface AnalysisContext {
  canonical_instrument: string;
  provider_instrument: string;
  provider: string;
  source_type: string;
  timeframe: string;
  candle_count: number;
  analysis_timestamp: string;
  data_from_cache: boolean;
}

export interface TrendResult {
  state: "bullish" | "bearish" | "ranging" | "unclear";
  reason: string;
  structure_labels: string[];
}

export interface StructureResult {
  latest_labels: string[];
  point_count: number;
}

export interface BOSEvent {
  direction: "bullish_bos" | "bearish_bos";
  broken_level: number;
  break_price: number;
  break_timestamp: string;
  confirmation_basis: string;
  timeframe: string;
  evidence: string;
}

export interface CHOCHEvent {
  direction: "bullish_choch" | "bearish_choch";
  broken_level: number;
  break_price: number;
  break_timestamp: string;
  confirmation_basis: string;
  prior_structure: string;
  timeframe: string;
  evidence: string;
}

export interface EventsResult {
  bos: BOSEvent[];
  choch: CHOCHEvent[];
}

export interface SupportResistanceZone {
  zone_type: "support" | "resistance";
  lower_bound: number;
  upper_bound: number;
  strength: number;
  source_swings: number[];
  timeframe: string;
}

export interface ZonesResult {
  support: SupportResistanceZone[];
  resistance: SupportResistanceZone[];
}

export interface RegimeResult {
  state: "trending_up" | "trending_down" | "ranging" | "volatile" | "unclear";
  evidence: string[];
}

export interface LiquidityPool {
  pool_id: string;
  side: "buy_side" | "sell_side";
  pool_type: "swing_high" | "swing_low" | "equal_highs" | "equal_lows";
  price_level: number;
  lower_bound: number;
  upper_bound: number;
  touch_count: number;
  source_swings: number[];
  status: "active" | "swept" | "invalidated";
  strength: "low" | "medium" | "high";
  timeframe: string;
}

export interface LiquiditySweep {
  sweep_id: string;
  pool_id: string;
  side: "buy_side" | "sell_side";
  pool_price_level: number;
  sweep_timestamp: string;
  sweep_mode: "wick" | "close";
  sweep_price: number;
  candle_close: number;
  reaction: "rejection" | "acceptance" | "neutral" | "unavailable";
}

export interface LiquidityResult {
  status: "available" | "unavailable";
  reason: string;
  active_pool_count: number;
  swept_pool_count: number;
  nearest_buy_side_pool: LiquidityPool | null;
  nearest_sell_side_pool: LiquidityPool | null;
  distance_to_buy_side: number | null;
  distance_to_sell_side: number | null;
  distance_to_buy_side_pct: number | null;
  distance_to_sell_side_pct: number | null;
  pool_count: number;
  sweep_count: number;
}

export interface MarketAnalysisResponse {
  status: "available" | "unavailable";
  reason: string;
  analysis_timestamp: string;
  context?: AnalysisContext;
  trend?: TrendResult;
  structure?: StructureResult;
  events?: EventsResult;
  zones?: ZonesResult;
  session?: string;
  regime?: RegimeResult;
  liquidity?: LiquidityResult;
}

export interface AnalysisCapabilities {
  supported_analyses: string[];
  configuration: Record<string, number>;
  supported_instruments: string[];
  supported_timeframes: string[];
}

/**
 * Generic fetch helper for analysis endpoints.
 */
async function analysisFetch<T>(
  path: string,
  timeoutMs: number = 30000,
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

/**
 * Run full market analysis.
 */
export async function fetchMarketAnalysis(
  instrument: string = "XAU/USD",
  timeframe: string = "1h",
  limit: number = 200,
) {
  return analysisFetch<MarketAnalysisResponse>(
    `/api/v1/market-analysis?instrument=${encodeURIComponent(instrument)}&timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
  );
}

/**
 * Fetch analysis health.
 */
export async function fetchAnalysisHealth() {
  return analysisFetch<{ status: string; module: string; version: string }>(
    "/api/v1/market-analysis/health",
  );
}

/**
 * Fetch analysis capabilities.
 */
export async function fetchAnalysisCapabilities() {
  return analysisFetch<AnalysisCapabilities>(
    "/api/v1/market-analysis/capabilities",
  );
}
