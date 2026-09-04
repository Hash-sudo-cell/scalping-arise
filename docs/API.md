# Scalping Arise — API Contract Reference

All endpoints are prefixed with `/api/v1`. This document records the current API surface as of Phase 4 Core completion.

---

## Health

### `GET /api/v1/health`

System health check.

**Response:**
```json
{
  "status": "healthy",
  "service": "scalping-arise",
  "version": "1.0.0",
  "environment": "development",
  "timestamp": "2025-01-01T00:00:00Z"
}
```

---

## Market Data

### `GET /api/v1/market-data/health`

Market data subsystem health. Reports provider status without exposing secrets.

**Response:**
```json
{
  "status": "healthy",
  "primary_provider": { "name": "twelve_data", "status": "healthy" },
  "fallback_provider": { "name": "yfinance", "status": "healthy" },
  "active_source": "primary"
}
```

### `GET /api/v1/market-data/candles`

Fetch validated historical OHLCV candles.

**Parameters:**
| Name | Type | Default | Range | Description |
|------|------|---------|-------|-------------|
| `instrument` | string | `XAU/USD` | `XAU/USD` | Canonical instrument name |
| `timeframe` | string | `1h` | `1m,3m,5m,15m,30m,1h,4h,1d,1w,1mo` | Candle timeframe |
| `limit` | int | `100` | 1–5000 | Number of candles |

**Response:**
```json
{
  "instrument": "XAU/USD",
  "timeframe": "1h",
  "source": "yfinance",
  "source_type": "futures_proxy",
  "count": 100,
  "has_gaps": false,
  "candles": [
    {
      "instrument": "XAU/USD",
      "timeframe": "1h",
      "timestamp": "2025-01-01T00:00:00Z",
      "open": 2620.5,
      "high": 2625.0,
      "low": 2618.0,
      "close": 2623.0,
      "volume": 1234.0,
      "is_closed": true,
      "source": "yfinance",
      "provider_instrument": "GC=F",
      "source_type": "futures_proxy"
    }
  ]
}
```

**Source identity fields preserved in each candle:**
- `source` — Provider name (`twelve_data` or `yfinance`)
- `provider_instrument` — Symbol used by provider (`XAU/USD` or `GC=F`)
- `source_type` — Data type (`spot` or `futures_proxy`)

### `GET /api/v1/market-data/latest`

Fetch latest market price for an instrument.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `instrument` | string | `XAU/USD` | Canonical instrument name |

**Response:**
```json
{
  "instrument": "XAU/USD",
  "price": 2623.0,
  "timestamp": "2025-01-01T00:00:00Z",
  "is_forming": false,
  "source": "yfinance",
  "source_type": "futures_proxy",
  "provider_instrument": "GC=F"
}
```

### `GET /api/v1/market-data/capabilities`

Report supported instruments, timeframe capabilities, and provider details.

**Response:**
```json
{
  "instruments": ["XAU/USD"],
  "timeframes": {
    "1m": { "native": ["twelve_data", "yfinance"], "derived": [] },
    "1h": { "native": ["twelve_data", "yfinance"], "derived": [] }
  },
  "primary_provider": {
    "name": "twelve_data",
    "requires_api_key": true,
    "source_type": "spot"
  },
  "fallback_provider": {
    "name": "yfinance",
    "requires_api_key": false,
    "source_type": "futures_proxy"
  }
}
```

---

## Market Analysis

### `GET /api/v1/market-analysis/health`

Analysis engine health check.

**Response:**
```json
{
  "status": "healthy",
  "module": "market_analysis",
  "version": "1.0.0"
}
```

### `GET /api/v1/market-analysis/capabilities`

Report supported analyses and configuration.

**Response:**
```json
{
  "supported_analyses": [
    "swing_detection", "market_structure", "trend_classification",
    "bos_detection", "choch_detection", "support_resistance",
    "session_classification", "market_regime"
  ],
  "configuration": {
    "min_candles_for_analysis": 20,
    "swing_lookback": 3,
    "bos_confirmation_mode": "wick",
    "bos_min_break_pct": 0.01,
    "sr_zone_tolerance_pct": 0.1,
    "sr_min_swings": 2,
    "regime_trend_min_consecutive": 3
  },
  "supported_instruments": ["XAU/USD"],
  "supported_timeframes": ["1m","3m","5m","15m","30m","1h","4h","1d","1w","1mo"]
}
```

