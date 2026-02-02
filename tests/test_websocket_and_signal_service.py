"""
Comprehensive tests for backend.services.signal_service and backend.websocket

Targets 80%+ coverage for these modules which handle:
- Trading signal generation and management
- WebSocket client management and message broadcasting
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import pytest

from backend.services.signal_service import (
    SignalService,
    get_signal_service,
    signal_service,
)
from backend.websocket import (
    WebSocketClient,
    WebSocketClientManager,
    get_websocket_manager,
    broadcaster,
)


# ============================================================================
# SIGNAL SERVICE TESTS
# ============================================================================

class TestSignalService:
    """Tests for SignalService"""
    
    @pytest.fixture
    def service(self):
        """Create a fresh SignalService instance"""
        return SignalService()
    
    def test_init(self, service):
        """Test service initialization"""
        assert service.signals == {}
        
    @pytest.mark.asyncio
    async def test_get_signals_with_symbol(self, service):
        """Test getting signals for a specific symbol"""
        signals = await service.get_signals(symbol="GOOG")
        
        assert len(signals) == 1
        assert signals[0]["symbol"] == "GOOG"
        assert signals[0]["signal"] == "BUY"
        assert signals[0]["confidence"] == 0.75
        assert "timestamp" in signals[0]
        
    @pytest.mark.asyncio
    async def test_get_signals_without_symbol(self, service):
        """Test getting signals without specifying symbol"""
        signals = await service.get_signals()
        
        assert len(signals) == 1
        assert signals[0]["symbol"] == "AAPL"
        assert signals[0]["confidence"] == 0.8
        
    @pytest.mark.asyncio
    async def test_generate_signal(self, service):
        """Test generating a trading signal"""
        data = {"price": 150.0, "volume": 1000000}
        
        signal = await service.generate_signal("MSFT", data)
        
        assert signal["symbol"] == "MSFT"
        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 0.75
        assert signal["data"] == data
        assert "timestamp" in signal
        
    @pytest.mark.asyncio
    async def test_generate_signal_with_empty_data(self, service):
        """Test generating signal with empty data"""
        signal = await service.generate_signal("TSLA", {})
        
        assert signal["symbol"] == "TSLA"
        assert signal["data"] == {}


class TestSignalServiceGlobal:
    """Tests for global signal service"""
    
    def test_global_instance_exists(self):
        """Test global instance exists"""
        assert signal_service is not None
        assert isinstance(signal_service, SignalService)
        
    @pytest.mark.asyncio
    async def test_get_signal_service(self):
        """Test dependency injection function"""
        service = await get_signal_service()
        
        assert service is signal_service


# ============================================================================
# WEBSOCKET CLIENT TESTS
# ============================================================================

class TestWebSocketClient:
    """Tests for WebSocketClient dataclass"""
    
    def test_client_creation(self):
        """Test WebSocketClient creation"""
        ws = Mock()
        now = datetime.now(UTC)
        
        client = WebSocketClient(
            websocket=ws,
            client_id="test-client-1",
            connected_at=now,
            last_seen=now,
            subscriptions=set()
        )
        
        assert client.client_id == "test-client-1"
        assert client.websocket == ws
        assert client.connected_at == now
        assert client.subscriptions == set()
        assert client.queue_size == 100
        assert client.message_queue == []
        
    def test_client_with_subscriptions(self):
        """Test client with initial subscriptions"""
        ws = Mock()
        now = datetime.now(UTC)
        
        client = WebSocketClient(
            websocket=ws,
            client_id="test-2",
            connected_at=now,
            last_seen=now,
            subscriptions={"prices", "orders"}
        )
        
        assert "prices" in client.subscriptions
        assert "orders" in client.subscriptions
        
    def test_message_queue_initialized(self):
        """Test message queue default initialization"""
        ws = Mock()
        now = datetime.now(UTC)
        
        client = WebSocketClient(
            websocket=ws,
            client_id="test-3",
            connected_at=now,
            last_seen=now,
            subscriptions=set()
        )
        
        assert client.message_queue is not None
        assert isinstance(client.message_queue, list)


# ============================================================================
# WEBSOCKET MANAGER TESTS
# ============================================================================

class TestWebSocketClientManager:
    """Tests for WebSocketClientManager"""
    
    @pytest.fixture
    def manager(self):
        """Create fresh manager instance"""
        return WebSocketClientManager()
    
    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket"""
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        return ws
    
    def test_init(self, manager):
        """Test manager initialization"""
        assert manager.clients == {}
        assert manager.max_queue_size == 100
        assert manager.client_ttl == 300
        assert manager.metrics['connections_total'] == 0
        
    def test_register_client(self, manager, mock_websocket):
        """Test registering a client"""
        client = manager.register_client(mock_websocket, "client-1")
        
        assert client.client_id == "client-1"
        assert "client-1" in manager.clients
        assert manager.metrics['connections_total'] == 1
        
    def test_register_multiple_clients(self, manager, mock_websocket):
        """Test registering multiple clients"""
        manager.register_client(mock_websocket, "client-1")
        manager.register_client(mock_websocket, "client-2")
        manager.register_client(mock_websocket, "client-3")
        
        assert len(manager.clients) == 3
        assert manager.metrics['connections_total'] == 3
        
    def test_unregister_client(self, manager, mock_websocket):
        """Test unregistering a client"""
        manager.register_client(mock_websocket, "client-1")
        
        result = manager.unregister_client("client-1")
        
        assert result is True
        assert "client-1" not in manager.clients
        assert manager.metrics['disconnections_total'] == 1
        
    def test_unregister_nonexistent_client(self, manager):
        """Test unregistering non-existent client"""
        result = manager.unregister_client("nonexistent")
        
        assert result is False
        
    def test_subscribe_client(self, manager, mock_websocket):
        """Test subscribing client to topic"""
        manager.register_client(mock_websocket, "client-1")
        
        manager.subscribe_client("client-1", "prices")
        
        assert "prices" in manager.clients["client-1"].subscriptions
        assert "client-1" in manager.subscriptions["prices"]
        
    def test_subscribe_nonexistent_client(self, manager):
        """Test subscribing non-existent client (no error)"""
        manager.subscribe_client("nonexistent", "prices")
        
        # Should not crash
        assert "nonexistent" not in manager.clients
        
    def test_unsubscribe_client(self, manager, mock_websocket):
        """Test unsubscribing client from topic"""
        manager.register_client(mock_websocket, "client-1")
        manager.subscribe_client("client-1", "prices")
        
        manager.unsubscribe_client("client-1", "prices")
        
        assert "prices" not in manager.clients["client-1"].subscriptions
        assert "client-1" not in manager.subscriptions["prices"]
        
    def test_unsubscribe_nonexistent_client(self, manager):
        """Test unsubscribing non-existent client (no error)"""
        manager.unsubscribe_client("nonexistent", "prices")
        
        # Should not crash
        assert True
        
    @pytest.mark.asyncio
    async def test_broadcast_to_all(self, manager, mock_websocket):
        """Test broadcasting to all clients"""
        manager.register_client(mock_websocket, "client-1")
        manager.register_client(mock_websocket, "client-2")
        
        await manager.broadcast_to_all({"type": "update", "data": "test"})
        
        assert mock_websocket.send_text.call_count == 2
        assert manager.metrics['messages_sent_total'] == 2
        
    @pytest.mark.asyncio
    async def test_broadcast_to_empty(self, manager):
        """Test broadcasting with no clients"""
        await manager.broadcast_to_all({"type": "update"})
        
        # Should not crash
        assert True
        
    @pytest.mark.asyncio
    async def test_broadcast_to_topic(self, manager, mock_websocket):
        """Test broadcasting to topic subscribers"""
        manager.register_client(mock_websocket, "client-1")
        manager.register_client(mock_websocket, "client-2")
        manager.subscribe_client("client-1", "prices")
        
        await manager.broadcast_to_topic("prices", {"type": "price_update"})
        
        # Only client-1 is subscribed
        assert mock_websocket.send_text.call_count == 1
        
    @pytest.mark.asyncio
    async def test_broadcast_to_empty_topic(self, manager):
        """Test broadcasting to topic with no subscribers"""
        await manager.broadcast_to_topic("empty-topic", {"type": "test"})
        
        # Should not crash
        assert True
        
    @pytest.mark.asyncio
    async def test_send_to_client(self, manager, mock_websocket):
        """Test sending to specific client"""
        manager.register_client(mock_websocket, "client-1")
        
        result = await manager.send_to_client("client-1", {"type": "direct"})
        
        assert result is True
        mock_websocket.send_text.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_send_to_nonexistent_client(self, manager):
        """Test sending to non-existent client"""
        result = await manager.send_to_client("nonexistent", {"type": "direct"})
        
        assert result is False
        
    def test_get_statistics(self, manager, mock_websocket):
        """Test getting manager statistics"""
        manager.register_client(mock_websocket, "client-1")
        manager.subscribe_client("client-1", "prices")
        manager.subscribe_client("client-1", "orders")
        
        stats = manager.get_statistics()
        
        assert stats['active_clients'] == 1
        assert stats['total_subscriptions'] == 2
        assert stats['heartbeat_interval'] == 30
        assert 'metrics' in stats
        
    def test_get_client_count(self, manager, mock_websocket):
        """Test getting client count"""
        assert manager.get_client_count() == 0
        
        manager.register_client(mock_websocket, "client-1")
        assert manager.get_client_count() == 1
        
    def test_cleanup_stale_clients(self, manager, mock_websocket):
        """Test cleaning up stale clients"""
        manager.register_client(mock_websocket, "client-1")
        
        # Set last_seen to be beyond TTL
        from datetime import timedelta
        manager.clients["client-1"].last_seen = datetime.now(UTC) - timedelta(seconds=400)
        
        manager.cleanup_stale_clients()
        
        assert "client-1" not in manager.clients
        
    def test_cleanup_keeps_active_clients(self, manager, mock_websocket):
        """Test cleanup keeps recently active clients"""
        manager.register_client(mock_websocket, "client-1")
        # last_seen is set to now on registration, so client should remain
        
        manager.cleanup_stale_clients()
        
        assert "client-1" in manager.clients
        
    @pytest.mark.asyncio
    async def test_broadcast_json_all(self, manager, mock_websocket):
        """Test broadcast_json to all clients"""
        manager.register_client(mock_websocket, "client-1")
        manager.register_client(mock_websocket, "client-2")
        
        count = await manager.broadcast_json({"type": "json_test"})
        
        assert count == 2
        
    @pytest.mark.asyncio
    async def test_broadcast_json_specific(self, manager, mock_websocket):
        """Test broadcast_json to specific clients"""
        manager.register_client(mock_websocket, "client-1")
        manager.register_client(mock_websocket, "client-2")
        
        count = await manager.broadcast_json({"type": "json_test"}, client_ids=["client-1"])
        
        assert count == 1


