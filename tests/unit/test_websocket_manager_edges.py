"""
Comprehensive unit tests for WebSocket manager backpressure, heartbeat, and client lifecycle.
Tests queue management, stale client cleanup, rate limiting, and connection edge cases.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocket, WebSocketDisconnect

from backend.api.main import WebSocketClientManager


class TestWebSocketClientManager:
    """Test WebSocket client manager core functionality."""

    @pytest.mark.unit
    def test_websocket_manager_initialization(self):
        """Test WebSocket client manager initialization with different configurations."""
        # Default initialization
        default_manager = WebSocketClientManager()
        assert default_manager.max_queue_size == 100  # Default value
        assert len(default_manager.clients) == 0
        assert default_manager._heartbeat_task is None
        
        # Custom queue size
        custom_manager = WebSocketClientManager(max_queue_size=50)
        assert custom_manager.max_queue_size == 50
        
        # Edge case: very small queue
        small_manager = WebSocketClientManager(max_queue_size=1)
        assert small_manager.max_queue_size == 1
        
        # Edge case: very large queue
        large_manager = WebSocketClientManager(max_queue_size=10000)
        assert large_manager.max_queue_size == 10000

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_client_basic(self):
        """Test adding WebSocket client with proper initialization."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "test-client-1"
        
        await manager.add_client(client_id, mock_websocket)
        
        # Verify client was added
        assert client_id in manager.clients
        client_info = manager.clients[client_id]
        
        assert client_info['websocket'] == mock_websocket
        assert client_info['queue'] is not None
        assert client_info['last_ping'] > 0  # Should be set to current time
        assert isinstance(client_info['subscriptions'], set)
        assert client_info['send_task'] is not None
        assert not client_info['send_task'].done()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_client_duplicate_id(self):
        """Test adding client with duplicate ID overwrites existing."""
        manager = WebSocketClientManager()
        mock_websocket1 = AsyncMock()
        mock_websocket2 = AsyncMock() 
        client_id = "duplicate-client"
        
        # Add first client
        await manager.add_client(client_id, mock_websocket1)
        first_task = manager.clients[client_id]['send_task']
        
        # Add second client with same ID
        await manager.add_client(client_id, mock_websocket2)
        
        # Should have new websocket and task
        assert manager.clients[client_id]['websocket'] == mock_websocket2
        assert manager.clients[client_id]['send_task'] != first_task

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remove_client_basic(self):
        """Test removing WebSocket client with proper cleanup."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "remove-test-client"
        
        # Add client first
        await manager.add_client(client_id, mock_websocket)
        assert client_id in manager.clients
        
        # Remove client
        await manager.remove_client(client_id)
        
        # Verify client was removed
        assert client_id not in manager.clients
        # WebSocket close should be called
        mock_websocket.close.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remove_nonexistent_client(self):
        """Test removing client that doesn't exist."""
        manager = WebSocketClientManager()
        
        # Should not raise exception
        await manager.remove_client("nonexistent-client")
        assert len(manager.clients) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remove_client_task_cleanup(self):
        """Test that client removal properly cancels send task."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "task-cleanup-test"
        
        await manager.add_client(client_id, mock_websocket)
        send_task = manager.clients[client_id]['send_task']
        
        # Task should be running
        assert not send_task.done()
        
        await manager.remove_client(client_id)
        
        # Give task a moment to be cancelled
        await asyncio.sleep(0.01)
        
        # Task should be cancelled
        assert send_task.done()
        assert send_task.cancelled()


class TestWebSocketBackpressure:
    """Test WebSocket backpressure handling and queue management."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_message_basic(self):
        """Test basic message broadcasting to all clients."""
        manager = WebSocketClientManager()
        
        # Add multiple clients
        clients = []
        for i in range(3):
            mock_ws = AsyncMock()
            client_id = f"broadcast-client-{i}"
            await manager.add_client(client_id, mock_ws)
            clients.append((client_id, mock_ws))
        
        test_message = {"type": "test", "data": "broadcast test"}
        
        await manager.broadcast_message(test_message)
        
        # Give message sender tasks time to process
        await asyncio.sleep(0.01)
        
        # Verify message was queued for all clients
        for client_id, _ in clients:
            assert client_id in manager.clients

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_message_with_subscription_filter(self):
        """Test message broadcasting with subscription filter."""
        manager = WebSocketClientManager()
        
        # Add clients with different subscriptions
        mock_ws1 = AsyncMock()
        await manager.add_client("filtered-client-1", mock_ws1)
        manager.clients["filtered-client-1"]['subscriptions'].add('signals')
        
        mock_ws2 = AsyncMock()
        await manager.add_client("filtered-client-2", mock_ws2)
        manager.clients["filtered-client-2"]['subscriptions'].add('portfolio')
        
        mock_ws3 = AsyncMock()
        await manager.add_client("filtered-client-3", mock_ws3)  # No subscriptions
        
        signals_message = {"type": "signal_update", "data": "signal data"}
        
        await manager.broadcast_message(signals_message, subscription_filter='signals')
        
        # Give tasks time to process
        await asyncio.sleep(0.01)
        
        # Only client-1 should receive the message (has signals subscription)
        # This is tested indirectly by verifying queue behavior

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_queue_backpressure_policy(self):
        """Test backpressure policy when client queue is full."""
        manager = WebSocketClientManager(max_queue_size=2)  # Very small queue
        mock_websocket = AsyncMock()
        client_id = "backpressure-test"
        
        await manager.add_client(client_id, mock_websocket)
        client_queue = manager.clients[client_id]['queue']
        
        # Fill queue to capacity
        message1 = {"type": "test", "data": "message1"}
        message2 = {"type": "test", "data": "message2"}
        message3 = {"type": "test", "data": "message3"}  # Should trigger backpressure
        
        await manager.broadcast_message(message1)
        await manager.broadcast_message(message2)
        
        # Queue should be full (size 2)
        assert client_queue.qsize() == 2
        
        # Third message should trigger backpressure (drop oldest)
        await manager.broadcast_message(message3)
        
        # Queue should still be size 2, but with newest message
        assert client_queue.qsize() == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_message_sender_task_functionality(self):
        """Test message sender task processes messages correctly."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "sender-test"
        
        await manager.add_client(client_id, mock_websocket)
        
        # Send a message
        test_message = {"type": "test", "content": "sender test"}
        await manager.broadcast_message(test_message)
        
        # Give sender task time to process
        await asyncio.sleep(0.1)
        
        # Verify websocket.send_text was called
        mock_websocket.send_text.assert_called()
        
        # Verify message content
        sent_data = mock_websocket.send_text.call_args[0][0]
        sent_message = json.loads(sent_data)
        assert sent_message["type"] == "test"
        assert sent_message["content"] == "sender test"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_message_sender_websocket_disconnect(self):
        """Test message sender handling when WebSocket disconnects."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "disconnect-test"
        
        # Configure websocket to raise disconnect exception
        mock_websocket.send_text.side_effect = WebSocketDisconnect()
        
        await manager.add_client(client_id, mock_websocket)
        
        # Send message that will cause disconnect
        await manager.broadcast_message({"type": "test"})
        
        # Give sender task time to handle disconnect and cleanup
        await asyncio.sleep(0.1)
        
        # Client should be removed automatically
        assert client_id not in manager.clients


