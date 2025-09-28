#!/usr/bin/env python3
"""
Module 33: WebSocket Handler Test
Tests the WebSocket client management and message broadcasting.

Test Target: backend/websocket.py
Focus: WebSocketClient dataclass and WebSocketClientManager functionality
"""

import pytest
import sys
import os
import json
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime, timezone
from typing import Dict, Any
import time

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.websocket import (
    WebSocketClient,
    WebSocketClientManager,
    get_websocket_manager,
    broadcaster
)
from fastapi import WebSocket, WebSocketDisconnect


class TestWebSocketClient:
    """Test the WebSocketClient dataclass."""
    
    def test_websocket_client_initialization(self):
        """Test WebSocketClient initialization with all parameters."""
        mock_websocket = Mock(spec=WebSocket)
        client_id = "test_client_123"
        now = datetime.now(timezone.utc)
        subscriptions = {"topic1", "topic2"}
        
        client = WebSocketClient(
            websocket=mock_websocket,
            client_id=client_id,
            connected_at=now,
            last_seen=now,
            subscriptions=subscriptions,
            queue_size=50
        )
        
        assert client.websocket is mock_websocket
        assert client.client_id == client_id
        assert client.connected_at == now
        assert client.last_seen == now
        assert client.subscriptions == subscriptions
        assert client.queue_size == 50
        assert client.message_queue == []  # Default from __post_init__
    
    def test_websocket_client_post_init_default_queue(self):
        """Test WebSocketClient __post_init__ creates empty message_queue when None."""
        mock_websocket = Mock(spec=WebSocket)
        now = datetime.now(timezone.utc)
        
        client = WebSocketClient(
            websocket=mock_websocket,
            client_id="test",
            connected_at=now,
            last_seen=now,
            subscriptions=set(),
            message_queue=None  # This should trigger __post_init__
        )
        
        assert client.message_queue == []
    
    def test_websocket_client_post_init_existing_queue(self):
        """Test WebSocketClient __post_init__ preserves existing message_queue."""
        mock_websocket = Mock(spec=WebSocket)
        now = datetime.now(timezone.utc)
        existing_queue = [{"msg": "test"}]
        
        client = WebSocketClient(
            websocket=mock_websocket,
            client_id="test",
            connected_at=now,
            last_seen=now,
            subscriptions=set(),
            message_queue=existing_queue
        )
        
        assert client.message_queue is existing_queue


