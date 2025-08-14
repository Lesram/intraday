import asyncio
import json
import pytest

from backend.api.websocket_manager import WebSocketClientManager


class FakeClock:
    def __init__(self, start):
        self.t = start
    def __call__(self):
        return self.t

class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.pings = 0
    async def send_text(self, text: str):
        self.sent.append(("text", text))
    async def send_json(self, data):
        self.sent.append(("json", data))
    async def ping(self):
        self.pings += 1


@pytest.mark.asyncio
async def test_queue_full_and_broadcast_drop_policy():
    mgr = WebSocketClientManager(queue_max=1, now=lambda: FakeClock(asyncio.get_event_loop().time())())
    ws = FakeWebSocket()
    await mgr.register_client("c1", ws)

    # Fill queue
    await mgr.broadcast_message({"type": "t1"})
    # Next message should trigger drop-and-replace policy
    await mgr.broadcast_message({"type": "t2"})

    # Let sender task process
    await asyncio.sleep(0.05)

    # Last message should be present in sent messages
    assert any(json.loads(t[1])["type"] == "t2" for t in ws.sent if t[0] == "text")


@pytest.mark.asyncio
async def test_heartbeat_timeout_and_cleanup():
    # Use a manual clock we can advance
    base = asyncio.get_event_loop().time()
    clock = FakeClock(type("_T", (), {"timestamp": lambda self: base})())
    mgr = WebSocketClientManager(heartbeat_interval=0, stale_connection_timeout=1, now=lambda: clock())

    ws = FakeWebSocket()
    await mgr.register_client("c1", ws)

    # Advance clock beyond timeout and cleanup
    clock.t = type("_T", (), {"timestamp": lambda self: base + 2})()
    await mgr.cleanup_stale_connections()

    assert "c1" not in mgr.clients


@pytest.mark.asyncio
async def test_send_to_client_basic():
    mgr = WebSocketClientManager()
    ws = FakeWebSocket()
    await mgr.register_client("c1", ws)

    ok = await mgr.send_to_client("c1", {"k": 1})
    assert ok
    assert any(t[0] == "json" and t[1]["k"] == 1 for t in ws.sent)
