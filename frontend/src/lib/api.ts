/**
 * Scalping Arise — API Client
 *
 * Centralized API communication layer.
 * All backend requests flow through this module.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  service: string;
  version: string;
  environment: string;
  timestamp: string;
}

export interface APIError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface ProviderHealth {
  provider_name: string;
  status: "healthy" | "degraded" | "unavailable";
  latency_ms: number | null;
  message: string | null;
  checked_at: string;
}

export interface MarketDataHealthResponse {
  status: "healthy" | "degraded" | "unavailable";
  primary: ProviderHealth;
  fallback: ProviderHealth | null;
  active_source: string | null;
  last_data_timestamp: string | null;
}

export interface TimeframeCapability {
  capability: "native" | "derived" | "unsupported";
  source: string | null;
}

export interface ProviderInfo {
  name: string;
  canonical_instrument: string;
  provider_instrument: string;
  source_type: "spot" | "futures_proxy";
  requires_api_key: boolean;
  rate_limit_per_minute: number | null;
}

export interface CapabilitiesResponse {
  primary: ProviderInfo;
  fallback: ProviderInfo;
  timeframes: Record<string, TimeframeCapability>;
  instruments: string[];
  active_source: string | null;
}

/**
 * Generic fetch helper with timeout and structured error handling.
 */
async function apiFetch<T>(
  path: string,
  timeoutMs: number = 10000,
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
 * Fetch backend health status.
 */
export async function fetchHealth() {
  return apiFetch<HealthResponse>("/api/v1/health");
}

/**
 * Fetch market data subsystem health.
 */
export async function fetchMarketDataHealth() {
  return apiFetch<MarketDataHealthResponse>("/api/v1/market-data/health");
}

/**
 * Fetch market data capabilities.
 */
export async function fetchCapabilities() {
  return apiFetch<CapabilitiesResponse>("/api/v1/market-data/capabilities");
}
