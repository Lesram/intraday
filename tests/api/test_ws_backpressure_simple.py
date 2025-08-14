"""
Simplified WebSocket Backpressure Tests
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta

from backend.api.websocket_manager import WebSocketClientManager


class TestWebSocketBackpressureSimple:
    """Simplified WebSocket backpressure tests"""
    
    @pytest.fixture
    def fixed_clock(self):
        """Fixed clock for predictable testing"""
        base_time = datetime(2025, 1, 15, 9, 29, 30, tzinfo=timezone.utc)
        call_count = 0
        
        def clock_func():
            nonlocal call_count
            call_count += 1
            return base_time + timedelta(seconds=call_count)
        
        return clock_func
    
    @pytest.fixture
    def ws_manager(self, fixed_clock):
        """Create WebSocketClientManager with DI parameters"""
        mock_metrics = MagicMock()
        mock_metrics.counter.return_value = MagicMock()
        mock_metrics.gauge.return_value = MagicMock()
        
        manager = WebSocketClientManager(
            queue_max=2,
            heartbeat_sec=2,
            now_func=fixed_clock,
            metrics_registry=mock_metrics
        )
        return manager

    @pytest.mark.asyncio
    async def test_websocket_manager_creation(self, ws_manager):
        """Test that WebSocket manager can be created with DI parameters"""
        assert ws_manager.max_queue_size == 2
        assert ws_manager.heartbeat_interval == 2
        assert ws_manager.stale_connection_timeout == 4
        assert ws_manager.now_func is not None
        assert ws_manager.metrics_registry is not None
        print("✓ WebSocket manager created successfully with DI parameters")

    @pytest.mark.asyncio 
    async def test_cleanup_stale_connections(self, ws_manager, fixed_clock):
        """Test stale connection cleanup using injected clock"""
        client_id = "stale_client"
        mock_websocket = MagicMock()
        
        # Add a client manually
        now = fixed_clock()
        ws_manager.clients[client_id] = {
            "websocket": mock_websocket,
            "queue": asyncio.Queue(),
            "last_heartbeat": now - timedelta(seconds=10),  # Stale
            "subscriptions": set(),
            "send_task": None
        }
        
        # Run cleanup
        await ws_manager.cleanup_stale_connections()
        
        # Stale client should be removed
        assert client_id not in ws_manager.clients
        print("✓ Stale connection cleanup working with injected clock")

    @pytest.mark.asyncio
    async def test_broadcast_message_basic(self, ws_manager):
        """Test basic message broadcasting"""
        # Setup a client manually
        client_id = "test_client"
        mock_websocket = MagicMock()
        queue = asyncio.Queue(maxsize=2)
        
        ws_manager.clients[client_id] = {
            "websocket": mock_websocket,
            "queue": queue,
            "subscriptions": set(),
            "send_task": None
        }
        
        # Broadcast a message
        message = {"type": "test", "data": "hello"}
        await ws_manager.broadcast_message(message)
        
        # Queue should have the message
        assert queue.qsize() == 1
        queued_message = queue.get_nowait()
        assert queued_message == message
        print("✓ Message broadcasting working")
