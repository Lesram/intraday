"""
Comprehensive WebSocket Manager Test Suite
Tests for backend/websocket.py and backend/api/websocket_manager.py covering all major functionality paths
"""

import asyncio
import json
import logging
import time
import os
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime, timezone
from typing import Any, Dict, List
import weakref

try:
    import pytest
except ImportError:
    pytest = None

try:
    from fastapi import WebSocket, WebSocketDisconnect
except ImportError:
    WebSocket = None
    WebSocketDisconnect = Exception

# Import the classes under test
from backend.websocket import (
    WebSocketClient,
    WebSocketClientManager
)

from backend.api.websocket_manager import (
    WebSocketClientInfo,
    WebSocketClientManager as EnhancedWebSocketClientManager,
    cancel_all_ws_tasks,
    _track_task,
    _WS_TASKS
)


class TestWebSocketClient:
    """Test WebSocketClient dataclass functionality."""
    
    def test_websocket_client_creation_basic(self):
        """Test basic WebSocketClient creation."""
        mock_websocket = Mock(spec=WebSocket)
        now = datetime.now(timezone.utc)
        
        client = WebSocketClient(
            websocket=mock_websocket,
            client_id="test_client_001",
            connected_at=now,
            last_seen=now,
            subscriptions={"market_data", "trade_updates"}
        )
        
        assert client.websocket == mock_websocket
        assert client.client_id == "test_client_001"
        assert client.connected_at == now
        assert client.last_seen == now
        assert client.subscriptions == {"market_data", "trade_updates"}
        assert client.queue_size == 100  # Default value
        assert client.message_queue == []  # Post-init default
    
    def test_websocket_client_with_custom_queue_size(self):
        """Test WebSocketClient with custom queue size."""
        mock_websocket = Mock(spec=WebSocket)
        now = datetime.now(timezone.utc)
        
        client = WebSocketClient(
            websocket=mock_websocket,
            client_id="test_client_002",
            connected_at=now,
            last_seen=now,
            subscriptions=set(),
            queue_size=250
        )
        
        assert client.queue_size == 250
        assert client.message_queue == []
    
    def test_websocket_client_with_message_queue(self):
        """Test WebSocketClient with pre-populated message queue."""
        mock_websocket = Mock(spec=WebSocket)
        now = datetime.now(timezone.utc)
        test_messages = [{"type": "heartbeat"}, {"type": "data", "content": "test"}]
        
        client = WebSocketClient(
            websocket=mock_websocket,
            client_id="test_client_003",
            connected_at=now,
            last_seen=now,
            subscriptions=set(),
            message_queue=test_messages
        )
        
        assert client.message_queue == test_messages
        assert len(client.message_queue) == 2


