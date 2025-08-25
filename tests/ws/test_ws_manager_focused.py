import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from backend.api.websocket_manager import WebSocketClientManager


class FakeClock:
	def __init__(self, start: datetime | None = None):
		self._now = start or datetime(2025, 1, 1, tzinfo=timezone.utc)

	def now(self) -> datetime:
		return self._now

	def advance(self, seconds: float):
		self._now = self._now + timedelta(seconds=seconds)


class FakeWebSocket:
	def __init__(self):
		self.sent_text = []
		self.sent_json = []
		self.pings = 0
		self.fail_ping = False

	async def send_text(self, text: str):
		self.sent_text.append(text)

	async def send_json(self, data):
		self.sent_json.append(data)

	async def ping(self):
		self.pings += 1
		if self.fail_ping:
			raise RuntimeError("ping failed")

	async def close(self):
		return


@pytest.mark.asyncio
async def test_queue_full_drops_oldest_and_keeps_latest():
	clock = FakeClock()
	mgr = WebSocketClientManager(queue_max=1, heartbeat_interval=1, stale_connection_timeout=5, now=clock.now)
	ws = FakeWebSocket()

	await mgr.register_client("c1", ws)
	# First message fills the queue
	await mgr.broadcast_message({"type": "t", "id": 1})
	# Second triggers drop-and-replace
	await mgr.broadcast_message({"type": "t", "id": 2})

	q = mgr.clients["c1"].queue
	assert q.qsize() == 1
	# Drain and check it's the latest
	latest = await q.get()
	assert latest["id"] == 2


@pytest.mark.asyncio
async def test_heartbeat_cleanup_removes_stale_clients():
	clock = FakeClock()
	mgr = WebSocketClientManager(queue_max=10, heartbeat_interval=1, stale_connection_timeout=5, now=clock.now)
	ws = FakeWebSocket()
	await mgr.register_client("c1", ws)

	# Make last heartbeat older than timeout
	mgr.clients["c1"].last_heartbeat = clock.now() - timedelta(seconds=10)
	await mgr.cleanup_stale_connections()

	assert "c1" not in mgr.clients


@pytest.mark.asyncio
async def test_basic_broadcast_json_sends_to_client():
	clock = FakeClock()
	mgr = WebSocketClientManager(queue_max=10, heartbeat_interval=1, stale_connection_timeout=5, now=clock.now)
	ws = FakeWebSocket()
	await mgr.register_client("c1", ws)

	msg = {"type": "heartbeat", "ok": True}
	sent = await mgr.broadcast_json(msg)

	assert sent == 1
	assert ws.sent_json and ws.sent_json[-1] == msg
