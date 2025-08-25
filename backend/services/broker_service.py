from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class BrokerService:
    """
    Minimal patch target for tests.
    The chaos tests monkeypatch methods on this class; implementations here
    are only safe defaults used when tests do not patch.
    """
    base_url: str | None = None

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok"}

    async def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        # Default "accept" behavior; chaos tests will patch this.
        return {"status": "accepted", "id": order.get("id", "test")}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return {"status": "cancelled", "id": order_id}
