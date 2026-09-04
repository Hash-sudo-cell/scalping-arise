# Contributing to Scalping Arise

Thank you for considering contributing to Scalping Arise. This document explains how to set up the project, make changes, and submit them for review.

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- npm

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd scalping-arise

# Backend setup
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Frontend setup
cd ../frontend
npm install
cp .env.example .env.local
```

### Running

```bash
# Backend (from backend/)
uvicorn app.main:application --reload --host 0.0.0.0 --port 8000

# Frontend (from frontend/)
npm run dev
```

### Running Tests

```bash
# Backend tests (from backend/)
pytest -v

# Frontend tests (from frontend/)
npm test
```

---

## Branch Naming

Use descriptive branch names that indicate the phase and type of change:

```
phase-3/fix-swing-detection-edge-case
phase-4/add-bollinger-band-tests
fix/correct-source-metadata-preservation
docs/update-api-contract
```

---

## Making Changes

### Rule 1: Do Not Mix Phases

Each phase has clear responsibilities. A single pull request should address one phase or one clearly defined improvement within a phase.

Do not combine unrelated changes. If you find a bug while working on a new feature, submit the bug fix as a separate pull request.

### Rule 2: Preserve Architecture

The project uses a layered architecture:

```
Market Data → Market Analysis → Technical Features → Strategy → Signals → Risk
```

Each layer depends only on layers below it. Do not create upward dependencies. Do not merge responsibilities between layers.

### Rule 3: Preserve Source Identity

The system explicitly tracks data source identity:

- `canonical_instrument` — The instrument the user requested (e.g., XAU/USD)
- `provider_instrument` — The symbol the provider uses (e.g., XAU/USD or GC=F)
- `source_type` — Whether the data is SPOT or FUTURES_PROXY

This metadata must flow through every layer. Do not remove, simplify, or silently merge these concepts.

### Rule 4: No Look-Ahead Bias

Features at candle N must only use data from candles up to and including N. Never use future data in calculations. This is critical for eventual backtesting integrity.

### Rule 5: Add Tests

Every new module, function, or significant behavior change should have corresponding tests. Tests use hand-crafted candle data — no external API calls in the test suite.

### Rule 6: No Hardcoded Secrets

Use environment variables with the `SCALPING_ARISE_` prefix. Never commit `.env` files, API keys, tokens, or credentials.

---

## Pull Request Expectations

1. **Clear description** — Explain what changed and why.
2. **Phase identified** — State which phase the change belongs to.
3. **Tests pass** — Run `pytest -v` and confirm all tests pass.
4. **No regressions** — Existing tests must not be weakened or removed to accommodate changes.
5. **Source metadata preserved** — If your change touches data flow, verify source identity is maintained.
6. **Documentation updated** — If you change API contracts, update the relevant documentation.

---

## What Not to Do

- Do not implement Phase 5+ logic (strategies, signals, risk management) until explicitly approved.
- Do not add BUY/SELL/NO-TRADE decisions before Phase 6.
- Do not add databases, Redis, Kafka, WebSockets, or microservices unless the architecture requires it.
- Do not refactor working modules without clear justification.
- Do not change API behavior without updating tests and documentation.
- Do not hardcode secrets or configuration values.
- Do not add look-ahead bias to any calculation.

---

## Code Style

- **Python:** Follow existing patterns. Use type hints. Functions fit on screen.
- **TypeScript:** Follow existing patterns. Use strict typing.
- **Tests:** Use hand-crafted data. No external API calls. Deterministic assertions.

---

## Questions

If you are unsure about architecture decisions, ask before implementing. The existing codebase is authoritative — when in doubt, follow the patterns already established.
