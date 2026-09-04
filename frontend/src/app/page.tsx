import HealthStatus from "@/components/HealthStatus";
import MarketDataStatus from "@/components/MarketDataStatus";
import MarketAnalysisStatus from "@/components/MarketAnalysisStatus";
import TechnicalFeaturesStatus from "@/components/TechnicalFeaturesStatus";

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
        <div className="info-badge">Phase 4</div>
        <div className="info-badge">Technical Feature Engine</div>
        <div className="info-badge">v{APP_VERSION}</div>
      </div>

      <HealthStatus />
      <MarketDataStatus />
      <MarketAnalysisStatus />
      <TechnicalFeaturesStatus />

      <footer className="home-footer">
        <span>Technical Feature Engine</span>
        <span className="home-footer-sep">|</span>
        <span>Descriptive features only — no trading logic</span>
      </footer>
    </main>
  );
}
