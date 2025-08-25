"""
WebSocket-related helpers used by HTTP endpoints and tests.

Exposes broadcast_market_update so tests can patch backend.api.websockets.broadcast_market_update.
"""
from __future__ import annotations

from typing import Any, Mapping


async def broadcast_market_update(app, update: Mapping[str, Any]) -> None:
    """Broadcast a market update to all connected websocket clients.

    This is a thin wrapper so tests can patch it. It uses the app.state.ws_manager
    if available, and silently no-ops otherwise.
    """
    try:
        mgr = getattr(getattr(app, "state", None), "ws_manager", None)
        if mgr is None:
            return
        payload = {
            "type": "market_update",
            "symbol": update.get("symbol", "UNKNOWN"),
            "price": update.get("price", 0),
        }
        await mgr.broadcast_message(payload)
    except Exception:
        # Do not raise in tests; broadcasting is best-effort
        pass
