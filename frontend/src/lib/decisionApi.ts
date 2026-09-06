/**
 * Scalping Arise — Decision Engine API Client
 *
 * Type-safe API client for the Phase 10 decision engine endpoints.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type FinalDecisionState =
  | "evaluating"
  | "waiting"
  | "actionable"
  | "no_trade"
  | "blocked"
  | "invalid"
  | "expired"
  | "invalidated";

export type FinalDecisionDirection = "buy" | "sell" | "none";

export type GateStatus = "passed" | "failed" | "skipped" | "error";

export type GateName =
  | "emergency_disable"
  | "signal_freshness"
  | "signal_quality"
  | "signal_confidence"
  | "event_risk"
  | "strategy_state"
  | "plan_validity"
  | "plan_risk_limits"
  | "plan_rr_minimum"
  | "plan_freshness"
  | "system_readiness"
  | "conflict_check";

export interface GateResult {
  gate: GateName;
  status: GateStatus;
  reason: string;
  evaluation_ms: number;
  details: Record<string, unknown>;
}

export interface ReasonItem {
  code: string;
  message: string;
  source: string;
  weight: number;
  evidence: string[];
}

export interface ExplainabilityChain {
  summary: string;
  reasons: ReasonItem[];
  contributing_factors: string[];
  blocking_factors: string[];
  confidence_breakdown: Record<string, number>;
}

export interface ModuleContribution {
  source: string;
  module_version: string;
  data_provided: string[];
  evaluation_time_ms: number;
  healthy: boolean;
}

export interface ProvenanceRecord {
  decision_id: string;
  total_evaluation_ms: number;
  modules_healthy: number;
  modules_total: number;
  contributions: ModuleContribution[];
}

export interface ConflictDetail {
  conflict_type: string;
  description: string;
  severity: number;
  involved_components: string[];
  resolution: string;
}

export interface ConflictReport {
  has_conflicts: boolean;
  conflicts: ConflictDetail[];
  overall_severity: number;
  resolution_applied: string;
}

export interface FinalDecision {
  decision_id: string;
  state: FinalDecisionState;
  direction: FinalDecisionDirection;
  instrument: string;
  signal_id: string | null;
  plan_id: string | null;
  intelligence_id: string | null;
  confidence: number;
  quality: number;
  gates_passed: number;
  gates_failed: number;
  gates_total: number;
  rejection_reason: string | null;
  blocked_by_gate: string | null;
  created_at: string;
  updated_at: string | null;
  expires_at: string | null;
  ttl_seconds: number;
  decision_version: string;
  idempotency_key: string | null;
  gates?: GateResult[];
  explainability?: ExplainabilityChain;
  provenance?: ProvenanceRecord;
  conflicts?: ConflictReport;
}

export interface DecisionSummary {
  decision_id: string;
  state: FinalDecisionState;
  direction: FinalDecisionDirection;
  instrument: string;
  signal_id: string | null;
  confidence: number;
  quality: number;
  gates_passed: number;
  gates_failed: number;
  gates_total: number;
  rejection_reason: string | null;
  created_at: string;
  expires_at: string | null;
}

export interface EvaluateRequest {
  signal_id: string;
  instrument?: string;
  signal_direction?: string;
  signal_confidence?: number;
  signal_quality?: number;
  signal_age_seconds?: number;
  plan_id?: string;
  plan_valid?: boolean;
  plan_state?: string;
  plan_side?: string;
  plan_risk_reward?: number;
  plan_within_risk_limits?: boolean;
  plan_age_seconds?: number;
  intelligence_id?: string;
  event_decision?: string;
  strategy_performance_state?: string;
  force?: boolean;
}

export interface MonitoringCounters {
  total_evaluations: number;
  actionable_decisions: number;
  no_trade_decisions: number;
  blocked_decisions: number;
  invalid_decisions: number;
  expired_decisions: number;
  gate_failures: Record<string, number>;
  avg_evaluation_ms: number;
  emergency_disable_count: number;
  idempotency_cache_hits: number;
  idempotency_cache_misses: number;
  retention_cleanups: number;
  last_evaluation_at: string | null;
}

export interface EmergencyStatus {
  disabled: boolean;
  toggled_at: string | null;
  toggle_count: number;
  last_reason: string;
}

// ---------------------------------------------------------------------------
// API Client
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json();
}

// Health
export async function getHealth(): Promise<Record<string, unknown>> {
  return apiFetch("/decision/health");
}

// Capabilities
export async function getCapabilities(): Promise<Record<string, unknown>> {
  return apiFetch("/decision/capabilities");
}

// Evaluate
export async function evaluateDecision(
  request: EvaluateRequest,
): Promise<FinalDecision> {
  return apiFetch("/decision/evaluate", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// Get decision
export async function getDecision(
  decisionId: string,
): Promise<FinalDecision> {
  return apiFetch(`/decision/${decisionId}`);
}

// Active decisions
export async function getActiveDecisions(): Promise<{
  count: number;
  decisions: DecisionSummary[];
}> {
  return apiFetch("/decision/active");
}

// History
export async function getHistory(
  limit: number = 20,
): Promise<{ count: number; decisions: DecisionSummary[] }> {
  return apiFetch(`/decision/history?limit=${limit}`);
}

// Invalidate
export async function invalidateDecision(
  decisionId: string,
  reason: string = "Manual invalidation",
): Promise<{ success: boolean; error?: string }> {
  return apiFetch(
    `/decision/${decisionId}/invalidate?reason=${encodeURIComponent(reason)}`,
    { method: "POST" },
  );
}

// Audit trail
export async function getAuditTrail(
  decisionId: string,
): Promise<{ decision_id: string; count: number; entries: Record<string, unknown>[] }> {
  return apiFetch(`/decision/${decisionId}/audit`);
}

// Monitoring counters
export async function getCounters(): Promise<MonitoringCounters> {
  return apiFetch("/decision/monitoring/counters");
}

// Emergency toggle
export async function toggleEmergency(
  disable: boolean,
  reason: string = "Manual emergency toggle",
): Promise<{
  success: boolean;
  emergency_disable: boolean;
  message: string;
  toggled_at: string | null;
}> {
  return apiFetch("/decision/emergency/disable", {
    method: "POST",
    body: JSON.stringify({ disable, reason }),
  });
}

// Emergency status
export async function getEmergencyStatus(): Promise<EmergencyStatus> {
  return apiFetch("/decision/emergency/status");
}

// Readiness
export async function getReadiness(): Promise<Record<string, unknown>> {
  return apiFetch("/decision/readiness");
}

// Retention cleanup
export async function runRetentionCleanup(): Promise<{
  success: boolean;
  removed: number;
}> {
  return apiFetch("/decision/retention/cleanup", { method: "POST" });
}
