import asyncio
import pytest

from backend.api.websocket_manager import WebSocketClientManager


class DummyWebSocket:
    async def send_text(self, text: str):
        pass

    async def send_json(self, obj):
        pass

    async def ping(self):
        return True


@pytest.mark.asyncio
async def test_disconnect_cleans_client_and_queue():
    mgr = WebSocketClientManager(queue_max=2)
    ws = DummyWebSocket()
    await mgr.register_client("c1", ws)

    assert mgr.get_client_count() == 1
    assert "c1" in mgr.list_clients()

    await mgr.remove_client("c1")

    assert mgr.get_client_count() == 0
    assert "c1" not in mgr.list_clients()
