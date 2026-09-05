/**
 * Scalping Arise — Backtesting API Client
 *
 * Type-safe API client for the backtesting module endpoints.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BacktestConfig {
  instrument?: string;
  timeframe?: string;
  candle_limit?: number;
  mode?: string;
  initial_balance?: number;
  max_positions?: number;
  risk_per_trade_pct?: number;
  fill_method?: string;
  slippage_pips?: number;
  spread_pips?: number;
  strategy_ids?: string[];
  timeframes?: string[];
  train_window?: number;
  test_window?: number;
  step_size?: number;
  monte_carlo_simulations?: number;
  random_seed?: number;
  max_trades?: number;
}

export interface TradeStatistics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  expectancy: number;
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  payoff_ratio: number;
}

export interface RiskMetrics {
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown_pct: number;
  max_drawdown_amount: number;
  volatility_annual: number;
  value_at_risk_95: number;
  conditional_var_95: number;
}

export interface PerformanceMetrics {
  total_return: number;
  total_return_pct: number;
  annualized_return: number;
  net_profit: number;
  gross_profit: number;
  gross_loss: number;
  trade_stats: TradeStatistics;
  risk_metrics: RiskMetrics;
}

export interface BacktestResult {
  run_id: string;
  status: string;
  config: {
    instrument: string;
    timeframe: string;
    mode: string;
    candle_limit: number;
    fill_method: string;
    slippage_pips: number;
    spread_pips: number;
    initial_balance: number;
  };
  candles_loaded: number;
  trades_count: number;
  data_quality: {
    total_candles: number;
    valid_candles: number;
    quality_score: number;
  } | null;
  metrics: PerformanceMetrics | null;
  equity_curve: {
    timestamps: string[];
    equity_values: number[];
    balance_values: number[];
    drawdown_values: number[];
  } | null;
  look_ahead_violations: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  random_seed_used: number | null;
}

export interface RunSummary {
  run_id: string;
  status: string;
  instrument: string;
  timeframe: string;
  mode: string;
  candles_loaded: number;
  trades_count: number;
  net_profit: number | null;
  sharpe_ratio: number | null;
  max_drawdown_pct: number | null;
  created_at: string | null;
  duration_seconds: number | null;
}

export interface BacktestHealthResponse {
  status: string;
  module: string;
  configuration: {
    enabled: boolean;
    enforce_determinism: boolean;
    strict_lookahead: boolean;
  };
  results_stored: number;
  paper_sessions: number;
}

// ---------------------------------------------------------------------------
// API Client
// ---------------------------------------------------------------------------

interface ApiResponse<T> {
  ok: boolean;
  data: T | null;
  error: string | null;
}

async function apiGet<T>(path: string): Promise<ApiResponse<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) {
      return { ok: false, data: null, error: `HTTP ${res.status}: ${res.statusText}` };
    }
    const data = await res.json();
    return { ok: true, data, error: null };
  } catch (err) {
    return { ok: false, data: null, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

async function apiPost<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      return { ok: false, data: null, error: `HTTP ${res.status}: ${res.statusText}` };
    }
    const data = await res.json();
    return { ok: true, data, error: null };
  } catch (err) {
    return { ok: false, data: null, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

async function apiDelete<T>(path: string): Promise<ApiResponse<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
    if (!res.ok) {
      return { ok: false, data: null, error: `HTTP ${res.status}: ${res.statusText}` };
    }
    const data = await res.json();
    return { ok: true, data, error: null };
  } catch (err) {
    return { ok: false, data: null, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

// ---------------------------------------------------------------------------
// Public API functions
// ---------------------------------------------------------------------------

export async function runBacktest(
  config: BacktestConfig
): Promise<ApiResponse<BacktestResult>> {
  return apiPost<BacktestResult>("/backtesting/run", config);
}

export async function listBacktestRuns(
  limit: number = 50
): Promise<ApiResponse<RunSummary[]>> {
  return apiGet<RunSummary[]>(`/backtesting/runs?limit=${limit}`);
}

export async function getBacktestRun(
  runId: string
): Promise<ApiResponse<BacktestResult>> {
  return apiGet<BacktestResult>(`/backtesting/runs/${runId}`);
}

export async function getBacktestTrades(
  runId: string
): Promise<ApiResponse<unknown[]>> {
  return apiGet<unknown[]>(`/backtesting/runs/${runId}/trades`);
}

export async function getBacktestAnalytics(
  runId: string
): Promise<ApiResponse<PerformanceMetrics>> {
  return apiGet<PerformanceMetrics>(`/backtesting/runs/${runId}/analytics`);
}

export async function deleteBacktestRun(
  runId: string
): Promise<ApiResponse<{ status: string; run_id: string }>> {
  return apiDelete<{ status: string; run_id: string }>(`/backtesting/runs/${runId}`);
}

export async function fetchBacktestHealth(): Promise<
  ApiResponse<BacktestHealthResponse>
> {
  return apiGet<BacktestHealthResponse>("/backtesting/health");
}

export async function startPaperTrading(): Promise<
  ApiResponse<{ session_id: string; status: string; balance: number }>
> {
  return apiPost("/backtesting/paper-trading/start");
}

export async function stopPaperTrading(
  sessionId: string
): Promise<ApiResponse<{ session_id: string; status: string }>> {
  return apiPost(`/backtesting/paper-trading/${sessionId}/stop`);
}
