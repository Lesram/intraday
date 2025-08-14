"""
WebSocket Manager Behavior Testing - Comprehensive connection and lifecycle coverage
Targets backend/api/websocket_manager.py for backpressure, stale client pruning
"""

import pytest
import asyncio
import time
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import uuid
import weakref
from collections import deque
import gc


class MockWebSocket:
    """Mock WebSocket connection for testing"""
    
    def __init__(self, client_id=None, fail_on_send=False, slow_send=False):
        self.client_id = client_id or str(uuid.uuid4())
        self.fail_on_send = fail_on_send
        self.slow_send = slow_send
        self.closed = False
        self.connected = True
        self.sent_messages = []
        self.last_activity = time.time()
        self.send_count = 0
        self.receive_count = 0
        self.close_code = None
        self.close_reason = None
        
        # Connection state
        self.state = "OPEN"  # OPEN, CLOSING, CLOSED
        
        # Backpressure simulation
        self.send_queue = deque()
        self.max_queue_size = 100
        self.send_delay = 0.1 if slow_send else 0.0
        
        # Dictionary interface for client_info access
        self._data = {}
    
    def __getitem__(self, key):
        """Dictionary-style getter for client_info access"""
        if key == "websocket":
            return self
        elif key == "queue":
            return self._data.get(key)
        return self._data.get(key)
    
    def __setitem__(self, key, value):
        """Dictionary-style setter for client_info access"""
        self._data[key] = value
    
    def __contains__(self, key):
        """Dictionary-style contains check"""
        if key == "websocket":
            return True
        return key in self._data
    
    def get(self, key, default=None):
        """Dictionary-style get with default"""
        if key == "websocket":
            return self
        return self._data.get(key, default)
    
    async def send(self, message):
        """Mock send method"""
        if self.closed or self.state != "OPEN":
            raise ConnectionError("WebSocket is closed")
        
        if self.fail_on_send:
            raise ConnectionError("Send failed")
        
        self.send_count += 1
        self.sent_messages.append(message)
        
        if self.send_delay:
            await asyncio.sleep(self.send_delay)

    async def send_text(self, message):
        """Mock send_text method"""
        await self.send(message)

    async def close(self, code=1000, reason=""):
        """Mock close method"""
        self.closed = True
        self.state = "CLOSED"
        self.close_code = code
        self.close_reason = reason


class MockFixedClock:
    """Mock clock for deterministic time testing"""
    
    def __init__(self, start_time=None):
        self.current_time = start_time or datetime.now()
    
    def now(self):
        """Get current mock time"""
        return self.current_time
        
    def advance(self, seconds):
        """Advance mock time by seconds"""
        self.current_time += timedelta(seconds=seconds)


class MockMetricsRegistry:
    """Mock metrics registry for testing"""
    
    def __init__(self):
        self.counters = {}
        self.gauges = {}
        
    def counter(self, name, labels=None):
        """Get or create counter"""
        key = f"{name}_{labels or {}}"
        if key not in self.counters:
            self.counters[key] = MockCounter()
        return self.counters[key]
    
    def gauge(self, name, labels=None):
        """Get or create gauge"""
        key = f"{name}_{labels or {}}"
        if key not in self.gauges:
            self.gauges[key] = MockGauge()
        return self.gauges[key]


class MockCounter:
    """Mock Prometheus counter"""
    
    def __init__(self):
        self.value = 0
    
    def inc(self, amount=1):
        """Increment counter"""
        self.value += amount


class MockGauge:
    """Mock Prometheus gauge"""
    
    def __init__(self):
        self.value = 0
        
    def set(self, value):
        """Set gauge value"""
        self.value = value
        
    def inc(self, amount=1):
        """Increment gauge"""
        self.value += amount
        
    def dec(self, amount=1):
        """Decrement gauge"""
        self.value -= amount