### `GET /api/v1/market-analysis`

Run the full market analysis pipeline.

**Parameters:**
| Name | Type | Default | Range | Description |
|------|------|---------|-------|-------------|
| `instrument` | string | `XAU/USD` | `XAU/USD` | Canonical instrument name |
| `timeframe` | string | `1h` | valid timeframes | Candle timeframe |
| `limit` | int | `200` | 20–5000 | Number of candles |

**Response:**
```json
{
  "status": "analyzed",
  "reason": "Market structure analyzed with 45 swing points",
  "analysis_timestamp": "2025-01-01T00:00:00Z",
  "context": {
    "instrument": "XAU/USD",
    "timeframe": "1h",
    "source_type": "futures_proxy",
    "candle_count": 200
  },
  "trend": {
    "classification": "bullish",
    "confidence": 0.75,
    "evidence": ["Higher highs detected", "EMA alignment bullish"]
  },
  "structure": {
    "latest_labels": ["HH", "HL", "HH"],
    "point_count": 45
  },
  "events": {
    "bos": [...],
    "choch": [...]
  },
  "zones": {
    "support": [...],
    "resistance": [...]
  },
  "session": "london",
  "regime": {
    "classification": "trending",
    "evidence": [...]
  }
}
```

**Important:** This endpoint returns descriptive analysis only. It does NOT generate trading signals or decisions.

---

## Technical Features

### `GET /api/v1/technical-features/health`

Feature engine health check. Reports configuration and indicator parameters.

**Response:**
```json
{
  "status": "healthy",
  "module": "technical_features",
  "configuration": {
    "ema_periods": [20, 50, 200],
    "rsi_period": 14,
    "macd_periods": [12, 26, 9],
    "atr_period": 14,
    "atr_thresholds": { "low_pct": 0.3, "high_pct": 1.5, "extreme_pct": 3.0 },
    "bollinger": { "period": 20, "std_dev": 2.0 },
    "volume_sma_period": 20,
    "price_lookback": 20
  }
}
```

### `GET /api/v1/technical-features/capabilities`

Report feature capabilities and minimum data requirements.

**Response:**
```json
{
  "module": "technical_features",
  "status": "active",
  "features": {
    "trend": { "ema": { "periods": [20, 50, 200] } },
    "momentum": { "rsi": { "period": 14 }, "macd": { "fast": 12, "slow": 26, "signal": 9 } },
    "volatility": { "atr": { "period": 14 }, "bollinger_bands": { "period": 20, "std_dev": 2.0 } },
    "volume": { "sma_period": 20 },
    "price": { "lookback": 20 }
  },
  "minimum_candles_required": 209
}
```

### `GET /api/v1/technical-features`

Calculate all technical features for a given timeframe.

**Parameters:**
| Name | Type | Default | Range | Description |
|------|------|---------|-------|-------------|
| `timeframe` | string | `1h` | valid timeframes | Candle timeframe |
| `limit` | int | `300` | 50–5000 | Number of candles |

