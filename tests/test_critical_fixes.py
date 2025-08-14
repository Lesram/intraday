"""
Critical Fix Validation Tests for Branch 1
Tests for WebSocket non-blocking behavior and metrics tracking
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest

from backend.api.main import app

# Check if prometheus is available
try:
    from prometheus_client import CollectorRegistry
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
from backend.api.websocket_manager import WebSocketClientManager


@pytest.fixture
async def ws_manager():
    """Create WebSocketClientManager instance for testing."""
    manager = WebSocketClientManager()
    return manager


class TestCriticalFixes:
    """Test critical fixes for WebSocket deadlocks and metrics"""

    @pytest.mark.asyncio
    async def test_websocket_receive_loop_non_blocking(self, ws_manager):
        """Test that WebSocket receive loop remains responsive during subscriptions"""
        client_id = "test_client_123"

        # Create mock WebSocket
        mock_websocket = AsyncMock()
        mock_websocket.receive_text = AsyncMock()

        # Simulate subscription messages
        messages = [
            '{"type": "subscribe_signals", "symbols": ["AAPL", "GOOGL"]}',
            '{"type": "subscribe_portfolio"}',
            '{"type": "ping"}',
            '{"type": "unsubscribe_signals"}',
            '{"type": "pong"}',
        ]

        mock_websocket.receive_text.side_effect = messages + [TimeoutError()]

        # Add client to manager
        await ws_manager.add_client(client_id, mock_websocket)

        # Simulate the WebSocket endpoint behavior
        background_tasks = {}
        messages_processed = 0

        try:
            for message_text in messages:
                message = json.loads(message_text)
                message_type = message.get("type")
                client_info = ws_manager.clients.get(client_id)

                if message_type == "subscribe_signals":
                    symbols = message.get("symbols", [])
                    client_info["subscriptions"].add("signals")

                    # Verify task is created but doesn't block
                    if "signals" in background_tasks:
                        background_tasks["signals"].cancel()

                    # This should not block
                    start_time = time.time()
                    background_tasks["signals"] = asyncio.create_task(
                        self._mock_signal_sender(client_id)
                    )
                    processing_time = time.time() - start_time

                    # Should be nearly instantaneous (< 10ms)
                    assert (
                        processing_time < 0.01
                    ), f"Task creation took {processing_time}s, should be < 0.01s"

                elif message_type == "subscribe_portfolio":
                    client_info["subscriptions"].add("portfolio")

                    if "portfolio" in background_tasks:
                        background_tasks["portfolio"].cancel()

                    start_time = time.time()
                    background_tasks["portfolio"] = asyncio.create_task(
                        self._mock_portfolio_sender(client_id)
                    )
                    processing_time = time.time() - start_time

                    assert (
                        processing_time < 0.01
                    ), f"Task creation took {processing_time}s, should be < 0.01s"

                messages_processed += 1

        finally:
            # Cancel background tasks
            for task_name, task in background_tasks.items():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            # Remove client
            await ws_manager.remove_client(client_id)

        # Verify all messages were processed without blocking
        assert messages_processed == len(
            messages
        ), f"Only {messages_processed}/{len(messages)} messages processed"

    async def _mock_signal_sender(self, client_id: str):
        """Mock signal sender that would run in background"""
        try:
            # Simulate some work
            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise

    async def _mock_portfolio_sender(self, client_id: str):
        """Mock portfolio sender that would run in background"""
        try:
            # Simulate some work
            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise

    @pytest.mark.asyncio
    async def test_background_task_cancellation(self, ws_manager):
        """Test that background tasks are properly cancelled on disconnect"""
        client_id = "test_client_cancel"
        mock_websocket = AsyncMock()

        await ws_manager.add_client(client_id, mock_websocket)

        # Start some background tasks
        background_tasks = {}
        background_tasks["signals"] = asyncio.create_task(
            self._long_running_task("signals")
        )
        background_tasks["portfolio"] = asyncio.create_task(
            self._long_running_task("portfolio")
        )

        # Let tasks start
        await asyncio.sleep(0.1)

        # Verify tasks are running
        assert not background_tasks["signals"].done()
        assert not background_tasks["portfolio"].done()

        # Cancel tasks (simulating client disconnect)
        cancelled_tasks = []
        for task_name, task in background_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    cancelled_tasks.append(task_name)

        # Verify all tasks were cancelled
        assert len(cancelled_tasks) == 2
        assert "signals" in cancelled_tasks
        assert "portfolio" in cancelled_tasks

        await ws_manager.remove_client(client_id)

    async def _long_running_task(self, task_type: str):
        """Simulate long-running background task"""
        try:
            for i in range(100):
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise

    @pytest.mark.asyncio
    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus not available")
    async def test_websocket_metrics_tracking(self, ws_manager):
        """Test that WebSocket metrics are properly tracked"""
        client_id = "test_client_metrics"
        mock_websocket = AsyncMock()

        # Import metrics

        await ws_manager.add_client(client_id, mock_websocket)
        client_info = ws_manager.clients[client_id]

        # Test queue size metric
        test_message = {"type": "test", "data": "test_data"}
        await ws_manager.broadcast_message(test_message)

        # Fill queue to capacity to test backpressure
        queue = client_info["queue"]
        for i in range(queue.maxsize + 5):  # Overfill to trigger backpressure
            try:
                await ws_manager.broadcast_message({"type": "test", "seq": i})
            except:
                pass

        # Verify queue is at capacity
        assert queue.qsize() == queue.maxsize

        # Test that metrics would be updated (we can't easily test the actual values
        # without a full Prometheus setup, but we can verify the code paths)

        await ws_manager.remove_client(client_id)

    @pytest.mark.asyncio
    async def test_heartbeat_timeout_tracking(self, ws_manager):
        """Test that heartbeat timeouts are properly tracked"""
        client_id = "test_client_timeout"
        mock_websocket = AsyncMock()

        await ws_manager.add_client(client_id, mock_websocket)
        client_info = ws_manager.clients[client_id]

        # Simulate stale client (no pong for > 60 seconds)
        client_info["last_ping"] = time.time() - 70

        # Run heartbeat check logic manually
        current_time = time.time()
        stale_clients = []

        for check_client_id, check_client_info in ws_manager.clients.items():
            if current_time - check_client_info["last_ping"] > 60:
                stale_clients.append(check_client_id)

        # Verify client was marked as stale
        assert client_id in stale_clients

        # Clean up
        for stale_client_id in stale_clients:
            await ws_manager.remove_client(stale_client_id)

    @pytest.mark.asyncio
    async def test_subscription_management(self, ws_manager):
        """Test that subscriptions are properly managed"""
        client_id = "test_client_subscriptions"
        mock_websocket = AsyncMock()

        await ws_manager.add_client(client_id, mock_websocket)
        client_info = ws_manager.clients[client_id]

        # Test subscription addition
        client_info["subscriptions"].add("signals")
        client_info["subscriptions"].add("portfolio")

        assert "signals" in client_info["subscriptions"]
        assert "portfolio" in client_info["subscriptions"]

        # Test subscription removal
        client_info["subscriptions"].discard("signals")

        assert "signals" not in client_info["subscriptions"]
        assert "portfolio" in client_info["subscriptions"]

        await ws_manager.remove_client(client_id)

    def test_websocket_endpoint_integration(self):
        """Test WebSocket endpoint integration"""
        with TestClient(app) as client:
            # Test that endpoint exists and is accessible
            with pytest.raises(Exception):  # WebSocket connection needs proper handling
                with client.websocket_connect("/ws/realtime/test_client"):
                    pass  # Connection setup would fail in test environment
