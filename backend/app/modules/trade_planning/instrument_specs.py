"""
Scalping Arise — Instrument Specification Registry

Provides instrument-specific trading parameters for all supported
instruments. Each specification defines tick size, contract size,
lot constraints, and pricing precision.

Phase 7 uses these specs for mathematically valid trade plan calculations.
"""

from __future__ import annotations

from typing import Optional

from app.modules.trade_planning.models import InstrumentSpecification


# ---------------------------------------------------------------------------
# Built-in instrument specifications
# ---------------------------------------------------------------------------

_SPECS: dict[str, InstrumentSpecification] = {
    "XAU/USD": InstrumentSpecification(
        instrument="XAU/USD",
        tick_size=0.01,
        contract_size=100.0,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
        price_precision=2,
        pip_value_per_lot=1.0,
        typical_spread_pips=3.0,
        margin_rate=0.05,
        trading_hours="24/5",
    ),
    "BTC/USD": InstrumentSpecification(
        instrument="BTC/USD",
        tick_size=0.01,
        contract_size=1.0,
        lot_step=0.001,
        min_lot=0.001,
        max_lot=10.0,
        price_precision=2,
        pip_value_per_lot=0.01,
        typical_spread_pips=50.0,
        margin_rate=0.10,
        trading_hours="24/7",
    ),
    "ETH/USD": InstrumentSpecification(
        instrument="ETH/USD",
        tick_size=0.01,
        contract_size=1.0,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
        price_precision=2,
        pip_value_per_lot=0.01,
        typical_spread_pips=30.0,
        margin_rate=0.10,
        trading_hours="24/7",
    ),
    "EUR/USD": InstrumentSpecification(
        instrument="EUR/USD",
        tick_size=0.00001,
        contract_size=100000.0,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
        price_precision=5,
        pip_value_per_lot=10.0,
        typical_spread_pips=1.0,
        margin_rate=0.02,
        trading_hours="24/5",
    ),
    "GBP/USD": InstrumentSpecification(
        instrument="GBP/USD",
        tick_size=0.00001,
        contract_size=100000.0,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
        price_precision=5,
        pip_value_per_lot=10.0,
        typical_spread_pips=1.5,
        margin_rate=0.02,
        trading_hours="24/5",
    ),
    "USD/JPY": InstrumentSpecification(
        instrument="USD/JPY",
        tick_size=0.001,
        contract_size=100000.0,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
        price_precision=3,
        pip_value_per_lot=6.67,
        typical_spread_pips=1.0,
        margin_rate=0.02,
        trading_hours="24/5",
    ),
    "US30": InstrumentSpecification(
        instrument="US30",
        tick_size=0.01,
        contract_size=1.0,
        lot_step=0.01,
        min_lot=0.01,
        max_lot=100.0,
        price_precision=2,
        pip_value_per_lot=0.01,
        typical_spread_pips=20.0,
        margin_rate=0.05,
        trading_hours="24/5",
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_spec(instrument: str) -> Optional[InstrumentSpecification]:
    """
    Get the trading specification for an instrument.

    Returns None if the instrument is not registered.
    """
    return _SPECS.get(instrument)


def get_spec_or_raise(instrument: str) -> InstrumentSpecification:
    """
    Get the trading specification for an instrument.

    Raises ValueError if the instrument is not registered.
    """
    spec = _SPECS.get(instrument)
    if spec is None:
        raise ValueError(f"No specification registered for instrument: {instrument}")
    return spec


def register_spec(spec: InstrumentSpecification) -> None:
    """
    Register or update an instrument specification.

    Allows runtime registration of custom instruments.
    """
    _SPECS[spec.instrument] = spec


def list_instruments() -> list[str]:
    """Return all registered instrument names."""
    return list(_SPECS.keys())


def is_instrument_supported(instrument: str) -> bool:
    """Check if an instrument has a registered specification."""
    return instrument in _SPECS
