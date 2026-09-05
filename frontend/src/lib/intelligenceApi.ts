/**
 * Scalping Arise — Intelligence API Client
 *
 * Typed API client for Phase 8: News, Event & Performance Intelligence.
 */

export interface IntelligenceEvaluation {
  decision_id: string;
  instrument: string;
  overall_decision: string;
  event_decision: string;
  strategy_state: string;
  event_data_status: string;
  restrictions: string[];
  reasons: string[];
  event_context_summary?: {
    total_events: number;
    relevant_events: number;
    high_impact_events: number;
    event_decision: string;
    freshness_status: string;
  };
  strategy_performance_context?: {
    total_trades: number;
    win_rate: number;
    net_pnl: number;
    profit_factor: number;
    max_drawdown: number;
    consecutive_losses: number;
  };
  timestamp: string;
}

export interface StrategyState {
  strategy_id: string;
  state: string;
  recovery_state: string | null;
  sample_size: number;
  state_reasons: string[];
  last_state_change: string;
  last_evaluation: string | null;
}

export interface StrategyMetrics {
  strategy_id: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  net_pnl: number;
  average_win: number;
  average_loss: number;
  profit_factor: number;
  max_drawdown: number;
  consecutive_losses: number;
  recent_win_rate: number;
  recent_trades: number;
}

export interface RecordOutcomeRequest {
  strategy_id: string;
  instrument: string;
  direction: string;
  entry_price: number;
  exit_price?: number;
  pnl: number;
  is_winner: boolean;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Evaluate intelligence for an instrument.
 */
export async function evaluateIntelligence(
  instrument: string,
  signalId?: string,
  strategyId?: string,
): Promise<IntelligenceEvaluation> {
  const response = await fetch(`${API_BASE}/api/v1/intelligence/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      instrument,
      signal_id: signalId,
      strategy_id: strategyId,
    }),
  });

  if (!response.ok) {
    throw new Error(`Intelligence evaluation failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Get current strategy state.
 */
export async function getStrategyState(
  strategyId: string,
): Promise<StrategyState> {
  const response = await fetch(
    `${API_BASE}/api/v1/intelligence/strategy-state/${strategyId}`,
  );

  if (!response.ok) {
    throw new Error(`Strategy state fetch failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Record a trade outcome for performance tracking.
 */
export async function recordOutcome(
  request: RecordOutcomeRequest,
): Promise<{ success: boolean; strategy_id: string; new_state: string; sample_size: number }> {
  const response = await fetch(`${API_BASE}/api/v1/intelligence/record-outcome`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Record outcome failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Get strategy performance metrics.
 */
export async function getMetrics(strategyId: string): Promise<StrategyMetrics> {
  const response = await fetch(
    `${API_BASE}/api/v1/intelligence/metrics/${strategyId}`,
  );

  if (!response.ok) {
    throw new Error(`Metrics fetch failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Clear intelligence data.
 */
export async function clearIntelligence(
  strategyId?: string,
): Promise<{ success: boolean }> {
  const params = strategyId ? `?strategy_id=${strategyId}` : "";
  const response = await fetch(
    `${API_BASE}/api/v1/intelligence/clear${params}`,
    { method: "DELETE" },
  );

  if (!response.ok) {
    throw new Error(`Clear intelligence failed: ${response.status}`);
  }

  return response.json();
}
