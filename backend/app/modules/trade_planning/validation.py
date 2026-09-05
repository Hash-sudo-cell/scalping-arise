"""
Scalping Arise — Trade Planning Input Validation

Validates and normalizes inputs for the trade planning engine.
"""

from __future__ import annotations

from app.modules.trade_planning.instrument_specs import get_spec_or_raise, is_instrument_supported


def validate_instrument(instrument: str) -> str:
    """
    Validate and normalize an instrument string.

    Raises ValueError if instrument is not supported.
    """
    if not instrument or not instrument.strip():
        raise ValueError("Instrument cannot be empty")
    normalized = instrument.strip().upper()
    if not is_instrument_supported(normalized):
        raise ValueError(f"Unsupported instrument: {normalized}")
    return normalized


def validate_account_balance(balance: float) -> float:
    """Validate account balance is positive."""
    if balance <= 0:
        raise ValueError(f"Account balance must be positive, got {balance}")
    return balance


def validate_risk_pct(pct: float) -> float:
    """Validate risk percentage is within bounds."""
    if pct <= 0:
        raise ValueError(f"Risk percentage must be positive, got {pct}")
    if pct > 100:
        raise ValueError(f"Risk percentage cannot exceed 100, got {pct}")
    return pct


def validate_price(price: float, name: str = "price") -> float:
    """Validate a price is positive."""
    if price <= 0:
        raise ValueError(f"{name} must be positive, got {price}")
    return price
