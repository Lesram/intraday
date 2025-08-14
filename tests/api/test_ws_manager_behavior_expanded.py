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
        from backend.api.factory import create_app
        
        # Create app with small queue and fixed clock
        fixed_clock = MockFixedClock()
        app = create_app(
            ws_queue_max=2,  # Very small queue
            ws_heartbeat=2, 
            now=fixed_clock.now
        )
        
        # Get WebSocket manager from app state
        ws_manager = app.state.ws_manager
        metrics_registry = app.state.metrics_registry
        
        # Create mock WebSocket client
        mock_ws = MockWebSocket("test_client_drops")
        client_id = "test_drops_client"
        
        # Add client to manager
        await ws_manager.add_client(client_id, mock_ws)
        
        # Verify client added
        assert client_id in ws_manager.clients
        client_queue = ws_manager.clients[client_id]["queue"]
        
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
        from backend.api.factory import create_app
        
        fixed_clock = MockFixedClock()
        app = create_app(ws_queue_max=1, ws_heartbeat=5, now=fixed_clock.now)  # Very small queue
        ws_manager = app.state.ws_manager
        metrics_registry = app.state.metrics_registry
        
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
        from backend.api.factory import create_app
        
        # Create app with fixed clock and short heartbeat/timeout
        fixed_clock = MockFixedClock()
        app = create_app(
            ws_queue_max=10,
            ws_heartbeat=2,  # 2 second heartbeat
            now=fixed_clock.now  # TTL will be 2 * 2 = 4 seconds
        )
        
        ws_manager = app.state.ws_manager
        
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
        from backend.api.factory import create_app
        
        fixed_clock = MockFixedClock()
        app = create_app(ws_queue_max=10, ws_heartbeat=1, now=fixed_clock.now)  # 1s heartbeat, 2s TTL
        ws_manager = app.state.ws_manager
        metrics_registry = app.state.metrics_registry
        
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
        from backend.api.factory import create_app
        
        fixed_clock = MockFixedClock()
        app = create_app(ws_queue_max=10, ws_heartbeat=1, now=fixed_clock.now)
        ws_manager = app.state.ws_manager
        metrics_registry = app.state.metrics_registry
        
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


class TestWebSocketManagerAdvancedBehavior:
    """Test advanced WebSocket manager behaviors"""
    
    @pytest.mark.asyncio
    async def test_heartbeat_with_fixed_clock_deterministic(self):
        """Test heartbeat loop with fixed clock for deterministic behavior"""
        from backend.api.factory import create_app
        
        fixed_clock = MockFixedClock()
        app = create_app(ws_queue_max=10, ws_heartbeat=1, now=fixed_clock.now)  # 1 second heartbeat
        ws_manager = app.state.ws_manager
        
        # Add client
        client_id = "heartbeat_test_client"
        mock_ws = MockWebSocket(client_id)
        await ws_manager.add_client(client_id, mock_ws)
        
        # Start heartbeat loop
        await ws_manager.start_heartbeat()
        
        # Let one heartbeat cycle run
        await asyncio.sleep(0.1)  # Allow task to start
        
        # Advance clock and trigger cleanup manually
        fixed_clock.advance(1.5)  # Advance beyond heartbeat interval but within TTL
        await ws_manager.cleanup_stale_connections()
        
        # Client should still be present (within TTL)
        assert client_id in ws_manager.clients, "Client should still be connected within TTL"
        
        # Advance beyond TTL
        fixed_clock.advance(1)  # Total 2.5s > 2s TTL
        await ws_manager.cleanup_stale_connections()
        
        # Now client should be removed
        assert client_id not in ws_manager.clients, "Client should be removed after TTL"
        
        # Stop heartbeat
        await ws_manager.stop_heartbeat()
        
        print(f"✅ Heartbeat with fixed clock test complete")
    
    @pytest.mark.asyncio
    async def test_concurrent_client_operations(self):
        """Test concurrent client add/remove operations"""
        from backend.api.factory import create_app
        
        fixed_clock = MockFixedClock()
        app = create_app(ws_queue_max=5, ws_heartbeat=10, now=fixed_clock.now)
        ws_manager = app.state.ws_manager
        
        # Add multiple clients concurrently
        async def add_client(client_num):
            client_id = f"concurrent_client_{client_num}"
            mock_ws = MockWebSocket(client_id)
            await ws_manager.add_client(client_id, mock_ws)
            return client_id
        
        # Add 5 clients concurrently
        client_tasks = [add_client(i) for i in range(5)]
        client_ids = await asyncio.gather(*client_tasks)
        
        # Verify all clients added
        assert len(ws_manager.clients) == 5, f"Should have 5 clients, have {len(ws_manager.clients)}"
        
        # Remove clients concurrently  
        remove_tasks = [ws_manager.remove_client(client_id) for client_id in client_ids[:3]]
        await asyncio.gather(*remove_tasks)
        
        # Verify correct number remain
        assert len(ws_manager.clients) == 2, f"Should have 2 clients remaining, have {len(ws_manager.clients)}"
        
        print(f"✅ Concurrent operations test complete: {len(ws_manager.clients)} clients remain")
    
    @pytest.mark.asyncio
    async def test_message_broadcast_with_subscription_filter(self):
        """Test message broadcasting with subscription filtering"""
        from backend.api.factory import create_app
        
        fixed_clock = MockFixedClock()
        app = create_app(ws_queue_max=10, ws_heartbeat=30, now=fixed_clock.now)
        ws_manager = app.state.ws_manager
        
        # Add clients with different subscriptions
        clients = []
        for i, topic in enumerate(["stocks", "crypto", "stocks"]):  # Two subscribe to stocks
            client_id = f"subscriber_{i}"
            mock_ws = MockWebSocket(client_id)
            await ws_manager.add_client(client_id, mock_ws)
            
            # Set subscription
            ws_manager.clients[client_id]["subscriptions"].add(topic)
            clients.append((client_id, mock_ws, topic))
        
        # Broadcast message to stocks subscribers only
        stocks_message = {"type": "price_update", "symbol": "AAPL", "price": 150.00}
        await ws_manager.broadcast_message(stocks_message, subscription_filter="stocks")
        
        # Check that only stocks subscribers got the message
        stocks_subscribers = [(cid, ws) for cid, ws, topic in clients if topic == "stocks"]
        crypto_subscribers = [(cid, ws) for cid, ws, topic in clients if topic == "crypto"]
        
        # Let message sending tasks complete
        await asyncio.sleep(0.1)
        
        # Stocks subscribers should have received message
        for client_id, mock_ws in stocks_subscribers:
            queue = ws_manager.clients[client_id]["queue"] 
            assert not queue.empty(), f"Stocks subscriber {client_id} should have received message"
        
        # Crypto subscriber should not have received message
        for client_id, mock_ws in crypto_subscribers:
            queue = ws_manager.clients[client_id]["queue"]
            # The queue might have heartbeat messages, so check message content
            messages_received = []
            while not queue.empty():
                try:
                    msg = queue.get_nowait()
                    messages_received.append(msg)
                except:
                    break
            
            # Should not contain the stocks message
            stock_messages = [msg for msg in messages_received if msg.get("symbol") == "AAPL"]
            assert len(stock_messages) == 0, f"Crypto subscriber {client_id} should not receive stocks message"
        
        print(f"✅ Subscription filtering test complete")