# ============================================================================
# WEBSOCKET ERROR HANDLING TESTS
# ============================================================================

class TestWebSocketErrorHandling:
    """Tests for WebSocket error handling"""
    
    @pytest.fixture
    def manager(self):
        return WebSocketClientManager()
    
    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnect(self, manager):
        """Test broadcast handles client disconnect gracefully"""
        from fastapi import WebSocketDisconnect
        
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=WebSocketDisconnect())
        
        manager.register_client(ws, "client-1")
        
        await manager.broadcast_to_all({"type": "test"})
        
        # Client should be removed after disconnect
        assert "client-1" not in manager.clients
        
    @pytest.mark.asyncio
    async def test_broadcast_handles_generic_error(self, manager):
        """Test broadcast handles generic errors gracefully"""
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=Exception("Connection error"))
        
        manager.register_client(ws, "client-1")
        
        await manager.broadcast_to_all({"type": "test"})
        
        # Client should be removed after error
        assert "client-1" not in manager.clients
        
    @pytest.mark.asyncio
    async def test_send_to_client_handles_disconnect(self, manager):
        """Test send_to_client handles disconnect"""
        from fastapi import WebSocketDisconnect
        
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=WebSocketDisconnect())
        
        manager.register_client(ws, "client-1")
        
        result = await manager.send_to_client("client-1", {"type": "test"})
        
        assert result is False
        assert "client-1" not in manager.clients
        
    @pytest.mark.asyncio
    async def test_send_to_client_handles_error(self, manager):
        """Test send_to_client handles generic error"""
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=Exception("Error"))
        
        manager.register_client(ws, "client-1")
        
        result = await manager.send_to_client("client-1", {"type": "test"})
        
        assert result is False
        
    @pytest.mark.asyncio
    async def test_topic_broadcast_handles_stale_subscription(self, manager):
        """Test topic broadcast handles client that left subscription list"""
        ws = AsyncMock()
        manager.register_client(ws, "client-1")
        manager.subscribe_client("client-1", "prices")
        
        # Manually remove client but leave subscription (simulating race condition)
        del manager.clients["client-1"]
        
        # Should not crash
        await manager.broadcast_to_topic("prices", {"type": "test"})


