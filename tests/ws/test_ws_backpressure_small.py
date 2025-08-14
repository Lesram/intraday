import asyncio
import json
import pytest

from backend.api.websocket_manager import WebSocketClientManager


class DummyWebSocket:
    def __init__(self):
        self.sent = []

    async def send_text(self, text: str):
        self.sent.append(text)

    async def send_json(self, obj):
        self.sent.append(json.dumps(obj))

    async def ping(self):
        return True


@pytest.mark.asyncio
async def test_small_queue_overflow_drops_oldest():
    mgr = WebSocketClientManager(queue_max=1)
    ws = DummyWebSocket()
    await mgr.register_client("c1", ws)

    # Fill queue quickly; policy is drop-oldest then enqueue new
    await mgr.broadcast_message({"n": 1})
    await mgr.broadcast_message({"n": 2})
    await mgr.broadcast_message({"n": 3})

    # Allow sender to drain one or more
    await asyncio.sleep(0.05)

    # At least last message should be present in the stream
    assert any(json.loads(s).get("n") == 3 for s in ws.sent)
