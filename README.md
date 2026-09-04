# Scalping Arise

XAU/USD modular trading analysis platform built as a layered architecture.

Scalping Arise analyzes market data through progressive layers — from raw market data through structure analysis, technical indicators, and eventually strategy evaluation. The system is purely analytical: it generates explainable descriptions and observations, never automatic trade execution.

**This system must never automatically execute trades or connect to a broker.**

---

## Current Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Project Foundation & Configuration | **Complete** |
| Phase 2 | Market Data Infrastructure | **Complete & Corrected** |
| Phase 3 | Market Analysis & Structure Engine | **Complete** |
| Phase 4 Core | Technical Indicators & Feature Engine | **Complete** |
| Phase 4 Extension | Multi-Timeframe, Volatility Classification, Feature Status | **Complete** |
| Phase 5 | Strategy Definition & Evaluation | **Complete** |
| Phase 6 | Signal Generation & Decision Engine | Planned |
| Phase 7 | Trade Planning & Risk Engine | Planned |
| Phase 8 | News, Events & Performance Intelligence | Planned |
| Phase 9 | Backtesting & Forward Testing | Planned |
| Phase 10 | Final Integration & Production System | Planned |

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
Signal Generation & Decision Engine
    ↓
Trade Planning & Risk Management
    ↓
News / Event & Performance Intelligence
    ↓
Backtesting & Forward Testing
    ↓
Explainability, Monitoring & Production Integration
```

Each phase has clear responsibilities. Phases do not merge responsibilities. Future phases must not be implemented until their predecessor is complete and approved.

---

## Repository Structure

```
scalping-arise/
├── backend/                          # Python — FastAPI
│   ├── app/
│   │   ├── api/v1/                   # Versioned API endpoints
│   │   │   ├── health.py             # System health
│   │   │   ├── market_data.py        # Phase 2 market data
│   │   │   ├── market_analysis.py    # Phase 3 analysis
│   │   │   ├── technical_features.py # Phase 4 features
│   │   │   └── strategies.py         # Phase 5 strategy evaluation
│   │   ├── config/                   # Centralized settings
│   │   ├── core/                     # Error handling, logging
│   │   └── modules/
│   │       ├── market_data/          # Phase 2 — Provider abstraction, caching, failover
│   │       ├── market_analysis/      # Phase 3 — Structure, trend, BOS/CHOCH, S/R, regime, liquidity
│   │       ├── technical_features/   # Phase 4 — EMA, RSI, MACD, ATR, BB, Volume, Price
│   │       └── strategies/           # Phase 5 — Definitions, eligibility, condition engine, invalidation, quality
│   ├── tests/                        # 459 tests
│   ├── .env.example                  # Environment template
│   ├── pyproject.toml                # pytest configuration
│   └── requirements.txt              # Python dependencies
├── frontend/                         # TypeScript — Next.js 15 (App Router)
│   ├── src/
│   │   ├── app/                      # Pages and layouts
│   │   ├── components/               # React components
│   │   │   ├── HealthStatus.tsx
│   │   │   ├── MarketDataStatus.tsx
│   │   │   ├── MarketAnalysisStatus.tsx
│   │   │   ├── TechnicalFeaturesStatus.tsx
│   │   │   └── StrategyEvaluationStatus.tsx
│   │   └── lib/                      # Typed API clients
│   │       ├── api.ts
│   │       ├── analysisApi.ts
│   │       ├── featuresApi.ts
│   │       └── strategiesApi.ts
│   ├── .env.example                  # Frontend environment template
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

Current baseline: **459 tests passing, 0 failures**.

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

**Parameters for candles:**
- `instrument` — Canonical instrument (default: `XAU/USD`)
- `timeframe` — Candle timeframe (default: `1h`). Options: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `1mo`
- `limit` — Number of candles (1–5000, default: 100)

### Market Analysis (Phase 3)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/market-analysis/health` | Analysis engine health |
| GET | `/api/v1/market-analysis/capabilities` | Analysis capabilities |
| GET | `/api/v1/market-analysis` | Full market analysis pipeline |