# ============================================================================
# WEBSOCKET BACKPRESSURE TESTS
# ============================================================================

class TestWebSocketBackpressure:
    """Tests for WebSocket backpressure management"""
    
    @pytest.fixture
    def manager(self):
        return WebSocketClientManager(max_queue_size=5)
    
    @pytest.mark.asyncio
    async def test_queue_overflow_drops_oldest(self, manager):
        """Test that queue overflow drops oldest messages"""
        ws = AsyncMock()
        manager.register_client(ws, "client-1")
        manager.subscribe_client("client-1", "prices")
        
        # Fill the queue
        client = manager.clients["client-1"]
        client.message_queue = ["msg1", "msg2", "msg3", "msg4", "msg5"]
        
        await manager.broadcast_to_topic("prices", {"type": "new_msg"})
        
        # Oldest message should be dropped
        assert manager.metrics['messages_dropped_total'] == 1


# ============================================================================
# GLOBAL INSTANCE TESTS
# ============================================================================

class TestGlobalInstances:
    """Tests for global WebSocket instances"""
    
    def test_get_websocket_manager(self):
        """Test getting global manager"""
        # Reset global
        import backend.websocket as ws_module
        ws_module.websocket_manager = None
        
        manager = get_websocket_manager()
        
        assert manager is not None
        assert isinstance(manager, WebSocketClientManager)
        
    def test_get_websocket_manager_singleton(self):
        """Test global manager is singleton"""
        manager1 = get_websocket_manager()
        manager2 = get_websocket_manager()
        
        assert manager1 is manager2
        
    def test_broadcaster_exists(self):
        """Test global broadcaster exists"""
        assert broadcaster is not None
        assert isinstance(broadcaster, WebSocketClientManager)


# ============================================================================
# CLIENT SUBSCRIPTION CLEANUP TESTS
# ============================================================================

class TestSubscriptionCleanup:
    """Tests for subscription cleanup on disconnect"""
    
    def test_unregister_cleans_subscriptions(self):
        """Test that unregistering client cleans all subscriptions"""
        manager = WebSocketClientManager()
        ws = Mock()
        
        manager.register_client(ws, "client-1")
        manager.subscribe_client("client-1", "prices")
        manager.subscribe_client("client-1", "orders")
        manager.subscribe_client("client-1", "trades")
        
        manager.unregister_client("client-1")
        
        assert "client-1" not in manager.subscriptions["prices"]
        assert "client-1" not in manager.subscriptions["orders"]
        assert "client-1" not in manager.subscriptions["trades"]