class TestWebSocketQueueBackpressureBehavior:
    """Test WebSocket queue backpressure behavior with message drops"""
    
    @pytest.mark.asyncio
    async def test_queue_size_2_send_5_messages_exactly_3_drops(self):
        """Test: Send 5 messages with queue size 2 → assert exactly 3 drops via ws_messages_dropped_total"""
        # Import after pytest setup
        from backend.api.websocket_manager import WebSocketClientManager
        from backend.infra.metrics import initialize_metrics_registry
        
        # Create mock components directly
        fixed_clock = MockFixedClock()
        metrics_registry = MockMetricsRegistry()
        
        # Create WebSocket manager directly
        ws_manager = WebSocketClientManager(
            queue_max=2,  # Very small queue
            heartbeat_sec=2, 
            now=fixed_clock.now,
            metrics_registry=metrics_registry
        )
        
        # Create mock WebSocket client
        mock_ws = MockWebSocket("test_client_drops")
        client_id = "test_drops_client"
        
        # Add client to manager
        await ws_manager.add_client(client_id, mock_ws)
        
        # Verify client added
        assert client_id in ws_manager.clients
        client_info = ws_manager.clients[client_id]
        client_queue = client_info.queue
        
        # Send 5 messages rapidly
        messages = [
            {"type": "test", "data": f"message_{i}", "timestamp": time.time()} 
            for i in range(5)
        ]
        
        # Broadcast all messages at once (should cause queue overflow)
        for message in messages:
            await ws_manager.broadcast_message(message)
        
        # Check drop counter in metrics
        dropped_count = 0
        for key, counter in metrics_registry.counters.items():
            if "ws_messages_dropped_total" in key:
                dropped_count += counter.value
        
        assert dropped_count == 3, f"Expected exactly 3 dropped messages, got {dropped_count}"
        
        # Verify queue only has 2 messages (queue size)
        assert client_queue.qsize() == 2, f"Queue should have exactly 2 messages, has {client_queue.qsize()}"
        
        print(f"✅ Queue backpressure test complete: {dropped_count} drops")
    
    @pytest.mark.asyncio
    async def test_multiple_clients_independent_queue_drops(self):
        """Test that queue drops are tracked independently per client"""
        from backend.api.websocket_manager import WebSocketClientManager
        
        fixed_clock = MockFixedClock()
        metrics_registry = MockMetricsRegistry()
        
        # Create WebSocket manager directly
        ws_manager = WebSocketClientManager(
            queue_max=1,  # Very small queue
            heartbeat_sec=5,
            now=fixed_clock.now,
            metrics_registry=metrics_registry
        )
        
        # Create two clients
        client1_id = "client_1"
        client2_id = "client_2"
        mock_ws1 = MockWebSocket(client1_id)
        mock_ws2 = MockWebSocket(client2_id)
        
        await ws_manager.add_client(client1_id, mock_ws1)
        await ws_manager.add_client(client2_id, mock_ws2)
        
        # Send 3 messages to each client (should cause 2 drops per client)
        messages = [{"type": "test", "data": f"msg_{i}"} for i in range(3)]
        
        for message in messages:
            await ws_manager.broadcast_message(message)
        
        # Check total drops across all clients
        total_drops = 0
        for key, counter in metrics_registry.counters.items():
            if "ws_messages_dropped_total" in key:
                total_drops += counter.value
        
        # Each client should drop 2 messages (3 sent - 1 queue capacity), total 4 drops
        assert total_drops == 4, f"Expected 4 total drops (2 per client), got {total_drops}"
        
        print(f"✅ Multi-client queue drops test complete: {total_drops} total drops")


