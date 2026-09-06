# Scalping Arise

XAU/USD modular trading analysis platform built as a layered architecture.

Scalping Arise analyzes market data through progressive layers — from raw market data through structure analysis, technical indicators, and eventually strategy evaluation. The system is purely analytical: it generates explainable descriptions and observations, never automatic trade execution.

**This system must never automatically execute trades or connect to a broker.**

---

## Current Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Project Foundation & Configuration | **Complete** |
| Phase 2 | Market Data Infrastructure | **Complete** |
| Phase 3 | Market Analysis & Structure Engine | **Complete** |
| Phase 4 Core | Technical Indicators & Feature Engine | **Complete** |
| Phase 4 Extension | Multi-Timeframe, Volatility Classification, Feature Status | **Complete** |
| Phase 5 | Strategy Definition & Evaluation | **Complete** |
| Phase 5 Extension | Liquidity Integration | **Complete** |
| Phase 6 | Signal & Confirmation Layer | **Complete** |
| Phase 7 | Trade Planning & Risk Engine | **Complete** |
| Phase 8 | News, Events & Performance Intelligence | **Complete** |
| Phase 9 | Backtesting & Forward Testing | **Complete** |
| Phase 10 | Final Integration & Decision Engine | **Complete** |

---

## Architecture

**Modular Monolith** — logical modules separated within a single deployable system.

```
Market Data
    ↓
Market Structure & Regime Analysis
    ↓
Technical Indicators & Feature Engine
    ↓
Strategy Definition & Evaluation
    ↓
Signal Generation & Confidence Scoring
    ↓
Trade Planning & Risk Management
    ↓
News / Event & Performance Intelligence
    ↓
Backtesting & Forward Testing
    ↓
Decision Engine & Final Integration
```

Each phase has clear responsibilities. Phases do not merge responsibilities.

---

## Repository Structure

```
scalping-arise/
├── backend/                              # Python — FastAPI
│   ├── app/
│   │   ├── api/v1/                       # Versioned API endpoints
│   │   │   ├── health.py                 # System health
│   │   │   ├── market_data.py            # Phase 2 market data
│   │   │   ├── market_analysis.py        # Phase 3 analysis
│   │   │   ├── technical_features.py     # Phase 4 features
│   │   │   ├── strategies.py             # Phase 5 strategy evaluation
│   │   │   ├── signals.py                # Phase 6 signal evaluation
│   │   │   ├── trade_planning.py         # Phase 7 trade planning
│   │   │   ├── intelligence.py           # Phase 8 intelligence
│   │   │   ├── backtesting.py            # Phase 9 backtesting
│   │   │   └── decision.py               # Phase 10 decision engine
│   │   ├── config/                       # Centralized settings
│   │   ├── core/                         # Error handling, logging
│   │   └── modules/
│   │       ├── market_data/              # Provider abstraction, caching, validation
│   │       ├── market_analysis/          # Structure, trend, BOS/CHOCH, S/R, regime
│   │       ├── technical_features/       # EMA, RSI, MACD, ATR, BB, Volume
│   │       ├── strategies/               # Definitions, condition engine, quality
│   │       ├── signal_engine/            # Candidates, MTF, conflicts, confidence
│   │       ├── trade_planning/           # Position sizing, plans, risk, instruments
│   │       ├── news_intelligence/        # Event detection, performance tracking
│   │       ├── backtesting/              # Simulators, analytics, runner, paper trading
│   │       └── decision/                 # Gates, merge, explainability, audit, emergency
│   ├── tests/                            # 1022 tests
│   ├── .env.example                      # Environment template
│   ├── pyproject.toml                    # pytest configuration
│   └── requirements.txt                  # Python dependencies
├── frontend/                             # TypeScript — Next.js 15 (App Router)
│   ├── src/
│   │   ├── app/                          # Pages and layouts
│   │   ├── components/                   # React components
│   │   │   ├── HealthStatus.tsx
│   │   │   ├── MarketDataStatus.tsx
│   │   │   ├── MarketAnalysisStatus.tsx
│   │   │   ├── TechnicalFeaturesStatus.tsx
│   │   │   ├── StrategyEvaluationStatus.tsx
│   │   │   ├── SignalEvaluationStatus.tsx
│   │   │   ├── IntelligenceStatus.tsx
│   │   │   ├── TradePlanStatus.tsx
│   │   │   ├── BacktestStatus.tsx
│   │   │   └── DecisionStatus.tsx
│   │   └── lib/                          # Typed API clients
│   │       ├── api.ts
│   │       ├── analysisApi.ts
│   │       ├── featuresApi.ts
│   │       ├── strategiesApi.ts
│   │       ├── signalsApi.ts
│   │       ├── tradePlanningApi.ts
│   │       ├── intelligenceApi.ts
│   │       ├── backtestingApi.ts
│   │       └── decisionApi.ts
│   ├── .env.example                      # Frontend environment template
│   ├── package.json
│   └── tsconfig.json
├── .gitignore
├── README.md
└── CONTRIBUTING.md
```

---

## Prerequisites

- **Python 3.12+**
- **Node.js 18+**
- **npm** (comes with Node.js)
- **Twelve Data API key** (optional — system falls back to yfinance without one)

