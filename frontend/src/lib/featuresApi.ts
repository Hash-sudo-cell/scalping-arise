/**
 * Scalping Arise — Technical Features API Client
 *
 * Types and fetch functions for the Phase 4 feature engine.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface FeatureMetadata {
  canonical_instrument: string;
  provider_instrument: string;
  provider: string;
  source_type: string;
  timeframe: string;
  candle_count: number;
  feature_timestamp: string;
}

export interface EMAValue {
  period: number;
  value: number | null;
  availability: "available" | "insufficient_data" | "unavailable";
  direction: "rising" | "falling" | "flat" | "unknown";
  price_relative: string | null;
  required_history: number;
}

export interface EMAResult {
  fast: EMAValue;
  medium: EMAValue;
  slow: EMAValue;
  alignment: "bullish" | "bearish" | "mixed" | "unavailable";
  alignment_evidence: string[];
}

export interface RSIResult {
  period: number;
  value: number | null;
  availability: "available" | "insufficient_data" | "unavailable";
  state: "overbought" | "strong" | "neutral" | "weak" | "oversold";
  required_history: number;
  evidence: string[];
}

export interface MACDResult {
  fast_period: number;
  slow_period: number;
  signal_period: number;
  macd_line: number | null;
  signal_line: number | null;
  histogram: number | null;
  availability: "available" | "insufficient_data" | "unavailable";
  macd_line_availability: "available" | "insufficient_data" | "unavailable";
  signal_line_availability: "available" | "insufficient_data" | "unavailable";
  histogram_availability: "available" | "insufficient_data" | "unavailable";
  context: "bullish" | "bearish" | "neutral";
  required_history: number;
  evidence: string[];
}

export interface ATRResult {
  period: number;
  value: number | null;
  percentage: number | null;
  availability: "available" | "insufficient_data" | "unavailable";
  state: "high" | "normal" | "low";
  required_history: number;
  evidence: string[];
}

export interface BollingerBandsResult {
  period: number;
  std_dev: number;
  middle_band: number | null;
  upper_band: number | null;
  lower_band: number | null;
  band_width: number | null;
  price_position: "above_upper" | "upper_region" | "middle_region" | "lower_region" | "below_lower" | "unavailable";
  availability: "available" | "insufficient_data" | "unavailable";
  required_history: number;
  evidence: string[];
}

export interface VolumeResult {
  sma_period: number;
  current_volume: number | null;
  average_volume: number | null;
  relative_volume: number | null;
  availability: "available" | "insufficient_data" | "unavailable";
  state: "high" | "normal" | "low" | "unavailable";
  required_history: number;
  evidence: string[];
}

export interface PriceFeatures {
  current_price: number | null;
  previous_close: number | null;
  absolute_change: number | null;
  percentage_change: number | null;
  recent_high: number | null;
  recent_low: number | null;
  recent_range: number | null;
  position_in_range: number | null;
  availability: "available" | "insufficient_data" | "unavailable";
  lookback: number;
  evidence: string[];
}

export interface FeatureAvailabilityItem {
  name: string;
  status: "available" | "insufficient_data" | "unavailable";
  reason: string;
}

export interface TechnicalFeaturesResponse {
  status: "available" | "insufficient_data" | "unavailable";
  reason: string;
  feature_set_status: "ready" | "warming_up" | "unavailable";
  feature_set_reason: string;
  volatility_classification?: "low" | "normal" | "high" | "extreme";
  volatility_classification_reason: string;
  feature_timestamp: string;
  metadata?: FeatureMetadata;
  trend?: EMAResult;
  momentum?: {
    rsi?: RSIResult;
    macd?: MACDResult;
  };
  volatility?: {
    atr?: ATRResult;
    bollinger_bands?: BollingerBandsResult;
  };
  volume?: VolumeResult;
  price?: PriceFeatures;
  availability?: FeatureAvailabilityItem[];
  warnings?: string[];
}

export interface MultiTimeframeResponse {
  feature_set_status: "ready" | "warming_up" | "unavailable";
  feature_set_reason: string;
  feature_timestamp: string;
  timeframes: TechnicalFeaturesResponse[];
  warnings?: string[];
}

export interface TechnicalFeaturesCapabilities {
  module: string;
  status: string;
  features: Record<string, unknown>;
  minimum_candles_required: number;
}

/**
 * Generic fetch helper for technical features endpoints.
 */
async function featuresFetch<T>(
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
 * Fetch all technical features.
 */
export async function fetchTechnicalFeatures(
  timeframe: string = "1h",
  limit: number = 300,
) {
  return featuresFetch<TechnicalFeaturesResponse>(
    `/api/v1/technical-features?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
  );
}

/**
 * Fetch technical features health.
 */
export async function fetchTechnicalFeaturesHealth() {
  return featuresFetch<{ status: string; module: string; configuration: Record<string, unknown> }>(
    "/api/v1/technical-features/health",
  );
}

/**
 * Fetch technical features capabilities.
 */
export async function fetchTechnicalFeaturesCapabilities() {
  return featuresFetch<TechnicalFeaturesCapabilities>(
    "/api/v1/technical-features/capabilities",
  );
}

/**
 * Fetch multi-timeframe technical features.
 */
export async function fetchMultiTimeframeFeatures(
  timeframes: string[] = ["1m", "5m", "15m"],
  limit: number = 300,
) {
  const tfParam = timeframes.join(",");
  return featuresFetch<MultiTimeframeResponse>(
    `/api/v1/technical-features/multi-timeframe?timeframes=${encodeURIComponent(tfParam)}&limit=${limit}`,
  );
}