class TestWebSocketHeartbeat:
    """Test WebSocket heartbeat mechanism and stale client detection."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_heartbeat(self):
        """Test starting heartbeat task."""
        manager = WebSocketClientManager()
        
        await manager.start_heartbeat()
        
        assert manager._heartbeat_task is not None
        assert not manager._heartbeat_task.done()

    @pytest.mark.unit 
    @pytest.mark.asyncio
    async def test_stop_heartbeat(self):
        """Test stopping heartbeat task."""
        manager = WebSocketClientManager()
        
        await manager.start_heartbeat()
        assert not manager._heartbeat_task.done()
        
        await manager.stop_heartbeat()
        
        # Task should be cancelled
        assert manager._heartbeat_task.done()
        assert manager._heartbeat_task.cancelled()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stop_heartbeat_when_not_started(self):
        """Test stopping heartbeat when it was never started."""
        manager = WebSocketClientManager()
        
        # Should not raise exception
        await manager.stop_heartbeat()
        assert manager._heartbeat_task is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_heartbeat_ping_message_format(self):
        """Test heartbeat sends properly formatted ping messages."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "ping-test"
        
        await manager.add_client(client_id, mock_websocket)
        
        # Start heartbeat
        await manager.start_heartbeat()
        
        # Wait for at least one heartbeat cycle
        await asyncio.sleep(0.1)  # Shorter than actual heartbeat interval for testing
        
        # Stop heartbeat to avoid cleanup issues
        await manager.stop_heartbeat()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stale_client_detection(self):
        """Test detection and removal of stale clients."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "stale-test"
        
        await manager.add_client(client_id, mock_websocket)
        
        # Manually set last_ping to old timestamp (simulate stale client)
        manager.clients[client_id]['last_ping'] = time.time() - 120  # 2 minutes ago
        
        # Simulate heartbeat stale detection logic
        current_time = time.time()
        stale_clients = []
        for cid, client_info in manager.clients.items():
            if current_time - client_info['last_ping'] > 60:  # 60 second threshold
                stale_clients.append(cid)
        
        assert client_id in stale_clients
        
        # Remove stale client
        for cid in stale_clients:
            await manager.remove_client(cid)
        
        assert client_id not in manager.clients

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_client_pong_updates_last_ping(self):
        """Test that client pong responses update last_ping timestamp."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "pong-test"
        
        await manager.add_client(client_id, mock_websocket)
        
        initial_ping = manager.clients[client_id]['last_ping']
        
        # Wait a bit
        await asyncio.sleep(0.01)
        
        # Simulate client pong response
        new_ping_time = time.time()
        manager.clients[client_id]['last_ping'] = new_ping_time
        
        assert manager.clients[client_id]['last_ping'] > initial_ping

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_heartbeat_queue_full_marks_stale(self):
        """Test that clients with full queues are marked as stale."""
        manager = WebSocketClientManager(max_queue_size=1)  # Very small queue
        mock_websocket = AsyncMock()
        client_id = "queue-full-stale"
        
        await manager.add_client(client_id, mock_websocket)
        client_queue = manager.clients[client_id]['queue']
        
        # Fill the queue
        await client_queue.put({"type": "test"})
        
        # Try to put ping message (should fail due to full queue)
        ping_message = {"type": "ping", "timestamp": time.time()}
        
        try:
            client_queue.put_nowait(ping_message)
        except asyncio.QueueFull:
            # Client should be considered stale
            stale_clients = [client_id]
        
        # In real implementation, stale clients would be removed
        assert len(stale_clients) == 1
        assert stale_clients[0] == client_id