---

## Backend Setup

```bash
cd backend

# Create virtual environment (first time only)
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# (Optional) Add your Twelve Data API key to .env
# Without it, the system uses yfinance fallback only

# Start development server
uvicorn app.main:application --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

In development mode:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Frontend Setup

```bash
cd frontend

# Install dependencies (first time only)
npm install

# Copy environment template
cp .env.example .env.local

# Start development server
npm run dev
```

The frontend will be available at `http://localhost:3000`.

---

## Testing

### Backend

```bash
cd backend
pytest -v
```

Current baseline: **1022 tests passing, 0 failures**.

### Frontend

```bash
cd frontend
npm test
```

---

## API Overview

All endpoints are prefixed with `/api/v1`.

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | System health check |

### Market Data (Phase 2)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/market-data/health` | Provider health status |
| GET | `/api/v1/market-data/candles` | Historical OHLCV candles |
| GET | `/api/v1/market-data/latest` | Latest market price |
| GET | `/api/v1/market-data/capabilities` | Provider capabilities |

### Market Analysis (Phase 3)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/market-analysis/health` | Analysis engine health |
| GET | `/api/v1/market-analysis/capabilities` | Analysis capabilities |
| GET | `/api/v1/market-analysis` | Full market analysis pipeline |

### Technical Features (Phase 4)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/technical-features/health` | Feature engine health |
| GET | `/api/v1/technical-features/capabilities` | Feature capabilities |
| GET | `/api/v1/technical-features` | All technical features |
| GET | `/api/v1/technical-features/multi-timeframe` | Multi-timeframe features |

### Strategy Evaluation (Phase 5)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/strategies/health` | Strategy engine health |
| GET | `/api/v1/strategies/capabilities` | Strategy capabilities |
| GET | `/api/v1/strategies` | List all strategy definitions |
| GET | `/api/v1/strategies/evaluate` | Evaluate a single strategy |
| GET | `/api/v1/strategies/evaluate-all` | Evaluate all enabled strategies |

### Signal Evaluation (Phase 6)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/signals/health` | Signal engine health |
| GET | `/api/v1/signals/capabilities` | Signal engine capabilities |
| GET | `/api/v1/signals/evaluate` | Full signal evaluation pipeline |

### Trade Planning (Phase 7)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/trade-planning/health` | Trade planning health |
| POST | `/api/v1/trade-planning/generate` | Generate a trade plan |
| GET | `/api/v1/trade-planning/validate` | Validate a plan |
| GET | `/api/v1/trade-planning/instruments` | Instrument specifications |

### Intelligence (Phase 8)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/intelligence/evaluate` | Evaluate intelligence |
| GET | `/api/v1/intelligence/strategy-state/{id}` | Strategy state |
| POST | `/api/v1/intelligence/record-outcome` | Record trade outcome |
| GET | `/api/v1/intelligence/metrics/{id}` | Strategy metrics |

### Backtesting (Phase 9)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/backtesting/run` | Run a backtest |
| GET | `/api/v1/backtesting/runs` | List backtest runs |
| GET | `/api/v1/backtesting/runs/{id}` | Get a specific run |
| GET | `/api/v1/backtesting/runs/{id}/trades` | Get trades for a run |
| GET | `/api/v1/backtesting/runs/{id}/analytics` | Get analytics |
| DELETE | `/api/v1/backtesting/runs/{id}` | Delete a run |
| GET | `/api/v1/backtesting/health` | Backtesting health |
| POST | `/api/v1/backtesting/paper-trading/start` | Start paper trading |
| POST | `/api/v1/backtesting/paper-trading/{id}/stop` | Stop paper trading |

### Decision Engine (Phase 10)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/decision/health` | Decision engine health |
| GET | `/api/v1/decision/capabilities` | Decision engine capabilities |
| POST | `/api/v1/decision/evaluate` | Evaluate a decision |
| GET | `/api/v1/decision/{id}` | Get a specific decision |
| GET | `/api/v1/decision/active` | Get active decisions |
| GET | `/api/v1/decision/history` | Get decision history |
| POST | `/api/v1/decision/{id}/invalidate` | Invalidate a decision |
| GET | `/api/v1/decision/{id}/audit` | Get audit trail |
| GET | `/api/v1/decision/monitoring/counters` | Monitoring counters |
| POST | `/api/v1/decision/emergency/disable` | Toggle emergency kill switch |
| GET | `/api/v1/decision/emergency/status` | Emergency status |
| GET | `/api/v1/decision/readiness` | System readiness |
| POST | `/api/v1/decision/retention/cleanup` | Run retention cleanup |

---

## Data Source Warning

The system uses two different data sources for XAU/USD:

| Source | Canonical Instrument | Provider Instrument | Source Type |
|--------|---------------------|--------------------|----|
| Twelve Data | XAU/USD | XAU/USD | SPOT |
| yfinance | XAU/USD | GC=F | FUTURES_PROXY |

**These are not identical.** GC=F is gold futures, not spot XAU/USD. The system preserves source identity throughout the pipeline.

---

## Configuration

All backend environment variables use the `SCALPING_ARISE_` prefix. See `backend/.env.example` for the complete template.

---

## License

Private — Scalping Arise Project