**Response:**
```json
{
  "status": "available",
  "reason": "All features calculated successfully",
  "feature_set_status": "ready",
  "feature_set_reason": "All core features ready: trend, rsi, macd, atr, bollinger_bands, price",
  "volatility_classification": "normal",
  "volatility_classification_reason": "ATR% 0.800% between low (0.3%) and high (1.5%) thresholds",
  "feature_timestamp": "2025-01-01T00:00:00Z",
  "metadata": {
    "canonical_instrument": "XAU/USD",
    "provider_instrument": "GC=F",
    "provider": "yfinance",
    "source_type": "futures_proxy",
    "timeframe": "1h",
    "candle_count": 300
  },
  "trend": {
    "fast": { "period": 20, "value": 2623.5, "availability": "available", "direction": "rising", "price_relative": "above", "required_history": 20 },
    "medium": { "period": 50, "value": 2620.0, "availability": "available", "direction": "rising", "price_relative": "above", "required_history": 50 },
    "slow": { "period": 200, "value": 2580.0, "availability": "available", "direction": "rising", "price_relative": "above", "required_history": 200 },
    "alignment": "bullish",
    "alignment_evidence": ["Price > EMA20 > EMA50 > EMA200"]
  },
  "momentum": {
    "rsi": { "period": 14, "value": 62.5, "availability": "available", "state": "strong", "required_history": 15 },
    "macd": {
      "macd_line": 5.2,
      "signal_line": 3.8,
      "histogram": 1.4,
      "availability": "available",
      "macd_line_availability": "available",
      "signal_line_availability": "available",
      "histogram_availability": "available",
      "context": "bullish",
      "required_history": 35
    }
  },
  "volatility": {
    "atr": { "period": 14, "value": 21.0, "percentage": 0.8, "availability": "available", "state": "normal", "required_history": 15 },
    "bollinger_bands": { "period": 20, "std_dev": 2.0, "upper_band": 2650.0, "middle_band": 2623.0, "lower_band": 2596.0, "band_width": 2.06, "price_position": "middle_region", "availability": "available", "required_history": 20 }
  },
  "volume": { "sma_period": 20, "current_volume": 1500.0, "average_volume": 1200.0, "relative_volume": 1.25, "availability": "available", "state": "normal", "required_history": 20 },
  "price": { "current_price": 2623.0, "previous_close": 2620.5, "absolute_change": 2.5, "percentage_change": 0.095, "recent_high": 2650.0, "recent_low": 2596.0, "recent_range": 54.0, "position_in_range": 0.5, "availability": "available", "lookback": 20 },
  "availability": [
    { "name": "trend", "status": "available", "reason": "EMA alignment: bullish (EMA20=available, EMA50=available, EMA200=available)" },
    { "name": "rsi", "status": "available", "reason": "RSI(14) = 62.5" },
    { "name": "macd", "status": "available", "reason": "MACD context: bullish (MACD line=available, signal=available, histogram=available)" },
    { "name": "atr", "status": "available", "reason": "ATR(14) = 21.0" },
    { "name": "bollinger_bands", "status": "available", "reason": "Bollinger position: middle_region" },
    { "name": "volume", "status": "available", "reason": "Volume state: normal" },
    { "name": "price", "status": "available", "reason": "Price: 2623.0" }
  ]
}
```

### `GET /api/v1/technical-features/multi-timeframe`

Calculate features for multiple timeframes independently.

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `timeframes` | string | `1m,5m,15m` | Comma-separated timeframes |
| `limit` | int | `300` | Candles per timeframe (50–5000) |

**Response:**
```json
{
  "feature_set_status": "warming_up",
  "feature_set_reason": "Partial readiness (ready: 1m, 5m; warming: 15m)",
  "feature_timestamp": "2025-01-01T00:00:00Z",
  "timeframes": [
    {
      "timeframe": "1m",
      "status": "available",
      "feature_set_status": "ready",
      "volatility_classification": "low",
      "metadata": { ... },
      "trend": { ... },
      "momentum": { ... },
      "volatility": { ... },
      "volume": { ... },
      "price": { ... }
    }
  ]
}
```

**Key behavior:** Each timeframe is calculated independently from its own candle series. A single timeframe failing does not affect other timeframes.

---

## Source Identity Fields

These fields appear across multiple endpoints and must be preserved:

| Field | Description | Example Values |
|-------|-------------|----------------|
| `canonical_instrument` | User-requested instrument | `XAU/USD` |
| `provider_instrument` | Symbol used by data provider | `XAU/USD`, `GC=F` |
| `provider` | Data provider name | `twelve_data`, `yfinance` |
| `source_type` | Data classification | `spot`, `futures_proxy` |

**Never merge or simplify these fields.** They distinguish native spot data from futures proxy data.