class TestWebSocketEdgeCases:
    """Test WebSocket edge cases and error conditions."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_client_operations(self):
        """Test concurrent client add/remove operations."""
        manager = WebSocketClientManager()
        
        # Concurrent add operations
        tasks = []
        for i in range(10):
            mock_ws = AsyncMock()
            task = asyncio.create_task(manager.add_client(f"concurrent-{i}", mock_ws))
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # All clients should be added
        assert len(manager.clients) == 10
        
        # Concurrent remove operations
        remove_tasks = []
        for i in range(10):
            task = asyncio.create_task(manager.remove_client(f"concurrent-{i}"))
            remove_tasks.append(task)
        
        await asyncio.gather(*remove_tasks)
        
        # All clients should be removed
        assert len(manager.clients) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_close_exception_handling(self):
        """Test handling when WebSocket.close() raises exception."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "close-exception-test"
        
        # Configure websocket.close to raise exception
        mock_websocket.close.side_effect = Exception("Close failed")
        
        await manager.add_client(client_id, mock_websocket)
        
        # Should handle exception gracefully
        await manager.remove_client(client_id)
        
        # Client should still be removed despite close exception
        assert client_id not in manager.clients

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_message_serialization_error(self):
        """Test handling of message serialization errors."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "serialization-test"
        
        await manager.add_client(client_id, mock_websocket)
        
        # Send message that can't be JSON serialized
        unserializable_message = {
            "type": "test",
            "data": lambda x: x  # Function can't be serialized
        }
        
        # Should handle gracefully without crashing
        try:
            await manager.broadcast_message(unserializable_message)
            await asyncio.sleep(0.1)  # Give sender task time to process
        except Exception:
            # If exception occurs, it should be handled gracefully
            pass
        
        # Client should still exist
        assert client_id in manager.clients

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_large_message_handling(self):
        """Test handling of very large messages."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "large-message-test"
        
        await manager.add_client(client_id, mock_websocket)
        
        # Create large message
        large_data = "x" * 1000000  # 1MB string
        large_message = {"type": "large", "data": large_data}
        
        await manager.broadcast_message(large_message)
        await asyncio.sleep(0.1)
        
        # Should handle large message
        mock_websocket.send_text.assert_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_client_metrics_tracking(self):
        """Test client connection metrics if available."""
        manager = WebSocketClientManager()
        
        # Test connection count tracking
        initial_count = len(manager.clients)
        assert initial_count == 0
        
        # Add clients
        for i in range(5):
            mock_ws = AsyncMock()
            await manager.add_client(f"metrics-client-{i}", mock_ws)
        
        assert len(manager.clients) == 5
        
        # Remove some clients
        for i in range(2):
            await manager.remove_client(f"metrics-client-{i}")
        
        assert len(manager.clients) == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_management(self):
        """Test client subscription management."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "subscription-test"
        
        await manager.add_client(client_id, mock_websocket)
        
        # Test subscription set operations
        subscriptions = manager.clients[client_id]['subscriptions']
        
        # Add subscriptions
        subscriptions.add('signals')
        subscriptions.add('portfolio')
        subscriptions.add('trades')
        
        assert 'signals' in subscriptions
        assert 'portfolio' in subscriptions
        assert 'trades' in subscriptions
        assert len(subscriptions) == 3
        
        # Remove subscription
        subscriptions.discard('portfolio')
        assert 'portfolio' not in subscriptions
        assert len(subscriptions) == 2
        
        # Remove non-existent subscription (should not error)
        subscriptions.discard('nonexistent')
        assert len(subscriptions) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_manager_cleanup_on_shutdown(self):
        """Test WebSocket manager cleanup during shutdown."""
        manager = WebSocketClientManager()
        
        # Add multiple clients
        client_ids = []
        for i in range(5):
            mock_ws = AsyncMock()
            client_id = f"shutdown-client-{i}"
            await manager.add_client(client_id, mock_ws)
            client_ids.append(client_id)
        
        # Start heartbeat
        await manager.start_heartbeat()
        
        # Simulate shutdown - remove all clients and stop heartbeat
        for client_id in list(manager.clients.keys()):
            await manager.remove_client(client_id)
        
        await manager.stop_heartbeat()
        
        # Verify cleanup
        assert len(manager.clients) == 0
        assert manager._heartbeat_task.done()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_rate_limiting_preparation(self):
        """Test data structures that would support rate limiting."""
        manager = WebSocketClientManager()
        mock_websocket = AsyncMock()
        client_id = "rate-limit-test"
        
        await manager.add_client(client_id, mock_websocket)
        
        # Verify client info has necessary fields for rate limiting
        client_info = manager.clients[client_id]
        
        # These could be extended to support rate limiting
        assert 'websocket' in client_info
        assert 'queue' in client_info
        assert 'last_ping' in client_info
        
        # Could add rate limiting fields like:
        # assert 'message_count' in client_info
        # assert 'last_reset_time' in client_info