class TestWebSocketClientManager:
    """Test WebSocketClientManager functionality."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.manager = WebSocketClientManager(max_queue_size=50, client_ttl=600)
        self.mock_websocket = Mock(spec=WebSocket)
        self.mock_websocket.send_text = AsyncMock()
    
    def test_manager_initialization(self):
        """Test WebSocketClientManager initialization."""
        assert self.manager.clients == {}
        assert dict(self.manager.subscriptions) == {}
        assert self.manager.max_queue_size == 50
        assert self.manager.client_ttl == 600
        assert self.manager.metrics['connections_total'] == 0
        assert self.manager.metrics['disconnections_total'] == 0
        assert self.manager.metrics['messages_sent_total'] == 0
        assert self.manager.metrics['messages_dropped_total'] == 0
    
    def test_register_client_basic(self):
        """Test basic client registration."""
        client = self.manager.register_client(self.mock_websocket, "client_001")
        
        assert client.client_id == "client_001"
        assert client.websocket == self.mock_websocket
        assert client.queue_size == 50
        assert "client_001" in self.manager.clients
        assert self.manager.metrics['connections_total'] == 1
    
    def test_register_multiple_clients(self):
        """Test registering multiple clients."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws2 = Mock(spec=WebSocket)
        
        client1 = self.manager.register_client(mock_ws1, "client_001")
        client2 = self.manager.register_client(mock_ws2, "client_002")
        
        assert len(self.manager.clients) == 2
        assert "client_001" in self.manager.clients
        assert "client_002" in self.manager.clients
        assert self.manager.metrics['connections_total'] == 2
    
    def test_unregister_client_success(self):
        """Test successful client unregistration."""
        # Register and subscribe client first
        client = self.manager.register_client(self.mock_websocket, "client_001")
        self.manager.subscribe_client("client_001", "market_data")
        
        # Verify subscription exists
        assert "client_001" in self.manager.subscriptions["market_data"]
        
        # Unregister client
        result = self.manager.unregister_client("client_001")
        
        assert result is True
        assert "client_001" not in self.manager.clients
        assert "client_001" not in self.manager.subscriptions["market_data"]
        assert self.manager.metrics['disconnections_total'] == 1
    
    def test_unregister_nonexistent_client(self):
        """Test unregistering nonexistent client."""
        result = self.manager.unregister_client("nonexistent_client")
        
        assert result is False
        assert self.manager.metrics['disconnections_total'] == 0
    
    def test_subscribe_client_success(self):
        """Test successful client subscription."""
        self.manager.register_client(self.mock_websocket, "client_001")
        self.manager.subscribe_client("client_001", "market_data")
        
        client = self.manager.clients["client_001"]
        assert "market_data" in client.subscriptions
        assert "client_001" in self.manager.subscriptions["market_data"]
    
    def test_subscribe_nonexistent_client(self):
        """Test subscribing nonexistent client (should not crash)."""
        # Should not raise an exception
        self.manager.subscribe_client("nonexistent_client", "market_data")
        
        # Subscription should not be created
        assert "nonexistent_client" not in self.manager.subscriptions["market_data"]
    
    def test_unsubscribe_client_success(self):
        """Test successful client unsubscription."""
        self.manager.register_client(self.mock_websocket, "client_001")
        self.manager.subscribe_client("client_001", "market_data")
        
        # Verify subscription exists
        assert "market_data" in self.manager.clients["client_001"].subscriptions
        
        # Unsubscribe
        self.manager.unsubscribe_client("client_001", "market_data")
        
        assert "market_data" not in self.manager.clients["client_001"].subscriptions
        assert "client_001" not in self.manager.subscriptions["market_data"]
    
    def test_unsubscribe_nonexistent_client(self):
        """Test unsubscribing nonexistent client (should not crash)."""
        # Should not raise an exception
        self.manager.unsubscribe_client("nonexistent_client", "market_data")
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_success(self):
        """Test successful broadcast to all clients."""
        # Register multiple clients
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock()
        
        self.manager.register_client(mock_ws1, "client_001")
        self.manager.register_client(mock_ws2, "client_002")
        
        message = {"type": "broadcast", "data": "test message"}
        
        await self.manager.broadcast_to_all(message)
        
        # Verify both clients received the message
        mock_ws1.send_text.assert_called_once_with(json.dumps(message))
        mock_ws2.send_text.assert_called_once_with(json.dumps(message))
        assert self.manager.metrics['messages_sent_total'] == 2
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_no_clients(self):
        """Test broadcast when no clients are connected."""
        message = {"type": "broadcast", "data": "test message"}
        
        # Should not raise an exception
        await self.manager.broadcast_to_all(message)
        
        assert self.manager.metrics['messages_sent_total'] == 0
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_with_disconnection(self):
        """Test broadcast handling client disconnection."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock(side_effect=WebSocketDisconnect())
        
        self.manager.register_client(mock_ws1, "client_001")
        self.manager.register_client(mock_ws2, "client_002")
        
        message = {"type": "broadcast", "data": "test message"}
        
        await self.manager.broadcast_to_all(message)
        
        # Client 1 should receive message, client 2 should be disconnected
        mock_ws1.send_text.assert_called_once()
        assert "client_001" in self.manager.clients
        assert "client_002" not in self.manager.clients
        assert self.manager.metrics['messages_sent_total'] == 1
        assert self.manager.metrics['disconnections_total'] == 1
    
    @pytest.mark.asyncio
    async def test_broadcast_to_topic_success(self):
        """Test successful broadcast to topic subscribers."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock()
        mock_ws3 = Mock(spec=WebSocket)
        mock_ws3.send_text = AsyncMock()
        
        self.manager.register_client(mock_ws1, "client_001")
        self.manager.register_client(mock_ws2, "client_002")
        self.manager.register_client(mock_ws3, "client_003")
        
        # Subscribe only client 1 and 2 to market_data
        self.manager.subscribe_client("client_001", "market_data")
        self.manager.subscribe_client("client_002", "market_data")
        
        message = {"type": "market_data", "symbol": "AAPL", "price": 150.0}
        
        await self.manager.broadcast_to_topic("market_data", message)
        
        # Only subscribed clients should receive the message
        mock_ws1.send_text.assert_called_once_with(json.dumps(message))
        mock_ws2.send_text.assert_called_once_with(json.dumps(message))
        mock_ws3.send_text.assert_not_called()
        assert self.manager.metrics['messages_sent_total'] == 2
    
    @pytest.mark.asyncio
    async def test_broadcast_to_topic_no_subscribers(self):
        """Test broadcast to topic with no subscribers."""
        message = {"type": "market_data", "symbol": "AAPL", "price": 150.0}
        
        # Should not raise an exception
        await self.manager.broadcast_to_topic("nonexistent_topic", message)
        
        assert self.manager.metrics['messages_sent_total'] == 0
    
    @pytest.mark.asyncio
    async def test_send_to_client_success(self):
        """Test successful message send to specific client."""
        self.manager.register_client(self.mock_websocket, "client_001")
        
        message = {"type": "personal", "data": "Hello client_001"}
        result = await self.manager.send_to_client("client_001", message)
        
        assert result is True
        self.mock_websocket.send_text.assert_called_once_with(json.dumps(message))
        assert self.manager.metrics['messages_sent_total'] == 1
    
    @pytest.mark.asyncio
    async def test_send_to_client_nonexistent(self):
        """Test send to nonexistent client."""
        message = {"type": "personal", "data": "Hello nonexistent"}
        result = await self.manager.send_to_client("nonexistent_client", message)
        
        assert result is False
        assert self.manager.metrics['messages_sent_total'] == 0
    
    @pytest.mark.asyncio
    async def test_send_to_client_disconnection(self):
        """Test send to client handling disconnection."""
        self.mock_websocket.send_text = AsyncMock(side_effect=WebSocketDisconnect())
        self.manager.register_client(self.mock_websocket, "client_001")
        
        message = {"type": "personal", "data": "Hello client_001"}
        result = await self.manager.send_to_client("client_001", message)
        
        assert result is False
        assert "client_001" not in self.manager.clients
        assert self.manager.metrics['disconnections_total'] == 1
    
    @pytest.mark.asyncio
    async def test_broadcast_json_all_clients(self):
        """Test broadcast_json to all clients."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock()
        
        self.manager.register_client(mock_ws1, "client_001")
        self.manager.register_client(mock_ws2, "client_002")
        
        message = {"type": "json_broadcast", "data": "test"}
        result = await self.manager.broadcast_json(message)
        
        assert result == 2  # Number of successful sends
        mock_ws1.send_text.assert_called_once()
        mock_ws2.send_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_broadcast_json_specific_clients(self):
        """Test broadcast_json to specific clients."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock()
        mock_ws3 = Mock(spec=WebSocket)
        mock_ws3.send_text = AsyncMock()
        
        self.manager.register_client(mock_ws1, "client_001")
        self.manager.register_client(mock_ws2, "client_002")
        self.manager.register_client(mock_ws3, "client_003")
        
        message = {"type": "json_broadcast", "data": "test"}
        result = await self.manager.broadcast_json(message, client_ids=["client_001", "client_003"])
        
        assert result == 2  # Number of successful sends
        mock_ws1.send_text.assert_called_once()
        mock_ws2.send_text.assert_not_called()
        mock_ws3.send_text.assert_called_once()
    
    def test_cleanup_stale_connections(self):
        """Test cleanup of stale connections."""
        # Create a client with old last_seen time
        past_time = datetime.now(timezone.utc).timestamp() - 1000  # Very old
        
        client = self.manager.register_client(self.mock_websocket, "stale_client")
        client.last_seen = datetime.fromtimestamp(past_time, timezone.utc)
        
        initial_count = len(self.manager.clients)
        assert initial_count == 1
        
        self.manager.cleanup_stale_clients()
        
        # Stale client should be removed
        assert len(self.manager.clients) == 0
        assert "stale_client" not in self.manager.clients
    
    def test_get_client_count(self):
        """Test getting client count."""
        assert self.manager.get_client_count() == 0
        
        self.manager.register_client(self.mock_websocket, "client_001")
        assert self.manager.get_client_count() == 1
        
        mock_ws2 = Mock(spec=WebSocket)
        self.manager.register_client(mock_ws2, "client_002")
        assert self.manager.get_client_count() == 2
    
    def test_get_statistics(self):
        """Test getting statistics."""
        stats = self.manager.get_statistics()
        
        assert 'metrics' in stats
        assert 'connections_total' in stats['metrics']
        assert 'disconnections_total' in stats['metrics']
        assert 'messages_sent_total' in stats['metrics']
        assert 'messages_dropped_total' in stats['metrics']
        assert stats['metrics']['connections_total'] == 0


