"""
Scalping Arise — Event Normalizer

Converts raw provider events into NormalizedEvent objects.
Handles missing fields, invalid timestamps, and format inconsistencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.modules.news_intelligence.models import EventImpact, NormalizedEvent


def normalize_event(raw: dict[str, Any], source: str = "unknown") -> NormalizedEvent:
    """
    Normalize a raw event dict into a NormalizedEvent.

    Handles missing fields gracefully. Never raises — returns
    a valid NormalizedEvent with UNKNOWN impact if data is incomplete.
    """
    # Extract timestamp
    timestamp = _parse_timestamp(raw.get("timestamp") or raw.get("date") or raw.get("time"))

    # Extract impact
    impact = _parse_impact(raw.get("impact") or raw.get("severity"))

    # Extract affected instruments
    instruments = _extract_instruments(raw)

    # Extract currencies
    currencies = _extract_currencies(raw)

    return NormalizedEvent(
        event_id=raw.get("event_id") or raw.get("id") or str(uuid.uuid4()),
        timestamp=timestamp,
        title=raw.get("title") or raw.get("name") or raw.get("event") or "Unknown Event",
        description=raw.get("description") or raw.get("detail") or "",
        source=source,
        category=raw.get("category") or raw.get("type") or "general",
        impact=impact,
        affected_instruments=instruments,
        affected_currencies=currencies,
        created_at=datetime.now(timezone.utc),
        updated_at=_parse_timestamp(raw.get("updated_at")),
    )


def _parse_timestamp(value: Any) -> datetime:
    """Parse a timestamp from various formats. Defaults to now UTC."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(value, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
    return datetime.now(timezone.utc)


def _parse_impact(value: Any) -> EventImpact:
    """Parse impact level from various representations."""
    if isinstance(value, EventImpact):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        mapping = {
            "high": EventImpact.HIGH,
            "medium": EventImpact.MEDIUM,
            "med": EventImpact.MEDIUM,
            "low": EventImpact.LOW,
            "important": EventImpact.HIGH,
            "significant": EventImpact.MEDIUM,
            "minor": EventImpact.LOW,
        }
        return mapping.get(normalized, EventImpact.UNKNOWN)
    return EventImpact.UNKNOWN


def _extract_instruments(raw: dict[str, Any]) -> list[str]:
    """Extract affected instruments from various field names."""
    for key in ("affected_instruments", "instruments", "symbols", "assets"):
        val = raw.get(key)
        if isinstance(val, list):
            return [str(v) for v in val if v]
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
    return []


def _extract_currencies(raw: dict[str, Any]) -> list[str]:
    """Extract affected currencies from various field names."""
    for key in ("affected_currencies", "currencies", "currency", "region"):
        val = raw.get(key)
        if isinstance(val, list):
            return [str(v).upper() for v in val if v]
        if isinstance(val, str):
            return [v.strip().upper() for v in val.split(",") if v.strip()]
    return []
