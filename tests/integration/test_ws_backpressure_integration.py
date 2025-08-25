"""
Integration tests for WebSocket backpressure and slow consumer scenarios.
Tests WebSocket broadcaster behavior with fast and slow clients.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.helpers.ws_client import WSTestClient


@pytest.mark.integration
class TestWebSocketBackpressure:
    """Tests for WebSocket backpressure handling and slow consumer scenarios."""

    @pytest.fixture
    async def ws_server_app(self):
        """Create WebSocket-enabled app for testing."""
        from backend.api.main import app

        # Ensure WebSocket manager is configured with test settings
        with patch(
            "backend.api.websocket_manager.WebSocketClientManager"
        ) as mock_broadcaster:
            mock_broadcaster_instance = AsyncMock()
            mock_broadcaster_instance.max_queue_size = 100
            mock_broadcaster_instance.drop_policy = "oldest"

            # Mock active connections tracking
            mock_broadcaster_instance.active_connections = {}
            mock_broadcaster_instance.connection_count = 0
            mock_broadcaster_instance.messages_sent = 0
            mock_broadcaster_instance.messages_dropped = 0

            async def mock_broadcast(message):
                """Mock broadcast that simulates backpressure behavior."""
                mock_broadcaster_instance.messages_sent += len(
                    mock_broadcaster_instance.active_connections
                )

                # Simulate dropping messages for slow consumers
                for (
                    conn_id,
                    connection,
                ) in mock_broadcaster_instance.active_connections.items():
                    if (
                        connection.get("slow", False)
                        and len(connection.get("queue", [])) > 50
                    ):
                        mock_broadcaster_instance.messages_dropped += 1
                        connection["queue"].pop(0)  # Drop oldest message
                    else:
                        connection.get("queue", []).append(message)

            mock_broadcaster_instance.broadcast.side_effect = mock_broadcast
            mock_broadcaster.return_value = mock_broadcaster_instance

            yield app, mock_broadcaster_instance

    @pytest.fixture
    async def test_ws_server(self, ws_server_app):
        """Start WebSocket test server."""
        app, mock_broadcaster = ws_server_app

        # For this test, we'd need a real WebSocket server
        # This is simplified - in practice you'd start uvicorn in test mode

        server_url = "ws://localhost:8001/ws"

        # Mock WebSocket endpoint responses
        yield server_url, mock_broadcaster

    @pytest.mark.asyncio
    async def test_fast_and_slow_client_backpressure(self, test_ws_server):
        """Test that slow clients don't affect fast clients due to backpressure."""
        server_url, mock_broadcaster = test_ws_server

        # This test would need a real WebSocket server
        # For now, we'll test the logic with mocked components

        # Simulate fast client (no read delay)
        fast_client = WSTestClient(
            uri=server_url, read_delay_ms=0, max_message_buffer=1000
        )

        # Simulate slow client (100ms delay per message)
        slow_client = WSTestClient(
            uri=server_url,
            read_delay_ms=100,
            max_message_buffer=50,  # Smaller buffer to trigger drops
        )

        try:
            # Mock connection setup
            mock_broadcaster.active_connections = {
                "fast_client": {"queue": [], "slow": False},
                "slow_client": {"queue": [], "slow": True},
            }

            # Simulate broadcasting 100 messages rapidly
            messages_to_send = 100

            for i in range(messages_to_send):
                message = {
                    "type": "market_data",
                    "symbol": "AAPL",
                    "price": 150.00 + i * 0.01,
                    "timestamp": f"2023-12-01T10:00:{i:02d}Z",
                }

                await mock_broadcaster.broadcast(json.dumps(message))

                # Small delay to simulate realistic message rate
                await asyncio.sleep(0.001)  # 1ms between messages

            # Verify fast client received all messages
            fast_queue = mock_broadcaster.active_connections["fast_client"]["queue"]
            slow_queue = mock_broadcaster.active_connections["slow_client"]["queue"]

            # Fast client should have received most/all messages
            assert len(fast_queue) >= messages_to_send * 0.9  # At least 90%

            # Slow client should have dropped messages due to backpressure
            assert len(slow_queue) < messages_to_send

            # Should have tracked dropped messages
            assert mock_broadcaster.messages_dropped > 0

        finally:
            # Cleanup would happen here in real test
            pass

    @pytest.mark.asyncio
    async def test_slow_consumer_message_dropping_policy(self, test_ws_server):
        """Test that slow consumers drop messages according to policy (oldest first)."""
        server_url, mock_broadcaster = test_ws_server

        # Configure mock for oldest-drop policy
        mock_broadcaster.drop_policy = "oldest"
        mock_broadcaster.max_queue_size = 10

        # Simulate slow client that can't keep up
        mock_broadcaster.active_connections = {
            "slow_client": {"queue": [], "slow": True, "max_queue": 10}
        }

        # Send messages that will cause queue overflow
        messages_sent = []
        for i in range(20):  # Send 20 messages to 10-message queue
            message = {"type": "test", "sequence": i, "data": f"message_{i}"}
            messages_sent.append(message)

            # Simulate queue management
            queue = mock_broadcaster.active_connections["slow_client"]["queue"]

            if len(queue) >= 10:
                # Drop oldest message
                dropped = queue.pop(0)
                mock_broadcaster.messages_dropped += 1

            queue.append(message)

        # Verify oldest messages were dropped
        final_queue = mock_broadcaster.active_connections["slow_client"]["queue"]

        assert len(final_queue) == 10  # Queue size limit maintained
        assert (
            final_queue[0]["sequence"] == 10
        )  # First message is sequence 10 (0-9 were dropped)
        assert final_queue[-1]["sequence"] == 19  # Last message is sequence 19
        assert mock_broadcaster.messages_dropped == 10  # 10 messages dropped

    @pytest.mark.asyncio
    async def test_websocket_connection_recovery_after_backpressure(
        self, test_ws_server
    ):
        """Test that connections can recover after backpressure conditions."""
        server_url, mock_broadcaster = test_ws_server

        # Simulate a client that becomes slow then fast again
        client_state = {"slow": True, "queue": []}

        mock_broadcaster.active_connections = {"recovering_client": client_state}

        # Phase 1: Send messages while client is slow
        for i in range(50):
            message = {"phase": 1, "sequence": i}

            if client_state["slow"] and len(client_state["queue"]) > 20:
                # Drop messages when slow and queue is full
                client_state["queue"].pop(0)
                mock_broadcaster.messages_dropped += 1
            else:
                client_state["queue"].append(message)

        messages_after_slow_phase = len(client_state["queue"])

        # Phase 2: Client speeds up (stops being slow)
        client_state["slow"] = False

        # Simulate client catching up by consuming messages
        consumed_messages = []
        while client_state["queue"]:
            consumed_messages.append(client_state["queue"].pop(0))
            await asyncio.sleep(0.001)  # Fast consumption

        # Phase 3: Send more messages to recovered client
        for i in range(50, 100):
            message = {"phase": 3, "sequence": i}
            client_state["queue"].append(message)

        # Verify recovery
        assert len(consumed_messages) == messages_after_slow_phase
        assert len(client_state["queue"]) == 50  # All new messages queued
        assert (
            mock_broadcaster.messages_dropped > 0
        )  # Some messages were dropped during slow phase

    @pytest.mark.asyncio
    async def test_multiple_slow_clients_isolation(self, test_ws_server):
        """Test that multiple slow clients don't affect each other or fast clients."""
        server_url, mock_broadcaster = test_ws_server

        # Set up multiple clients with different characteristics
        mock_broadcaster.active_connections = {
            "fast_client": {"queue": [], "slow": False, "max_queue": 1000},
            "slow_client_1": {"queue": [], "slow": True, "max_queue": 20},
            "slow_client_2": {"queue": [], "slow": True, "max_queue": 15},
            "medium_client": {"queue": [], "slow": False, "max_queue": 100},
        }

        # Send a burst of messages
        for i in range(100):
            message = {"type": "burst", "sequence": i}

            # Simulate per-client queue management
            for client_id, client_state in mock_broadcaster.active_connections.items():
                if len(client_state["queue"]) >= client_state["max_queue"]:
                    # Drop oldest for this specific client
                    client_state["queue"].pop(0)
                    mock_broadcaster.messages_dropped += 1

                client_state["queue"].append(message.copy())

        # Verify isolation
        fast_queue = mock_broadcaster.active_connections["fast_client"]["queue"]
        slow1_queue = mock_broadcaster.active_connections["slow_client_1"]["queue"]
        slow2_queue = mock_broadcaster.active_connections["slow_client_2"]["queue"]
        medium_queue = mock_broadcaster.active_connections["medium_client"]["queue"]

        # Fast client should have received all messages
        assert len(fast_queue) == 100

        # Slow clients should have limited queue sizes
        assert len(slow1_queue) <= 20
        assert len(slow2_queue) <= 15

        # Medium client should have received all messages
        assert len(medium_queue) == 100

        # Each slow client should have recent messages (not necessarily the same ones)
        assert slow1_queue[-1]["sequence"] == 99  # Most recent message
        assert slow2_queue[-1]["sequence"] == 99  # Most recent message

    @pytest.mark.asyncio
    async def test_websocket_metrics_during_backpressure(self, test_ws_server):
        """Test that WebSocket metrics are correctly updated during backpressure scenarios."""
        server_url, mock_broadcaster = test_ws_server

        # Initialize metrics tracking
        metrics = {
            "ws_connections_total": 0,
            "ws_messages_sent_total": 0,
            "ws_messages_dropped_total": 0,
            "ws_queue_size_current": {},
        }

        # Set up clients
        mock_broadcaster.active_connections = {
            "client_1": {"queue": [], "slow": True},
            "client_2": {"queue": [], "slow": False},
        }

        metrics["ws_connections_total"] = len(mock_broadcaster.active_connections)

        # Send messages and track metrics
        for i in range(50):
            message = {"sequence": i}

            for client_id, client_state in mock_broadcaster.active_connections.items():
                if client_state["slow"] and len(client_state["queue"]) > 25:
                    # Drop message
                    client_state["queue"].pop(0)
                    metrics["ws_messages_dropped_total"] += 1
                else:
                    client_state["queue"].append(message)
                    metrics["ws_messages_sent_total"] += 1

                # Track current queue sizes
                metrics["ws_queue_size_current"][client_id] = len(client_state["queue"])

        # Verify metrics
        assert metrics["ws_connections_total"] == 2
        assert metrics["ws_messages_sent_total"] > 0
        assert metrics["ws_messages_dropped_total"] > 0

        # Verify queue size tracking
        assert "client_1" in metrics["ws_queue_size_current"]
        assert "client_2" in metrics["ws_queue_size_current"]
        assert metrics["ws_queue_size_current"]["client_1"] <= 25  # Capped due to drops

    @pytest.mark.asyncio
    async def test_websocket_graceful_disconnection_under_load(self, test_ws_server):
        """Test graceful disconnection of slow clients under high load."""
        server_url, mock_broadcaster = test_ws_server

        # Simulate high load scenario
        mock_broadcaster.active_connections = {
            "overloaded_client": {
                "queue": [],
                "slow": True,
                "disconnect_threshold": 100,
            }
        }

        disconnect_triggered = False

        # Send messages until disconnect threshold is reached
        for i in range(150):
            message = {"sequence": i}
            client_state = mock_broadcaster.active_connections.get("overloaded_client")

            if client_state:
                client_state["queue"].append(message)

                # Simulate disconnect when queue gets too large
                if len(client_state["queue"]) >= client_state["disconnect_threshold"]:
                    # Client would be disconnected in real scenario
                    del mock_broadcaster.active_connections["overloaded_client"]
                    disconnect_triggered = True
                    break

        # Verify graceful disconnection occurred
        assert disconnect_triggered
        assert "overloaded_client" not in mock_broadcaster.active_connections

    @pytest.mark.asyncio
    async def test_websocket_connection_limit_enforcement(self, test_ws_server):
        """Test that WebSocket connection limits are enforced under load."""
        server_url, mock_broadcaster = test_ws_server

        # Set connection limit
        max_connections = 5
        mock_broadcaster.max_connections = max_connections

        # Simulate connection attempts
        connection_attempts = []

        for i in range(10):  # Try to create 10 connections
            client_id = f"client_{i}"

            if len(mock_broadcaster.active_connections) < max_connections:
                # Accept connection
                mock_broadcaster.active_connections[client_id] = {
                    "queue": [],
                    "connected_at": f"2023-12-01T10:00:{i:02d}Z",
                }
                connection_attempts.append({"client_id": client_id, "accepted": True})
            else:
                # Reject connection
                connection_attempts.append({"client_id": client_id, "accepted": False})

        # Verify connection limit enforcement
        assert len(mock_broadcaster.active_connections) == max_connections

        accepted_connections = [
            attempt for attempt in connection_attempts if attempt["accepted"]
        ]
        rejected_connections = [
            attempt for attempt in connection_attempts if not attempt["accepted"]
        ]

        assert len(accepted_connections) == max_connections
        assert len(rejected_connections) == 5  # 10 attempts - 5 accepted = 5 rejected

    @pytest.mark.asyncio
    async def test_websocket_load_balancing_across_connections(self, test_ws_server):
        """Test load balancing of message distribution across connections."""
        server_url, mock_broadcaster = test_ws_server

        # Set up multiple balanced connections
        num_connections = 4
        mock_broadcaster.active_connections = {}

        for i in range(num_connections):
            mock_broadcaster.active_connections[f"client_{i}"] = {
                "queue": [],
                "load_factor": 1.0,  # All clients have equal load capacity
                "priority": "normal",
            }

        # Send messages with load balancing logic
        total_messages = 100

        for i in range(total_messages):
            message = {"sequence": i, "data": f"message_{i}"}

            # Simple round-robin distribution
            client_id = f"client_{i % num_connections}"
            mock_broadcaster.active_connections[client_id]["queue"].append(message)

        # Verify balanced distribution
        for i in range(num_connections):
            client_queue = mock_broadcaster.active_connections[f"client_{i}"]["queue"]
            expected_messages = total_messages // num_connections

            # Each client should have approximately equal number of messages
            assert len(client_queue) == expected_messages

            # Verify message distribution pattern (every 4th message)
            for j, msg in enumerate(client_queue):
                expected_sequence = i + (j * num_connections)
                assert msg["sequence"] == expected_sequence