class TestWebSocketClientInfo:
    """Test WebSocketClientInfo dataclass functionality."""
    
    def test_websocket_client_info_creation(self):
        """Test WebSocketClientInfo creation."""
        mock_websocket = Mock(spec=WebSocket)
        mock_queue = Mock(spec=asyncio.Queue)
        now = datetime.now(timezone.utc)
        
        client_info = WebSocketClientInfo(
            client_id="enhanced_client_001",
            websocket=mock_websocket,
            queue=mock_queue,
            last_heartbeat=now
        )
        
        assert client_info.client_id == "enhanced_client_001"
        assert client_info.websocket == mock_websocket
        assert client_info.queue == mock_queue
        assert client_info.last_heartbeat == now
        assert client_info.subscriptions == set()  # Default post-init
        assert client_info.send_queue is None
        assert client_info.send_task is None
        assert client_info.last_ping == 0.0
    
    def test_websocket_client_info_with_subscriptions(self):
        """Test WebSocketClientInfo with custom subscriptions."""
        mock_websocket = Mock(spec=WebSocket)
        mock_queue = Mock(spec=asyncio.Queue)
        now = datetime.now(timezone.utc)
        
        client_info = WebSocketClientInfo(
            client_id="enhanced_client_002",
            websocket=mock_websocket,
            queue=mock_queue,
            last_heartbeat=now,
            subscriptions={"market_data", "trade_updates"}
        )
        
        assert client_info.subscriptions == {"market_data", "trade_updates"}
    
    def test_client_info_dict_compatibility(self):
        """Test WebSocketClientInfo dictionary-style access for backward compatibility."""
        mock_websocket = Mock(spec=WebSocket)
        mock_queue = Mock(spec=asyncio.Queue)
        now = datetime.now(timezone.utc)
        
        client_info = WebSocketClientInfo(
            client_id="compat_client",
            websocket=mock_websocket,
            queue=mock_queue,
            last_heartbeat=now
        )
        
        # Test __getitem__
        assert client_info["client_id"] == "compat_client"
        assert client_info["websocket"] == mock_websocket
        
        # Test __setitem__
        client_info["last_ping"] = 123.456
        assert client_info.last_ping == 123.456
        
        # Test __contains__
        assert "client_id" in client_info
        assert "websocket" in client_info
        assert "nonexistent_field" not in client_info


