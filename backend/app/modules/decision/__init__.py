"""
Scalping Arise — Decision Engine Module (Phase 10)

Final decision, explainability, and production readiness layer.

This module is an orchestrator + safety layer. It does NOT:
  - Generate signals (Phase 6)
  - Plan trades (Phase 7)
  - Fetch market data (Phase 2)
  - Evaluate strategies (Phase 5)

It DOES:
  - Consume SignalRecord (Phase 6), TradePlan (Phase 7), IntelligenceDecision (Phase 8)
  - Run configurable gates against all inputs
  - Produce FinalDecision with full explainability, provenance, and audit trail
"""