**Parameters for analysis:**
- `instrument` — Canonical instrument (default: `XAU/USD`)
- `timeframe` — Candle timeframe (default: `1h`)
- `limit` — Number of candles (20–5000, default: 200)

### Technical Features (Phase 4)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/technical-features/health` | Feature engine health |
| GET | `/api/v1/technical-features/capabilities` | Feature capabilities |
| GET | `/api/v1/technical-features` | All technical features |
| GET | `/api/v1/technical-features/multi-timeframe` | Multi-timeframe features |

**Parameters for features:**
- `timeframe` — Candle timeframe (default: `1h`)
- `limit` — Number of candles (50–5000, default: 300)

**Parameters for multi-timeframe:**
- `timeframes` — Comma-separated timeframes (default: `1m,5m,15m`)
- `limit` — Number of candles per timeframe (50–5000, default: 300)

### Strategy Evaluation (Phase 5)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/strategies/health` | Strategy engine health |
| GET | `/api/v1/strategies/capabilities` | Strategy capabilities and registered strategies |
| GET | `/api/v1/strategies` | List all strategy definitions |
| GET | `/api/v1/strategies/evaluate` | Evaluate a single strategy |
| GET | `/api/v1/strategies/evaluate-all` | Evaluate all enabled strategies |

**Parameters for evaluate:**
- `strategy_id` — Strategy to evaluate (required). Options: `trend_continuation`, `pullback_continuation`, `range_reversal`
- `instrument` — Canonical instrument (default: `XAU/USD`)
- `timeframes` — Comma-separated timeframes (default: `15m,5m,1m`)
- `candle_limit` — Candles per timeframe (default: 300)

**Parameters for evaluate-all:**
- `instrument` — Canonical instrument (default: `XAU/USD`)
- `timeframes` — Comma-separated timeframes (default: `15m,5m,1m`)
- `candle_limit` — Candles per timeframe (default: 300)

---

## Data Source Warning

The system uses two different data sources for XAU/USD:

| Source | Canonical Instrument | Provider Instrument | Source Type |
|--------|---------------------|--------------------|----|
| Twelve Data | XAU/USD | XAU/USD | SPOT |
| yfinance | XAU/USD | GC=F | FUTURES_PROXY |

**These are not identical.** GC=F is gold futures, not spot XAU/USD. The system preserves source identity throughout the pipeline. Source metadata (`source_type`, `provider_instrument`) is always included in responses.

The system must never pretend that `GC=F` is native XAU/USD spot data. They are different data sources with different characteristics.

---

## Configuration

All backend environment variables use the `SCALPING_ARISE_` prefix. See `backend/.env.example` for the complete template.

### Key Configuration Groups

- **Application** — Name, version, environment, debug mode
- **Server** — Host, port, workers, API prefix, CORS
- **Providers** — Primary (Twelve Data) and fallback (yfinance)
- **Data Freshness** — Maximum allowed data age per timeframe
- **Cache** — In-memory candle cache (TTL-based, LRU eviction)
- **Technical Features** — EMA, RSI, MACD, ATR, Bollinger, Volume, Price parameters
- **Volatility** — ATR percentage thresholds for classification

---

## Development Rules

1. **Do not mix phases.** Each phase has clear boundaries.
2. **No look-ahead bias.** Features at candle N must only use candles up to N.
3. **Preserve source metadata.** Source identity flows through the entire pipeline.
4. **Do not hardcode secrets.** Use environment variables.
5. **Add tests for new functionality.** Every module has corresponding tests.
6. **Run regression tests before declaring a phase complete.**
7. **Do not add BUY/SELL logic before Phase 6.** Phases 1-5 are descriptive only.
8. **Volume is optional.** Its absence must not cause other features to fail.
9. **One timeframe failing must not destroy other timeframes** (multi-timeframe context).

---

## License

Private — Scalping Arise Project