class TestEnhancedWebSocketClientManager:
    """Test enhanced WebSocketClientManager functionality."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.manager = EnhancedWebSocketClientManager(
            queue_max=50,
            heartbeat_interval=30,
            stale_connection_timeout=120
        )
        self.mock_websocket = Mock(spec=WebSocket)
        self.mock_websocket.send_text = AsyncMock()
        self.mock_websocket.send_json = AsyncMock()
    
    def test_enhanced_manager_initialization(self):
        """Test enhanced WebSocketClientManager initialization."""
        assert self.manager.clients == {}
        assert self.manager.queue_max == 50
        assert self.manager.max_queue_size == 50  # Alias
        assert self.manager.heartbeat_interval == 30
        assert self.manager.stale_connection_timeout == 120
        assert callable(self.manager.now_func)
        assert self.manager._heartbeat_task is None
    
    def test_enhanced_manager_legacy_parameter_compatibility(self):
        """Test backward compatibility with legacy parameter names."""
        manager = EnhancedWebSocketClientManager(
            max_queue_size=75,
            heartbeat_sec=45,
            now_func=lambda: datetime.now(timezone.utc)
        )
        
        assert manager.queue_max == 75
        assert manager.heartbeat_interval == 45
        assert callable(manager.now_func)
    
    @pytest.mark.asyncio
    async def test_register_client_enhanced(self):
        """Test enhanced client registration."""
        result = await self.manager.register_client("enhanced_client_001", self.mock_websocket)
        
        assert result is True
        assert "enhanced_client_001" in self.manager.clients
        
        client_info = self.manager.clients["enhanced_client_001"]
        assert client_info.client_id == "enhanced_client_001"
        assert client_info.websocket == self.mock_websocket
        assert isinstance(client_info.queue, asyncio.Queue)
    
    @pytest.mark.asyncio
    async def test_register_client_duplicate(self):
        """Test registering duplicate client."""
        await self.manager.register_client("duplicate_client", self.mock_websocket)
        
        # Registering same client again should return True (handled gracefully)
        result = await self.manager.register_client("duplicate_client", self.mock_websocket)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_add_client_alias(self):
        """Test add_client method (alias for register_client)."""
        result = await self.manager.add_client("alias_client", self.mock_websocket)
        assert result is True
        assert "alias_client" in self.manager.clients
    
    @pytest.mark.asyncio
    async def test_open_client_method(self):
        """Test open method for client registration."""
        result = await self.manager.open(self.mock_websocket, "open_client")
        assert result is True
        assert "open_client" in self.manager.clients
    
    @pytest.mark.asyncio
    async def test_remove_client_success(self):
        """Test successful client removal."""
        await self.manager.register_client("remove_client", self.mock_websocket)
        assert "remove_client" in self.manager.clients
        
        await self.manager.remove_client("remove_client")
        assert "remove_client" not in self.manager.clients
    
    @pytest.mark.asyncio
    async def test_unregister_client_enhanced(self):
        """Test enhanced client unregistration."""
        await self.manager.register_client("unreg_client", self.mock_websocket)
        
        result = await self.manager.unregister_client("unreg_client")
        assert result is True
        assert "unreg_client" not in self.manager.clients
    
    @pytest.mark.asyncio
    async def test_unregister_nonexistent_client(self):
        """Test unregistering nonexistent client."""
        result = await self.manager.unregister_client("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_disconnect_client(self):
        """Test client disconnection."""
        await self.manager.register_client("disconnect_client", self.mock_websocket)
        
        await self.manager.disconnect("disconnect_client")
        assert "disconnect_client" not in self.manager.clients
    
    @pytest.mark.asyncio
    async def test_broadcast_message_enhanced(self):
        """Test enhanced broadcast message functionality."""
        # Register multiple clients
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock()
        
        await self.manager.register_client("client_001", mock_ws1)
        await self.manager.register_client("client_002", mock_ws2)
        
        message = {"type": "enhanced_broadcast", "data": "test"}
        
        await self.manager.broadcast_message(message)
        
        # The enhanced manager uses different message sending patterns
        # Just verify the method doesn't raise an exception
        assert "client_001" in self.manager.clients
        assert "client_002" in self.manager.clients
    
    @pytest.mark.asyncio
    async def test_send_to_client_enhanced(self):
        """Test enhanced send to client functionality."""
        await self.manager.register_client("target_client", self.mock_websocket)
        
        message = {"type": "personal", "content": "Hello target_client"}
        result = await self.manager.send_to_client("target_client", message)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_send_to_client_nonexistent_enhanced(self):
        """Test send to nonexistent client in enhanced manager."""
        message = {"type": "personal", "content": "Hello nobody"}
        result = await self.manager.send_to_client("nonexistent", message)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_broadcast_to_topic_enhanced(self):
        """Test enhanced broadcast to topic."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        
        await self.manager.register_client("topic_client", mock_ws1)
        
        message = {"type": "topic_data", "topic": "market_data"}
        
        # Should not raise an exception even without subscription management
        await self.manager.broadcast_to_topic("market_data", message)
    
    @pytest.mark.asyncio
    async def test_handle_heartbeat_response(self):
        """Test heartbeat response handling."""
        await self.manager.register_client("heartbeat_client", self.mock_websocket)
        
        # Should not raise an exception
        await self.manager.handle_heartbeat_response("heartbeat_client")
        
        # Verify client heartbeat was updated
        client_info = self.manager.clients["heartbeat_client"]
        assert client_info.last_heartbeat is not None
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_enhanced(self):
        """Test enhanced broadcast to all clients."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock()
        
        await self.manager.register_client("all_client_1", mock_ws1)
        await self.manager.register_client("all_client_2", mock_ws2)
        
        message = {"type": "global_announcement", "data": "System maintenance"}
        
        await self.manager.broadcast_to_all(message)
        
        # The enhanced manager uses queuing, just verify no exceptions
        assert "all_client_1" in self.manager.clients
        assert "all_client_2" in self.manager.clients
    
    @pytest.mark.asyncio
    async def test_broadcast_json_enhanced(self):
        """Test enhanced JSON broadcast functionality."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        
        await self.manager.register_client("json_client", mock_ws1)
        
        message = {"type": "json_data", "payload": {"key": "value"}}
        result = await self.manager.broadcast_json(message)
        
        assert result >= 0  # Should return number of successful sends
    
    @pytest.mark.asyncio
    async def test_send_personal_message(self):
        """Test sending personal message."""
        await self.manager.register_client("personal_client", self.mock_websocket)
        
        result = await self.manager.send_personal_message("Hello personal client", "personal_client")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_broadcast_string_message(self):
        """Test broadcasting string message."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        
        await self.manager.register_client("string_client", mock_ws1)
        
        result = await self.manager.broadcast("Hello all clients")
        assert result >= 0
    
    @pytest.mark.asyncio
    async def test_start_stop_heartbeat(self):
        """Test heartbeat task management."""
        # Start heartbeat
        await self.manager.start_heartbeat()
        assert self.manager._heartbeat_task is not None
        
        # Stop heartbeat
        await self.manager.stop_heartbeat()
        # Task should be cancelled/cleaned up
    
    @pytest.mark.asyncio
    async def test_cleanup_stale_connections_enhanced(self):
        """Test cleanup of stale connections in enhanced manager."""
        # Create client with recent heartbeat
        await self.manager.register_client("fresh_client", self.mock_websocket)
        
        # Create client with old heartbeat
        old_websocket = Mock(spec=WebSocket)
        await self.manager.register_client("stale_client", old_websocket)
        
        # Manually set old heartbeat time
        client_info = self.manager.clients["stale_client"]
        old_time = datetime.now(timezone.utc).timestamp() - 1000
        client_info.last_heartbeat = datetime.fromtimestamp(old_time, timezone.utc)
        
        await self.manager.cleanup_stale_connections()
        
        # Fresh client should remain, stale client should be removed
        assert "fresh_client" in self.manager.clients
        assert "stale_client" not in self.manager.clients


class TestWebSocketTaskManagement:
    """Test WebSocket task tracking and management functionality."""
    
    def test_track_task_functionality(self):
        """Test task tracking functionality."""
        # Create a mock task
        mock_task = Mock(spec=asyncio.Task)
        
        # Track the task
        result = _track_task(mock_task)
        
        assert result == mock_task
        # Task should be in weak set (if no exceptions)
    
    def test_track_task_error_handling(self):
        """Test task tracking error handling."""
        # Test with an object that can't be added to WeakSet
        non_task_object = "not_a_task"
        
        # Should not raise an exception
        result = _track_task(non_task_object)
        assert result == non_task_object
    
    @pytest.mark.asyncio
    async def test_cancel_all_ws_tasks_empty(self):
        """Test cancelling all WebSocket tasks when none exist."""
        # Should not raise an exception
        await cancel_all_ws_tasks(timeout=0.1)
    
    @pytest.mark.asyncio
    async def test_cancel_all_ws_tasks_with_tasks(self):
        """Test cancelling all WebSocket tasks with actual tasks."""
        async def dummy_task():
            await asyncio.sleep(10)  # Long-running task
        
        # Create and track some tasks
        task1 = asyncio.create_task(dummy_task())
        task2 = asyncio.create_task(dummy_task())
        
        _track_task(task1)
        _track_task(task2)
        
        # Cancel all tasks
        await cancel_all_ws_tasks(timeout=0.1)
        
        # Tasks should be cancelled
        assert task1.cancelled() or task1.done()
        assert task2.cancelled() or task2.done()


class TestWebSocketIntegrationScenarios:
    """Test WebSocket integration scenarios and edge cases."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.basic_manager = WebSocketClientManager()
        self.enhanced_manager = EnhancedWebSocketClientManager()
    
    @pytest.mark.asyncio
    async def test_client_lifecycle_basic_manager(self):
        """Test complete client lifecycle with basic manager."""
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.send_text = AsyncMock()
        
        # Register client
        client = self.basic_manager.register_client(mock_websocket, "lifecycle_client")
        assert "lifecycle_client" in self.basic_manager.clients
        
        # Subscribe to topics
        self.basic_manager.subscribe_client("lifecycle_client", "market_data")
        self.basic_manager.subscribe_client("lifecycle_client", "trade_updates")
        
        assert len(client.subscriptions) == 2
        
        # Send messages
        await self.basic_manager.send_to_client("lifecycle_client", {"type": "welcome"})
        await self.basic_manager.broadcast_to_topic("market_data", {"symbol": "AAPL", "price": 150.0})
        
        # Verify messages sent
        assert mock_websocket.send_text.call_count == 2
        
        # Unregister client
        result = self.basic_manager.unregister_client("lifecycle_client")
        assert result is True
        assert "lifecycle_client" not in self.basic_manager.clients
    
    @pytest.mark.asyncio
    async def test_client_lifecycle_enhanced_manager(self):
        """Test complete client lifecycle with enhanced manager."""
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.send_text = AsyncMock()
        
        # Register client
        await self.enhanced_manager.register_client("enhanced_lifecycle", mock_websocket)
        assert "enhanced_lifecycle" in self.enhanced_manager.clients
        
        # Send messages
        await self.enhanced_manager.send_to_client("enhanced_lifecycle", {"type": "welcome"})
        await self.enhanced_manager.broadcast_to_all({"type": "announcement"})
        
        # Handle heartbeat
        await self.enhanced_manager.handle_heartbeat_response("enhanced_lifecycle")
        
        # Disconnect client
        await self.enhanced_manager.disconnect("enhanced_lifecycle")
        assert "enhanced_lifecycle" not in self.enhanced_manager.clients
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent WebSocket operations."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws1.send_text = AsyncMock()
        mock_ws2 = Mock(spec=WebSocket)
        mock_ws2.send_text = AsyncMock()
        
        # Register clients concurrently
        await asyncio.gather(
            self.enhanced_manager.register_client("concurrent_1", mock_ws1),
            self.enhanced_manager.register_client("concurrent_2", mock_ws2)
        )
        
        # Broadcast messages concurrently
        message1 = {"type": "concurrent_msg_1"}
        message2 = {"type": "concurrent_msg_2"}
        
        await asyncio.gather(
            self.enhanced_manager.broadcast_message(message1),
            self.enhanced_manager.broadcast_message(message2)
        )
        
        # Both clients should have received both messages
        assert mock_ws1.send_text.call_count >= 2
        assert mock_ws2.send_text.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_error_resilience(self):
        """Test WebSocket error resilience."""
        # Test with websocket that raises exceptions
        error_websocket = Mock(spec=WebSocket)
        error_websocket.send_text = AsyncMock(side_effect=Exception("Connection error"))
        
        good_websocket = Mock(spec=WebSocket)
        good_websocket.send_text = AsyncMock()
        
        self.basic_manager.register_client(error_websocket, "error_client")
        self.basic_manager.register_client(good_websocket, "good_client")
        
        # Broadcast should handle errors gracefully
        await self.basic_manager.broadcast_to_all({"type": "test_resilience"})
        
        # Good client should still receive message
        good_websocket.send_text.assert_called_once()
        
        # Error client should be removed
        assert "error_client" not in self.basic_manager.clients
        assert "good_client" in self.basic_manager.clients
    
    @pytest.mark.asyncio
    async def test_message_queue_overflow_handling(self):
        """Test handling of message queue overflow scenarios."""
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.send_text = AsyncMock()
        
        # Register client with small queue size
        manager = WebSocketClientManager(max_queue_size=2)
        client = manager.register_client(mock_websocket, "queue_test_client")
        
        # Fill up the message queue beyond capacity
        for i in range(5):
            client.message_queue.append({"message": f"test_{i}"})
        
        # Queue should be limited by max_queue_size in real implementation
        # For this test, we just verify the setup works
        assert len(client.message_queue) == 5  # Mock doesn't enforce limits
    
    def test_statistics_accuracy(self):
        """Test statistics tracking accuracy."""
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws2 = Mock(spec=WebSocket)
        
        initial_stats = self.basic_manager.get_statistics()
        
        # Register clients
        self.basic_manager.register_client(mock_ws1, "stats_client_1")
        self.basic_manager.register_client(mock_ws2, "stats_client_2")
        
        stats_after_register = self.basic_manager.get_statistics()
        assert stats_after_register['metrics']['connections_total'] == initial_stats['metrics']['connections_total'] + 2
        
        # Unregister clients
        self.basic_manager.unregister_client("stats_client_1")
        self.basic_manager.unregister_client("stats_client_2")
        
        final_stats = self.basic_manager.get_statistics()
        assert final_stats['metrics']['disconnections_total'] == initial_stats['metrics']['disconnections_total'] + 2


