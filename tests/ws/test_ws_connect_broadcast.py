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
async def test_connect_broadcast_receive():
    mgr = WebSocketClientManager(queue_max=10)
    ws = DummyWebSocket()

    await mgr.register_client("c1", ws)

    await mgr.broadcast_message({"type": "tick", "v": 1})
    await mgr.broadcast_message({"type": "tick", "v": 2})

    # Allow sender task to flush
    await asyncio.sleep(0.05)

    # Expect two messages delivered
    assert len(ws.sent) == 2
    payloads = [json.loads(s) for s in ws.sent]
    assert payloads[0]["v"] == 1 and payloads[1]["v"] == 2