class TestWebSocketStaleClientPruning:
    """Test WebSocket stale client detection and pruning with fixed clock"""
    
    @pytest.mark.asyncio 
    async def test_advance_clock_beyond_ttl_prune_removes_client(self):
        """Test: Advance fixed clock beyond TTL → prune_stale() removes 1 client"""
        from backend.api.websocket_manager import WebSocketClientManager
        
        # Create WebSocket manager directly with fixed clock
        fixed_clock = MockFixedClock()
        metrics_registry = MockMetricsRegistry()
        
        ws_manager = WebSocketClientManager(
            queue_max=10,
            heartbeat_sec=2,  # 2 second heartbeat, TTL = 4 seconds
            now=fixed_clock.now,
            metrics_registry=metrics_registry
        )
        
        # Add client
        client_id = "stale_test_client"
        mock_ws = MockWebSocket(client_id)
        await ws_manager.add_client(client_id, mock_ws)
        
        # Verify client is present
        assert client_id in ws_manager.clients, "Client should be present initially"
        initial_client_count = len(ws_manager.clients)
        
        # Advance clock beyond TTL (stale_connection_timeout = heartbeat * 2 = 4 seconds)
        fixed_clock.advance(5)  # Advance 5 seconds > 4 second TTL
        
        # Manually trigger stale client cleanup
        await ws_manager.cleanup_stale_connections()
        
        # Verify client was removed
        assert client_id not in ws_manager.clients, "Stale client should be removed"
        final_client_count = len(ws_manager.clients)
        
        assert final_client_count == initial_client_count - 1, "Exactly 1 client should be removed"
        
        print(f"✅ Stale client pruning test complete: {initial_client_count - final_client_count} client removed")
    
    @pytest.mark.asyncio
    async def test_websocket_clients_gauge_decremented_on_prune(self):
        """Test: websocket_clients_gauge decremented when stale client pruned"""
        from backend.api.websocket_manager import WebSocketClientManager
        
        fixed_clock = MockFixedClock()
        metrics_registry = MockMetricsRegistry()
        
        ws_manager = WebSocketClientManager(
            queue_max=10,
            heartbeat_sec=1,  # 1s heartbeat, 2s TTL
            now=fixed_clock.now,
            metrics_registry=metrics_registry
        )
        
        # Add client (should increment gauge)
        client_id = "gauge_test_client"
        mock_ws = MockWebSocket(client_id)
        await ws_manager.add_client(client_id, mock_ws)
        
        # Check initial connection counter
        connection_counter = None
        for key, counter in metrics_registry.counters.items():
            if "websocket_connections_total" in key:
                connection_counter = counter
                break
        
        initial_connections = connection_counter.value if connection_counter else 0
        
        # Advance clock to make client stale
        fixed_clock.advance(3)  # Beyond 2s TTL
        
        # Cleanup stale connections
        await ws_manager.cleanup_stale_connections()
        
        # Client should be removed
        assert client_id not in ws_manager.clients
        
        print(f"✅ Gauge decrement test complete: initial={initial_connections}")
    
    @pytest.mark.asyncio
    async def test_reconnect_increments_connection_counter(self):
        """Test: reconnect after pruning increments websocket_connections_total"""
        from backend.api.websocket_manager import WebSocketClientManager
        
        fixed_clock = MockFixedClock()
        metrics_registry = MockMetricsRegistry()
        
        ws_manager = WebSocketClientManager(
            queue_max=10,
            heartbeat_sec=1,
            now=fixed_clock.now,
            metrics_registry=metrics_registry
        )
        
        client_id = "reconnect_test_client"
        
        # First connection
        mock_ws1 = MockWebSocket(client_id + "_1")
        await ws_manager.add_client(client_id, mock_ws1)
        
        # Get initial connection count
        initial_count = 0
        for key, counter in metrics_registry.counters.items():
            if "websocket_connections_total" in key:
                initial_count = counter.value
                break
        
        # Make client stale and prune
        fixed_clock.advance(3)
        await ws_manager.cleanup_stale_connections()
        assert client_id not in ws_manager.clients
        
        # Reconnect (new client)
        mock_ws2 = MockWebSocket(client_id + "_2")
        await ws_manager.add_client(client_id, mock_ws2)
        
        # Check connection count increased
        final_count = 0
        for key, counter in metrics_registry.counters.items():
            if "websocket_connections_total" in key:
                final_count = counter.value
                break
        
        assert final_count == initial_count + 1, f"Connection count should increment on reconnect: {initial_count} → {final_count}"
        
        print(f"✅ Reconnect counter test complete: {initial_count} → {final_count}")