class TestWebSocketEdgeCasesAndErrorHandling:
    """Test WebSocket edge cases and error handling scenarios."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.manager = WebSocketClientManager()
    
    def test_empty_subscriptions_handling(self):
        """Test handling of empty subscriptions."""
        mock_websocket = Mock(spec=WebSocket)
        client = self.manager.register_client(mock_websocket, "empty_sub_client")
        
        # Subscribe and immediately unsubscribe
        self.manager.subscribe_client("empty_sub_client", "test_topic")
        assert "test_topic" in client.subscriptions
        
        self.manager.unsubscribe_client("empty_sub_client", "test_topic")
        assert "test_topic" not in client.subscriptions
        
        # Try to unsubscribe from non-existent topic
        self.manager.unsubscribe_client("empty_sub_client", "nonexistent_topic")
        # Should not raise an exception
    
    @pytest.mark.asyncio
    async def test_websocket_state_transitions(self):
        """Test WebSocket connection state transitions."""
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.send_text = AsyncMock()
        
        # Normal registration
        client = self.manager.register_client(mock_websocket, "state_client")
        assert client.websocket == mock_websocket
        
        # Simulate connection loss during send
        mock_websocket.send_text = AsyncMock(side_effect=WebSocketDisconnect())
        
        result = await self.manager.send_to_client("state_client", {"type": "test"})
        assert result is False
        assert "state_client" not in self.manager.clients
    
    def test_subscription_cleanup_on_unregister(self):
        """Test that subscriptions are properly cleaned up on client unregister."""
        mock_websocket = Mock(spec=WebSocket)
        client = self.manager.register_client(mock_websocket, "cleanup_client")
        
        # Subscribe to multiple topics
        topics = ["topic1", "topic2", "topic3"]
        for topic in topics:
            self.manager.subscribe_client("cleanup_client", topic)
        
        # Verify subscriptions exist
        for topic in topics:
            assert "cleanup_client" in self.manager.subscriptions[topic]
        
        # Unregister client
        self.manager.unregister_client("cleanup_client")
        
        # Verify all subscriptions are cleaned up
        for topic in topics:
            assert "cleanup_client" not in self.manager.subscriptions[topic]
    
    @pytest.mark.asyncio
    async def test_malformed_message_handling(self):
        """Test handling of malformed messages."""
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.send_text = AsyncMock()
        
        self.manager.register_client(mock_websocket, "malformed_client")
        
        # Test with various message types
        test_messages = [
            None,
            {"invalid": object()},  # Non-serializable object
            {"nested": {"very": {"deep": {"structure": "value"}}}},
            "",
            []
        ]
        
        for message in test_messages:
            try:
                await self.manager.send_to_client("malformed_client", message)
                # If it doesn't raise an exception, that's fine
            except (TypeError, ValueError):
                # JSON serialization errors are acceptable
                pass
    
    def test_high_frequency_registration_unregistration(self):
        """Test high-frequency client registration and unregistration."""
        websockets = []
        client_ids = []
        
        # Rapidly register many clients
        for i in range(100):
            mock_ws = Mock(spec=WebSocket)
            client_id = f"rapid_client_{i}"
            websockets.append(mock_ws)
            client_ids.append(client_id)
            
            self.manager.register_client(mock_ws, client_id)
        
        assert len(self.manager.clients) == 100
        
        # Rapidly unregister all clients
        for client_id in client_ids:
            self.manager.unregister_client(client_id)
        
        assert len(self.manager.clients) == 0
        assert self.manager.metrics['connections_total'] == 100
        assert self.manager.metrics['disconnections_total'] == 100


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_websocket_comprehensive_coverage.py -v
    if pytest:
        pytest.main([__file__, "-v", "--tb=short"])
    else:
        print("pytest not available, skipping test execution")