"""
Scalping Arise — WebSocket Realtime Endpoint

Provides /api/v1/ws for real-time event streaming.
Clients receive decision updates, signal events, and system status
as JSON messages over WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Active connections
_connections: set[WebSocket] = set()


async def _broadcast_to_clients(event: dict[str, Any]) -> None:
    """Send an event to all connected WebSocket clients."""
    if not _connections:
        return

    message = json.dumps(event, default=str)
    dead: list[WebSocket] = []

    for ws in _connections:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)

    for ws in dead:
        _connections.discard(ws)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """
    WebSocket endpoint for real-time event streaming.

    On connect:
      - Client is added to the broadcast pool
      - Recent event history is sent for context
      - Client receives all future events until disconnect

    Message format (JSON):
      {"type": "event_type", "data": {...}}

    Event types:
      - decision: New decision evaluated
      - emergency: Emergency state changed
      - signal: Signal engine event
      - system: System health/status
    """
    await ws.accept()
    _connections.add(ws)
    logger.info("WebSocket client connected (total: %d)", len(_connections))

    # Send recent history for context
    try:
        from app.modules.events import get_event_bus
        bus = get_event_bus()

        # Send recent decision events
        history = bus.get_history("decision", limit=10)
        for event in history:
            await ws.send_text(json.dumps(event, default=str))

        # Send recent emergency events
        emergency_history = bus.get_history("emergency", limit=5)
        for event in emergency_history:
            await ws.send_text(json.dumps(event, default=str))

        # Send connection confirmation
        await ws.send_text(json.dumps({
            "type": "connected",
            "message": "Real-time event stream active",
            "client_count": len(_connections),
        }))
    except Exception as e:
        logger.warning("Failed to send history to client: %s", e)

    try:
        # Keep connection alive, handle incoming messages
        while True:
            data = await ws.receive_text()
            # Client can send pings or subscription preferences
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
                elif msg_type == "subscribe":
                    # Client can request specific event types
                    await ws.send_text(json.dumps({
                        "type": "subscribed",
                        "topics": msg.get("topics", ["decision", "emergency"]),
                    }))
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
    finally:
        _connections.discard(ws)
        logger.info("WebSocket client disconnected (total: %d)", len(_connections))


def get_client_count() -> int:
    """Get the number of active WebSocket connections."""
    return len(_connections)
