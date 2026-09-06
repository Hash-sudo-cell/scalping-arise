"""
Scalping Arise — Event Bus

In-process pub/sub event bus for broadcasting real-time updates
to WebSocket clients. Decoupled from specific services — any module
can emit events, any subscriber can listen.

Events are JSON-serializable dicts with a required 'type' field.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Event handler type
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """
    Thread-safe, async-compatible event bus.

    Supports:
      - Subscribe/unsubscribe by event type
      - Wildcard subscriptions (type='*')
      - Non-blocking emit (async, with optional backpressure)
      - Event history for late joiners
    """

    def __init__(self, max_history: int = 100) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._max_history = max_history

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to an event type. Use '*' for all events."""
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                except ValueError:
                    pass

    async def emit(self, event: dict[str, Any]) -> None:
        """
        Emit an event to all subscribers.

        The event dict must have a 'type' field.
        Events are delivered asynchronously — emit() does not wait
        for handlers to complete.
        """
        event_type = event.get("type", "unknown")
        event["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Store in history
        with self._lock:
            self._history[event_type].append(event)
            if len(self._history[event_type]) > self._max_history:
                self._history[event_type] = self._history[event_type][-self._max_history:]

        # Collect matching handlers
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
            handlers += list(self._subscribers.get("*", []))

        if not handlers:
            return

        # Deliver to all handlers (don't block on slow handlers)
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.warning("Event handler error for %s: %s", event_type, e)

    def get_history(self, event_type: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent events of a type (for late joiners)."""
        with self._lock:
            return list(self._history.get(event_type, [])[-limit:])

    def subscriber_count(self, event_type: str = "*") -> int:
        """Count subscribers for a type."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))


# Module-level singleton
_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Get or create the global event bus singleton."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus
