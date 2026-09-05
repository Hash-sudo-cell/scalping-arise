import HealthStatus from "@/components/HealthStatus";
import MarketDataStatus from "@/components/MarketDataStatus";
import MarketAnalysisStatus from "@/components/MarketAnalysisStatus";
import TechnicalFeaturesStatus from "@/components/TechnicalFeaturesStatus";
import StrategyEvaluationStatus from "@/components/StrategyEvaluationStatus";
import SignalEvaluationStatus from "@/components/SignalEvaluationStatus";
import IntelligenceStatus from "@/components/IntelligenceStatus";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME || "Scalping Arise";
const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0";

export default function Home() {
  return (
    <main className="home-main">
      <div className="home-hero">
        <h1 className="home-title">{APP_NAME}</h1>
        <p className="home-subtitle">
          XAU/USD Multi-Timeframe Scalping Signal Intelligence
        </p>
      </div>

      <div className="home-badges">
        <div className="info-badge">Phase 8</div>
        <div className="info-badge">Intelligence Engine</div>
        <div className="info-badge">v{APP_VERSION}</div>
      </div>

      <HealthStatus />
      <MarketDataStatus />
      <MarketAnalysisStatus />
      <TechnicalFeaturesStatus />
      <StrategyEvaluationStatus />
      <SignalEvaluationStatus />
      <IntelligenceStatus instrument="XAU/USD" strategyId="default" />

      <footer className="home-footer">
        <span>Intelligence Engine</span>
        <span className="home-footer-sep">|</span>
        <span>Risk context only — no execution</span>
      </footer>
    </main>
  );
}