class TestWebSocketClientManager:
    """Test the WebSocketClientManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = WebSocketClientManager(max_queue_size=50, client_ttl=300)
        self.mock_websocket = Mock(spec=WebSocket)
        self.client_id = "test_client_123"
    
    def test_websocket_client_manager_initialization(self):
        """Test WebSocketClientManager initialization."""
        manager = WebSocketClientManager(max_queue_size=100, client_ttl=600)
        
        assert manager.clients == {}
        assert manager.subscriptions == {}
        assert manager.max_queue_size == 100
        assert manager.client_ttl == 600
        assert manager.metrics == {
            'connections_total': 0,
            'disconnections_total': 0,
            'messages_sent_total': 0,
            'messages_dropped_total': 0
        }
    
    def test_register_client(self):
        """Test registering a new WebSocket client."""
        with patch('backend.websocket.datetime') as mock_datetime:
            mock_now = datetime.now(timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            client = self.manager.register_client(self.mock_websocket, self.client_id)
            
            assert isinstance(client, WebSocketClient)
            assert client.websocket is self.mock_websocket
            assert client.client_id == self.client_id
            assert client.connected_at == mock_now
            assert client.last_seen == mock_now
            assert client.subscriptions == set()
            assert client.queue_size == self.manager.max_queue_size
            
            # Check client is stored in manager
            assert self.client_id in self.manager.clients
            assert self.manager.clients[self.client_id] is client
            assert self.manager.metrics['connections_total'] == 1
    
    def test_unregister_client_existing(self):
        """Test unregistering an existing client."""
        # First register a client
        client = self.manager.register_client(self.mock_websocket, self.client_id)
        
        # Subscribe to some topics
        self.manager.subscribe_client(self.client_id, "topic1")
        self.manager.subscribe_client(self.client_id, "topic2")
        
        # Unregister the client
        result = self.manager.unregister_client(self.client_id)
        
        assert result is True
        assert self.client_id not in self.manager.clients
        assert self.client_id not in self.manager.subscriptions["topic1"]
        assert self.client_id not in self.manager.subscriptions["topic2"]
        assert self.manager.metrics['disconnections_total'] == 1
    
    def test_unregister_client_nonexistent(self):
        """Test unregistering a non-existent client."""
        result = self.manager.unregister_client("nonexistent_client")
        
        assert result is False
        assert self.manager.metrics['disconnections_total'] == 0
    
    def test_subscribe_client_existing(self):
        """Test subscribing an existing client to a topic."""
        # Register client first
        self.manager.register_client(self.mock_websocket, self.client_id)
        
        # Subscribe to topic
        self.manager.subscribe_client(self.client_id, "test_topic")
        
        assert "test_topic" in self.manager.clients[self.client_id].subscriptions
        assert self.client_id in self.manager.subscriptions["test_topic"]
    
    def test_subscribe_client_nonexistent(self):
        """Test subscribing a non-existent client does nothing."""
        self.manager.subscribe_client("nonexistent", "test_topic")
        
        # Should not crash and should not create subscription
        assert "nonexistent" not in self.manager.clients
    
    def test_unsubscribe_client_existing(self):
        """Test unsubscribing an existing client from a topic."""
        # Register and subscribe client
        self.manager.register_client(self.mock_websocket, self.client_id)
        self.manager.subscribe_client(self.client_id, "test_topic")
        
        # Unsubscribe
        self.manager.unsubscribe_client(self.client_id, "test_topic")
        
        assert "test_topic" not in self.manager.clients[self.client_id].subscriptions
        assert self.client_id not in self.manager.subscriptions["test_topic"]
    
    def test_unsubscribe_client_nonexistent(self):
        """Test unsubscribing a non-existent client does nothing."""
        self.manager.unsubscribe_client("nonexistent", "test_topic")
        
        # Should not crash
        assert "nonexistent" not in self.manager.clients
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_success(self):
        """Test broadcasting message to all connected clients successfully."""
        # Register multiple clients
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        
        self.manager.register_client(mock_ws1, "client1")
        self.manager.register_client(mock_ws2, "client2")
        
        message = {"type": "test", "data": "hello"}
        
        with patch('backend.websocket.datetime') as mock_datetime:
            mock_now = datetime.now(timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            await self.manager.broadcast_to_all(message)
            
            # Check both clients received the message
            mock_ws1.send_text.assert_called_once_with(json.dumps(message))
            mock_ws2.send_text.assert_called_once_with(json.dumps(message))
            
            # Check last_seen was updated
            assert self.manager.clients["client1"].last_seen == mock_now
            assert self.manager.clients["client2"].last_seen == mock_now
            assert self.manager.metrics['messages_sent_total'] == 2
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_no_clients(self):
        """Test broadcasting to all when no clients are connected."""
        message = {"type": "test", "data": "hello"}
        
        # Should not raise any exceptions
        await self.manager.broadcast_to_all(message)
        
        assert self.manager.metrics['messages_sent_total'] == 0
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_with_disconnect(self):
        """Test broadcasting when some clients disconnect."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        
        # Make ws1 raise WebSocketDisconnect
        mock_ws1.send_text.side_effect = WebSocketDisconnect(code=1000)
        
        self.manager.register_client(mock_ws1, "client1")
        self.manager.register_client(mock_ws2, "client2")
        
        message = {"type": "test", "data": "hello"}
        
        await self.manager.broadcast_to_all(message)
        
        # client1 should be removed due to disconnect
        assert "client1" not in self.manager.clients
        assert "client2" in self.manager.clients
        
        # client2 should still receive the message
        mock_ws2.send_text.assert_called_once_with(json.dumps(message))
        assert self.manager.metrics['messages_sent_total'] == 1
        assert self.manager.metrics['disconnections_total'] == 1
    
    @pytest.mark.asyncio
    async def test_broadcast_to_all_with_general_exception(self):
        """Test broadcasting when a general exception occurs (not WebSocketDisconnect)."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        
        # Make ws1 raise a general Exception
        mock_ws1.send_text.side_effect = Exception("Connection error")
        
        self.manager.register_client(mock_ws1, "client1")
        self.manager.register_client(mock_ws2, "client2")
        
        message = {"type": "test", "data": "hello"}
        
        await self.manager.broadcast_to_all(message)
        
        # client1 should be removed due to exception
        assert "client1" not in self.manager.clients
        assert "client2" in self.manager.clients
        
        # client2 should still receive the message
        mock_ws2.send_text.assert_called_once_with(json.dumps(message))
        assert self.manager.metrics['messages_sent_total'] == 1
        assert self.manager.metrics['disconnections_total'] == 1
    
    @pytest.mark.asyncio
    async def test_broadcast_to_topic_success(self):
        """Test broadcasting to clients subscribed to a specific topic."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        mock_ws3 = AsyncMock(spec=WebSocket)
        
        # Register clients
        self.manager.register_client(mock_ws1, "client1")
        self.manager.register_client(mock_ws2, "client2")
        self.manager.register_client(mock_ws3, "client3")
        
        # Subscribe clients 1 and 2 to topic
        self.manager.subscribe_client("client1", "test_topic")
        self.manager.subscribe_client("client2", "test_topic")
        
        message = {"type": "topic_data", "data": "hello"}
        
        with patch('backend.websocket.datetime') as mock_datetime:
            mock_now = datetime.now(timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            await self.manager.broadcast_to_topic("test_topic", message)
            
            # Only subscribed clients should receive the message
            mock_ws1.send_text.assert_called_once_with(json.dumps(message))
            mock_ws2.send_text.assert_called_once_with(json.dumps(message))
            mock_ws3.send_text.assert_not_called()
            
            assert self.manager.metrics['messages_sent_total'] == 2
    
    @pytest.mark.asyncio
    async def test_broadcast_to_topic_no_subscribers(self):
        """Test broadcasting to a topic with no subscribers."""
        message = {"type": "topic_data", "data": "hello"}
        
        await self.manager.broadcast_to_topic("empty_topic", message)
        
        assert self.manager.metrics['messages_sent_total'] == 0
    
    @pytest.mark.asyncio
    async def test_broadcast_to_topic_with_queue_overflow(self):
        """Test broadcasting with message queue overflow handling."""
        mock_ws = AsyncMock(spec=WebSocket)
        
        # Register client with small queue size
        manager = WebSocketClientManager(max_queue_size=2)
        client = manager.register_client(mock_ws, "client1")
        manager.subscribe_client("client1", "test_topic")
        
        # Fill the queue beyond capacity
        client.message_queue = [{"old": "msg1"}, {"old": "msg2"}]  # At capacity
        
        message = {"type": "new", "data": "hello"}
        
        await manager.broadcast_to_topic("test_topic", message)
        
        # Old message should be dropped
        assert manager.metrics['messages_dropped_total'] == 1
        mock_ws.send_text.assert_called_once_with(json.dumps(message))
    
    @pytest.mark.asyncio
    async def test_broadcast_to_topic_client_not_in_clients(self):
        """Test broadcasting to topic when subscribed client is not in clients dict."""
        # Create a scenario where subscription exists but client doesn't
        self.manager.subscriptions["test_topic"] = {"nonexistent_client"}
        
        message = {"type": "test", "data": "hello"}
        
        # Should not crash and should continue gracefully
        await self.manager.broadcast_to_topic("test_topic", message)
        
        assert self.manager.metrics['messages_sent_total'] == 0
    
    @pytest.mark.asyncio
    async def test_broadcast_to_topic_with_websocket_disconnect(self):
        """Test broadcasting to topic when WebSocketDisconnect occurs."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        
        # Make ws1 raise WebSocketDisconnect
        mock_ws1.send_text.side_effect = WebSocketDisconnect(code=1000)
        
        self.manager.register_client(mock_ws1, "client1")
        self.manager.register_client(mock_ws2, "client2")
        
        self.manager.subscribe_client("client1", "test_topic")
        self.manager.subscribe_client("client2", "test_topic")
        
        message = {"type": "test", "data": "hello"}
        
        await self.manager.broadcast_to_topic("test_topic", message)
        
        # client1 should be removed due to disconnect
        assert "client1" not in self.manager.clients
        assert "client2" in self.manager.clients
        
        # client2 should still receive the message
        mock_ws2.send_text.assert_called_once_with(json.dumps(message))
        assert self.manager.metrics['messages_sent_total'] == 1
        assert self.manager.metrics['disconnections_total'] == 1
    
    @pytest.mark.asyncio
    async def test_broadcast_to_topic_with_general_exception(self):
        """Test broadcasting to topic when a general exception occurs."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        
        # Make ws1 raise a general Exception
        mock_ws1.send_text.side_effect = Exception("Network error")
        
        self.manager.register_client(mock_ws1, "client1")
        self.manager.register_client(mock_ws2, "client2")
        
        self.manager.subscribe_client("client1", "test_topic")
        self.manager.subscribe_client("client2", "test_topic")
        
        message = {"type": "test", "data": "hello"}
        
        await self.manager.broadcast_to_topic("test_topic", message)
        
        # client1 should be removed due to exception
        assert "client1" not in self.manager.clients
        assert "client2" in self.manager.clients
        
        # client2 should still receive the message
        mock_ws2.send_text.assert_called_once_with(json.dumps(message))
        assert self.manager.metrics['messages_sent_total'] == 1
        assert self.manager.metrics['disconnections_total'] == 1
    
    @pytest.mark.asyncio
    async def test_send_to_client_success(self):
        """Test sending message to a specific client successfully."""
        mock_ws = AsyncMock(spec=WebSocket)
        self.manager.register_client(mock_ws, self.client_id)
        
        message = {"type": "direct", "data": "hello"}
        
        with patch('backend.websocket.datetime') as mock_datetime:
            mock_now = datetime.now(timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            result = await self.manager.send_to_client(self.client_id, message)
            
            assert result is True
            mock_ws.send_text.assert_called_once_with(json.dumps(message))
            assert self.manager.clients[self.client_id].last_seen == mock_now
            assert self.manager.metrics['messages_sent_total'] == 1
    
    @pytest.mark.asyncio
    async def test_send_to_client_not_found(self):
        """Test sending message to non-existent client."""
        message = {"type": "direct", "data": "hello"}
        
        result = await self.manager.send_to_client("nonexistent", message)
        
        assert result is False
        assert self.manager.metrics['messages_sent_total'] == 0
    
    @pytest.mark.asyncio
    async def test_send_to_client_disconnect(self):
        """Test sending message when client disconnects."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_text.side_effect = WebSocketDisconnect(code=1000)
        
        self.manager.register_client(mock_ws, self.client_id)
        
        message = {"type": "direct", "data": "hello"}
        
        result = await self.manager.send_to_client(self.client_id, message)
        
        assert result is False
        assert self.client_id not in self.manager.clients  # Should be unregistered
        assert self.manager.metrics['disconnections_total'] == 1
    
    @pytest.mark.asyncio
    async def test_send_to_client_exception(self):
        """Test sending message when an exception occurs."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_text.side_effect = Exception("Connection error")
        
        self.manager.register_client(mock_ws, self.client_id)
        
        message = {"type": "direct", "data": "hello"}
        
        result = await self.manager.send_to_client(self.client_id, message)
        
        assert result is False
        assert self.manager.metrics['messages_sent_total'] == 0
    
    def test_get_statistics(self):
        """Test getting WebSocket manager statistics."""
        # Register some clients and subscriptions
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws2 = Mock(spec=WebSocket)
        
        self.manager.register_client(mock_ws1, "client1")
        self.manager.register_client(mock_ws2, "client2")
        
        self.manager.subscribe_client("client1", "topic1")
        self.manager.subscribe_client("client2", "topic1")
        self.manager.subscribe_client("client2", "topic2")
        
        stats = self.manager.get_statistics()
        
        expected_stats = {
            'active_clients': 2,
            'client_count': 2,
            'total_clients': 2,
            'total_connections': 2,
            'total_subscriptions': 3,  # client1->topic1, client2->topic1, client2->topic2
            'heartbeat_interval': 30,
            'queue_max': 100,
            'metrics': {
                'connections_total': 2,
                'disconnections_total': 0,
                'messages_sent_total': 0,
                'messages_dropped_total': 0
            }
        }
        
        assert stats == expected_stats
    
    def test_cleanup_stale_clients(self):
        """Test cleanup of stale clients based on TTL."""
        # Set up manager with short TTL
        manager = WebSocketClientManager(client_ttl=60)  # 1 minute TTL
        
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws2 = Mock(spec=WebSocket)
        
        with patch('backend.websocket.datetime') as mock_datetime:
            # Mock current time
            now = datetime.now(timezone.utc)
            mock_datetime.now.return_value = now
            
            # Register clients
            client1 = manager.register_client(mock_ws1, "client1")
            client2 = manager.register_client(mock_ws2, "client2")
            
            # Make client1 stale (older than TTL)
            stale_time = datetime.fromtimestamp(now.timestamp() - 120, tz=timezone.utc)  # 2 minutes ago
            client1.last_seen = stale_time
            
            # Run cleanup
            manager.cleanup_stale_clients()
            
            # client1 should be removed, client2 should remain
            assert "client1" not in manager.clients
            assert "client2" in manager.clients
            assert manager.metrics['disconnections_total'] == 1
    
    def test_get_client_count(self):
        """Test getting the number of active clients."""
        assert self.manager.get_client_count() == 0
        
        mock_ws1 = Mock(spec=WebSocket)
        mock_ws2 = Mock(spec=WebSocket)
        
        self.manager.register_client(mock_ws1, "client1")
        assert self.manager.get_client_count() == 1
        
        self.manager.register_client(mock_ws2, "client2")
        assert self.manager.get_client_count() == 2
        
        self.manager.unregister_client("client1")
        assert self.manager.get_client_count() == 1
    
    @pytest.mark.asyncio
    async def test_broadcast_json_to_all(self):
        """Test broadcasting JSON to all clients."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        
        self.manager.register_client(mock_ws1, "client1")
        self.manager.register_client(mock_ws2, "client2")
        
        message = {"type": "broadcast", "data": "test"}
        
        result = await self.manager.broadcast_json(message)
        
        assert result == 2  # Number of clients message was sent to
        mock_ws1.send_text.assert_called_once()
        mock_ws2.send_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_broadcast_json_to_specific_clients(self):
        """Test broadcasting JSON to specific clients."""
        mock_ws1 = AsyncMock(spec=WebSocket)
        mock_ws2 = AsyncMock(spec=WebSocket)
        mock_ws3 = AsyncMock(spec=WebSocket)
        
        self.manager.register_client(mock_ws1, "client1")
        self.manager.register_client(mock_ws2, "client2")
        self.manager.register_client(mock_ws3, "client3")
        
        message = {"type": "targeted", "data": "test"}
        
        result = await self.manager.broadcast_json(message, client_ids=["client1", "client3"])
        
        assert result == 2  # Successfully sent to 2 clients
        mock_ws1.send_text.assert_called_once()
        mock_ws2.send_text.assert_not_called()
        mock_ws3.send_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_broadcast_json_to_nonexistent_clients(self):
        """Test broadcasting JSON to non-existent clients."""
        message = {"type": "test", "data": "hello"}
        
        result = await self.manager.broadcast_json(message, client_ids=["nonexistent1", "nonexistent2"])
        
        assert result == 0  # No clients found
        assert self.manager.metrics['messages_sent_total'] == 0


class TestGlobalFunctions:
    """Test global functions and variables."""
    
    def test_get_websocket_manager_singleton(self):
        """Test that get_websocket_manager returns a singleton instance."""
        # Clear the global variable first
        import backend.websocket
        backend.websocket.websocket_manager = None
        
        manager1 = get_websocket_manager()
        manager2 = get_websocket_manager()
        
        assert manager1 is manager2
        assert isinstance(manager1, WebSocketClientManager)
    
    def test_get_websocket_manager_existing(self):
        """Test that get_websocket_manager returns existing instance."""
        import backend.websocket
        
        # Set a specific instance
        existing_manager = WebSocketClientManager(max_queue_size=200)
        backend.websocket.websocket_manager = existing_manager
        
        result = get_websocket_manager()
        
        assert result is existing_manager
        assert result.max_queue_size == 200
    
    def test_broadcaster_global_instance(self):
        """Test that broadcaster is a global WebSocketClientManager instance."""
        assert isinstance(broadcaster, WebSocketClientManager)
        assert broadcaster.max_queue_size == 100  # Default value
        assert broadcaster.client_ttl == 300  # Default value


if __name__ == "__main__":
    pytest.main([__file__])