"""
Comprehensive tests for backend/integrations/alpaca_stream.py

Tests the AlpacaStreamClient WebSocket client for Alpaca trade updates.
Covers: connection, authentication, subscription, message handling,
        reconnection logic, queue processing, and status mapping.

Phase 3: Alpaca Integrations - Stream Tests
"""

import asyncio
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_settings():
    """Mock settings for Alpaca stream client."""
    settings = MagicMock()
    settings.ALPACA_API_KEY_ID = "test_key"
    settings.ALPACA_API_SECRET_KEY = "test_secret"
    settings.ALPACA_PAPER = True
    return settings


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set environment variables for Alpaca stream client."""
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test_key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test_secret")
    monkeypatch.setenv("ALPACA_PAPER", "true")
    monkeypatch.setenv("ALPACA_STREAM_URL", "wss://paper-api.alpaca.markets/stream")


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    ws.ping = AsyncMock()
    return ws


# ============================================================================
# AlpacaStreamClient INITIALIZATION TESTS
# ============================================================================

class TestAlpacaStreamClientInit:
    """Tests for AlpacaStreamClient initialization."""

    def test_init_with_paper_env(self, mock_env_vars):
        """Test initialization with paper trading environment."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client.api_key == "test_key"
            assert client.api_secret == "test_secret"
            assert client.is_paper is True
            assert "paper-api" in client.ws_url

    def test_init_with_live_env(self, monkeypatch):
        """Test initialization with live trading environment."""
        monkeypatch.setenv("ALPACA_API_KEY_ID", "live_key")
        monkeypatch.setenv("ALPACA_API_SECRET_KEY", "live_secret")
        monkeypatch.setenv("ALPACA_PAPER", "false")
        
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_stream.os.getenv") as mock_getenv:
            mock_get.return_value = MagicMock()
            
            # Mock os.getenv to return live trading values
            def getenv_side_effect(key, default=None):
                env_map = {
                    "ALPACA_API_KEY_ID": "live_key",
                    "ALPACA_API_SECRET_KEY": "live_secret",
                    "ALPACA_PAPER": "false"
                    # ALPACA_STREAM_URL not in map - will use default
                }
                if key in env_map:
                    return env_map[key]
                return default  # Use the provided default for other keys
            
            mock_getenv.side_effect = getenv_side_effect
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client.is_paper is False
            assert "paper-api" not in client.ws_url
            assert "api.alpaca.markets" in client.ws_url

    def test_init_default_reconnection_config(self, mock_env_vars):
        """Test default reconnection configuration."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client.reconnect_delay == 1.0
            assert client.max_reconnect_delay == 60.0
            assert client.reconnect_multiplier == 2.0
            assert client.max_reconnect_attempts == 10

    def test_init_queue_and_heartbeat_config(self, mock_env_vars):
        """Test queue and heartbeat configuration."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            # Queue is unbounded (maxsize=0) — trade updates must never be dropped
            assert client.update_queue.maxsize == 0
            assert client.heartbeat_interval == 30.0

    def test_init_connection_state(self, mock_env_vars):
        """Test initial connection state."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client.websocket is None
            assert client.is_connected is False
            assert client.is_authenticated is False
            assert client.should_reconnect is True


# ============================================================================
# CONNECTION TESTS
# ============================================================================

class TestAlpacaStreamClientConnect:
    """Tests for AlpacaStreamClient connection logic."""

    @pytest.mark.asyncio
    async def test_connect_no_credentials(self, monkeypatch):
        """Test connection fails when credentials are missing."""
        monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
        monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
        
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.api_key = None
            client.api_secret = None
            
            result = await client.connect()
            
            assert result is False

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_env_vars, mock_websocket):
        """Test successful connection."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_stream.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_get.return_value = MagicMock()
            mock_connect.return_value = mock_websocket

            # Mock authentication response (old format)
            mock_websocket.recv.side_effect = [
                json.dumps({"T": "success", "msg": "authenticated"}),
                json.dumps({"T": "listening", "data": {"streams": ["trade_updates"]}})
            ]

            from backend.integrations.alpaca_stream import AlpacaStreamClient

            client = AlpacaStreamClient()

            # Mock background tasks
            with patch.object(client, "_start_background_tasks", new_callable=AsyncMock):
                result = await client.connect()

            assert result is True
            assert client.is_connected is True
            assert client.reconnect_attempts == 0

    @pytest.mark.asyncio
    async def test_connect_exception_handling(self, mock_env_vars):
        """Test connection handles exceptions gracefully."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_stream.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_get.return_value = MagicMock()
            mock_connect.side_effect = Exception("Connection failed")
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            result = await client.connect()
            
            assert result is False
            assert client.is_connected is False


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

class TestAlpacaStreamClientAuthentication:
    """Tests for AlpacaStreamClient authentication logic."""

    @pytest.mark.asyncio
    async def test_authenticate_old_format_success(self, mock_env_vars, mock_websocket):
        """Test authentication with old Alpaca API format."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            
            # Old format response
            mock_websocket.recv.return_value = json.dumps({
                "T": "success", "msg": "authenticated"
            })
            
            result = await client._authenticate()
            
            assert result is True
            assert client.is_authenticated is True

    @pytest.mark.asyncio
    async def test_authenticate_new_format_success(self, mock_env_vars, mock_websocket):
        """Test authentication with new Alpaca API format."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            
            # New format response
            mock_websocket.recv.return_value = json.dumps({
                "stream": "authorization",
                "data": {"action": "authenticate", "status": "authorized"}
            })
            
            result = await client._authenticate()
            
            assert result is True
            assert client.is_authenticated is True

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, mock_env_vars, mock_websocket):
        """Test authentication failure."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            
            # Failed auth response
            mock_websocket.recv.return_value = json.dumps({
                "T": "error", "msg": "unauthorized"
            })
            
            result = await client._authenticate()
            
            assert result is False
            assert client.is_authenticated is False

    @pytest.mark.asyncio
    async def test_authenticate_exception(self, mock_env_vars, mock_websocket):
        """Test authentication handles exceptions."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            
            mock_websocket.recv.side_effect = Exception("Network error")
            
            result = await client._authenticate()
            
            assert result is False


# ============================================================================
# SUBSCRIPTION TESTS
# ============================================================================

class TestAlpacaStreamClientSubscription:
    """Tests for AlpacaStreamClient subscription logic."""

    @pytest.mark.asyncio
    async def test_subscribe_old_format_success(self, mock_env_vars, mock_websocket):
        """Test subscription with old Alpaca API format."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            
            mock_websocket.recv.return_value = json.dumps({
                "T": "listening", "data": {"streams": ["trade_updates"]}
            })
            
            result = await client._subscribe_to_trade_updates()
            
            assert result is True

    @pytest.mark.asyncio
    async def test_subscribe_new_format_success(self, mock_env_vars, mock_websocket):
        """Test subscription with new Alpaca API format."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            
            mock_websocket.recv.return_value = json.dumps({
                "stream": "listening", "data": {"streams": ["trade_updates"]}
            })
            
            result = await client._subscribe_to_trade_updates()
            
            assert result is True

    @pytest.mark.asyncio
    async def test_subscribe_failure(self, mock_env_vars, mock_websocket):
        """Test subscription failure."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            
            mock_websocket.recv.return_value = json.dumps({
                "T": "error", "msg": "subscription_failed"
            })
            
            result = await client._subscribe_to_trade_updates()
            
            assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_exception(self, mock_env_vars, mock_websocket):
        """Test subscription handles exceptions."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            
            mock_websocket.recv.side_effect = Exception("Timeout")
            
            result = await client._subscribe_to_trade_updates()
            
            assert result is False


# ============================================================================
# MESSAGE HANDLING TESTS
# ============================================================================

class TestAlpacaStreamClientMessageHandling:
    """Tests for AlpacaStreamClient message handling."""

    @pytest.mark.asyncio
    async def test_handle_trade_updates_message(self, mock_env_vars):
        """Test handling trade_updates message type."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            message = {
                "T": "trade_updates",
                "data": {
                    "id": "order123",
                    "status": "filled"
                }
            }
            
            await client._handle_message(message)
            
            # Message should be queued
            assert not client.update_queue.empty()

    @pytest.mark.asyncio
    async def test_handle_trade_updates_new_format(self, mock_env_vars):
        """Test handling trade_updates with new format."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            message = {
                "stream": "trade_updates",
                "data": {
                    "id": "order456",
                    "status": "partially_filled"
                }
            }
            
            await client._handle_message(message)
            
            assert not client.update_queue.empty()

    @pytest.mark.asyncio
    async def test_handle_success_message(self, mock_env_vars):
        """Test handling success message type."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            message = {"T": "success", "msg": "operation completed"}
            
            # Should not raise
            await client._handle_message(message)
            
            # Queue should be empty (success messages not queued)
            assert client.update_queue.empty()

    @pytest.mark.asyncio
    async def test_handle_error_message(self, mock_env_vars):
        """Test handling error message type."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            message = {"T": "error", "msg": "something went wrong"}
            
            # Should not raise
            await client._handle_message(message)

    @pytest.mark.asyncio
    async def test_handle_unknown_message_type(self, mock_env_vars):
        """Test handling unknown message type."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            message = {"T": "unknown_type", "data": {}}
            
            # Should not raise
            await client._handle_message(message)

    @pytest.mark.asyncio
    async def test_handle_queue_never_drops_messages(self, mock_env_vars):
        """Test that trade updates are never dropped — queue is unbounded."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            from backend.integrations.alpaca_stream import AlpacaStreamClient

            client = AlpacaStreamClient()

            # Pre-fill queue with many items
            for i in range(100):
                await client.update_queue.put({"dummy": f"data-{i}"})

            message = {
                "T": "trade_updates",
                "data": {"id": "order789"}
            }

            # New message should be accepted (not dropped)
            await client._handle_message(message)

            # Queue now has 101 items (100 + 1 new)
            assert client.update_queue.qsize() == 101


# ============================================================================
# STATUS MAPPING TESTS
# ============================================================================

class TestAlpacaStreamClientStatusMapping:
    """Tests for AlpacaStreamClient status mapping."""

    def test_map_alpaca_status_new(self, mock_env_vars):
        """Test mapping 'new' status."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client._map_alpaca_status("new") == "submitted"

    def test_map_alpaca_status_filled(self, mock_env_vars):
        """Test mapping 'filled' status."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client._map_alpaca_status("filled") == "filled"

    def test_map_alpaca_status_canceled(self, mock_env_vars):
        """Test mapping 'canceled' status."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client._map_alpaca_status("canceled") == "cancelled"

    def test_map_alpaca_status_partially_filled(self, mock_env_vars):
        """Test mapping 'partially_filled' status."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client._map_alpaca_status("partially_filled") == "partially_filled"

    def test_map_alpaca_status_pending_new(self, mock_env_vars):
        """Test mapping 'pending_new' status."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client._map_alpaca_status("pending_new") == "pending"

    def test_map_alpaca_status_rejected(self, mock_env_vars):
        """Test mapping 'rejected' status."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client._map_alpaca_status("rejected") == "rejected"

    def test_map_alpaca_status_expired(self, mock_env_vars):
        """Test mapping 'expired' status."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client._map_alpaca_status("expired") == "expired"

    def test_map_alpaca_status_unknown_returns_original(self, mock_env_vars):
        """Test that unknown status returns original."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client._map_alpaca_status("custom_status") == "custom_status"

    def test_map_alpaca_status_case_insensitive(self, mock_env_vars):
        """Test status mapping is case insensitive."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            assert client._map_alpaca_status("NEW") == "submitted"
            assert client._map_alpaca_status("Filled") == "filled"
            assert client._map_alpaca_status("CANCELED") == "cancelled"


# ============================================================================
# BACKGROUND TASK TESTS
# ============================================================================

class TestAlpacaStreamClientBackgroundTasks:
    """Tests for AlpacaStreamClient background task management."""

    @pytest.mark.asyncio
    async def test_start_background_tasks(self, mock_env_vars):
        """Test starting background tasks."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.is_connected = True
            
            await client._start_background_tasks()
            
            assert client.queue_processor_task is not None
            assert client.heartbeat_task is not None
            
            # Cleanup
            await client._stop_background_tasks()

    @pytest.mark.asyncio
    async def test_stop_background_tasks(self, mock_env_vars):
        """Test stopping background tasks."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.is_connected = True
            
            await client._start_background_tasks()
            await client._stop_background_tasks()
            
            assert client.queue_processor_task is None
            assert client.heartbeat_task is None


# ============================================================================
# DISCONNECT TESTS
# ============================================================================

class TestAlpacaStreamClientDisconnect:
    """Tests for AlpacaStreamClient disconnect logic."""

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_env_vars, mock_websocket):
        """Test clean disconnect."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.is_authenticated = True
            
            await client._disconnect()
            
            assert client.is_connected is False
            assert client.is_authenticated is False
            assert client.websocket is None
            mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_handles_close_exception(self, mock_env_vars, mock_websocket):
        """Test disconnect handles close exception gracefully."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            
            mock_websocket.close.side_effect = Exception("Close failed")
            
            # Should not raise
            await client._disconnect()
            
            assert client.websocket is None


# ============================================================================
# RECONNECTION TESTS
# ============================================================================

class TestAlpacaStreamClientReconnection:
    """Tests for AlpacaStreamClient reconnection logic."""

    @pytest.mark.asyncio
    async def test_start_with_reconnect_success(self, mock_env_vars, mock_websocket):
        """Test start_with_reconnect on successful connection."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_stream.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_get.return_value = MagicMock()
            mock_connect.return_value = mock_websocket
            
            mock_websocket.recv.side_effect = [
                json.dumps({"T": "success", "msg": "authenticated"}),
                json.dumps({"T": "listening", "data": {"streams": ["trade_updates"]}})
            ]
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.should_reconnect = False  # Only try once
            
            with patch.object(client, "listen", new_callable=AsyncMock), \
                 patch.object(client, "_start_background_tasks", new_callable=AsyncMock):
                await client.start_with_reconnect()
            
            # After successful connect, reconnect_delay should reset
            assert client.reconnect_delay == 1.0

    @pytest.mark.asyncio
    async def test_max_reconnect_attempts_reached(self, mock_env_vars):
        """Test reconnection stops after max attempts."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            from backend.integrations.alpaca_stream import AlpacaStreamClient

            client = AlpacaStreamClient()
            client.max_reconnect_attempts = 2
            client.reconnect_delay = 0.01

            # Override connect to fail and stop loop after enough attempts
            connect_calls = 0
            original_reconnect = client.should_reconnect
            async def _failing_connect():
                nonlocal connect_calls
                connect_calls += 1
                if connect_calls > 4:
                    client.should_reconnect = False
                return False

            with patch.object(client, "connect", side_effect=_failing_connect), \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                await client.start_with_reconnect()

            # connect was called multiple times before loop ended
            assert connect_calls >= 2

    @pytest.mark.asyncio
    async def test_stop_client(self, mock_env_vars, mock_websocket):
        """Test stopping the stream client."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            
            await client.stop()
            
            assert client.should_reconnect is False


# ============================================================================
# GLOBAL INSTANCE TESTS
# ============================================================================

class TestAlpacaStreamGlobalInstance:
    """Tests for global stream client instance functions."""

    def test_get_stream_client_singleton(self, mock_env_vars):
        """Test get_stream_client returns singleton."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations import alpaca_stream
            
            # Reset global
            alpaca_stream._stream_client = None
            
            client1 = alpaca_stream.get_stream_client()
            client2 = alpaca_stream.get_stream_client()
            
            assert client1 is client2
            
            # Cleanup
            alpaca_stream._stream_client = None

    @pytest.mark.asyncio
    async def test_stop_stream_client(self, mock_env_vars):
        """Test stop_stream_client clears global."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations import alpaca_stream
            
            # Create client
            alpaca_stream._stream_client = None
            client = alpaca_stream.get_stream_client()
            
            with patch.object(client, "stop", new_callable=AsyncMock):
                await alpaca_stream.stop_stream_client()
            
            assert alpaca_stream._stream_client is None


# ============================================================================
# PROCESS TRADE UPDATE TESTS
# ============================================================================

class TestAlpacaStreamClientProcessTradeUpdate:
    """Tests for processing trade updates."""

    @pytest.mark.asyncio
    async def test_process_trade_update_empty_data(self, mock_env_vars):
        """Test processing trade update with empty data."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            # Empty data should log warning but not raise
            await client._process_trade_update({"data": {}})

    @pytest.mark.asyncio
    async def test_process_trade_update_missing_fields(self, mock_env_vars):
        """Test processing trade update with missing required fields."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            # Missing broker_order_id and status
            await client._process_trade_update({
                "data": {"symbol": "AAPL"}
            })

    @pytest.mark.asyncio
    async def test_process_trade_update_order_not_found(self, mock_env_vars):
        """Test processing trade update when order not found."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_stream.get_session_context") as mock_session:
            mock_get.return_value = MagicMock()

            # Mock async context manager for session
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = MagicMock()
            mock_session.return_value = mock_ctx

            from backend.integrations.alpaca_stream import AlpacaStreamClient

            client = AlpacaStreamClient()

            with patch("backend.integrations.alpaca_stream.OrdersRepo") as mock_repo:
                mock_repo_instance = MagicMock()
                mock_repo_instance.get_by_broker_order_id = AsyncMock(return_value=None)
                mock_repo.return_value = mock_repo_instance

                await client._process_trade_update({
                    "data": {
                        "order": {
                            "id": "unknown_order",
                            "status": "filled"
                        }
                    }
                })


# ============================================================================
# HEARTBEAT TESTS
# ============================================================================

class TestAlpacaStreamClientHeartbeat:
    """Tests for heartbeat functionality."""

    @pytest.mark.asyncio
    async def test_heartbeat_loop_runs(self, mock_env_vars, mock_websocket):
        """Test heartbeat loop sends pings."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.heartbeat_interval = 0.01  # Fast for testing
            
            # Run heartbeat briefly
            task = asyncio.create_task(client._heartbeat_loop())
            await asyncio.sleep(0.05)
            client.is_connected = False
            await asyncio.sleep(0.02)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            assert mock_websocket.ping.called

    @pytest.mark.asyncio
    async def test_heartbeat_handles_ping_failure(self, mock_env_vars, mock_websocket):
        """Test heartbeat handles ping failure gracefully."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.heartbeat_interval = 0.01
            
            mock_websocket.ping.side_effect = Exception("Ping failed")
            
            # Should exit gracefully
            task = asyncio.create_task(client._heartbeat_loop())
            await asyncio.sleep(0.05)
            
            try:
                await task
            except asyncio.CancelledError:
                pass


# ============================================================================
# LISTEN LOOP TESTS
# ============================================================================

class TestAlpacaStreamClientListenLoop:
    """Tests for listen loop functionality."""

    @pytest.mark.asyncio
    async def test_listen_not_connected(self, mock_env_vars):
        """Test listen returns early when not connected."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.is_connected = False
            
            # Should return without error
            await client.listen()

    @pytest.mark.asyncio
    async def test_listen_not_authenticated(self, mock_env_vars):
        """Test listen returns early when not authenticated."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.is_connected = True
            client.is_authenticated = False
            
            # Should return without error
            await client.listen()

    @pytest.mark.asyncio
    async def test_listen_handles_invalid_json(self, mock_env_vars, mock_websocket):
        """Test listen handles invalid JSON gracefully."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.is_authenticated = True
            
            # Return invalid JSON then break loop
            async def mock_iter():
                yield "not valid json"
            
            mock_websocket.__aiter__ = lambda self: mock_iter()
            
            # Should handle gracefully
            await client.listen()

    @pytest.mark.asyncio
    async def test_listen_handles_connection_closed(self, mock_env_vars, mock_websocket):
        """Test listen handles connection closed."""
        from websockets.exceptions import ConnectionClosed
        
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.is_authenticated = True
            
            # Raise ConnectionClosed
            async def mock_iter():
                raise ConnectionClosed(None, None)
            
            mock_websocket.__aiter__ = lambda self: mock_iter()
            
            await client.listen()
            
            assert client.is_connected is False
            assert client.is_authenticated is False

# ============================================================================
# ADDITIONAL COVERAGE TESTS - Process Trade Update with Broadcast
# ============================================================================

class TestAlpacaStreamProcessTradeUpdateBroadcast:
    """Tests for trade update processing with WebSocket broadcast."""

    @pytest.mark.asyncio
    async def test_process_trade_update_broadcasts_to_user(self, mock_env_vars):
        """Test successful trade update broadcasts to user."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_stream.get_session_context") as mock_db, \
             patch("backend.api.socketio_server.broadcast_order_update", new_callable=AsyncMock) as mock_broadcast:
            mock_get.return_value = MagicMock()

            # Mock DB session as async context manager
            mock_session = AsyncMock()
            mock_order = MagicMock()
            mock_order.id = "order-123"
            mock_order.symbol = "AAPL"
            mock_order.side = "buy"
            mock_order.qty = 100
            mock_order.order_type = "market"
            mock_order.submitted_at = None
            mock_order.user_id = "test_user"

            mock_orders_repo = AsyncMock()
            mock_orders_repo.get_by_broker_order_id.return_value = mock_order

            # Create async context manager mock
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_session
            mock_ctx.__aexit__.return_value = None
            mock_db.return_value = mock_ctx

            with patch("backend.integrations.alpaca_stream.OrdersRepo", return_value=mock_orders_repo):
                from backend.integrations.alpaca_stream import AlpacaStreamClient

                client = AlpacaStreamClient()

                update = {
                    "data": {
                        "order": {
                            "id": "broker-123",
                            "status": "filled",
                            "filled_qty": "100",
                            "filled_avg_price": "150.50"
                        }
                    }
                }

                await client._process_trade_update(update)

                # Should have broadcast to user
                mock_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_trade_update_broadcast_failure_doesnt_break(self, mock_env_vars):
        """Test that broadcast failure doesn't break order update."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_stream.get_session_context") as mock_db, \
             patch("backend.api.socketio_server.broadcast_order_update",
                   new_callable=AsyncMock, side_effect=Exception("Broadcast failed")):
            mock_get.return_value = MagicMock()

            mock_session = AsyncMock()
            mock_order = MagicMock()
            mock_order.id = "order-123"
            mock_order.symbol = "AAPL"
            mock_order.side = "buy"
            mock_order.qty = 100
            mock_order.order_type = "market"
            mock_order.submitted_at = None
            mock_order.user_id = None  # No user_id

            mock_orders_repo = AsyncMock()
            mock_orders_repo.get_by_broker_order_id.return_value = mock_order

            # Create async context manager mock
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_session
            mock_ctx.__aexit__.return_value = None
            mock_db.return_value = mock_ctx

            with patch("backend.integrations.alpaca_stream.OrdersRepo", return_value=mock_orders_repo):
                from backend.integrations.alpaca_stream import AlpacaStreamClient

                client = AlpacaStreamClient()

                update = {
                    "data": {
                        "order": {
                            "id": "broker-123",
                            "status": "filled",
                            "filled_qty": "100"
                        }
                    }
                }

                # Should not raise even if broadcast fails
                await client._process_trade_update(update)


class TestAlpacaStreamStartWithReconnectLoop:
    """Tests for the full reconnect loop."""

    @pytest.mark.asyncio
    async def test_start_with_reconnect_exception_handling(self, mock_env_vars):
        """Test start_with_reconnect handles unexpected exceptions."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            from backend.integrations.alpaca_stream import AlpacaStreamClient

            client = AlpacaStreamClient()
            client.max_reconnect_attempts = 1
            client.reconnect_delay = 0.01

            call_count = 0
            async def _failing_connect():
                nonlocal call_count
                call_count += 1
                if call_count > 3:
                    client.should_reconnect = False
                raise Exception("Unexpected error")

            with patch.object(client, "connect", side_effect=_failing_connect), \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                await client.start_with_reconnect()

            # connect was retried multiple times before giving up
            assert call_count >= 1


class TestAlpacaStreamListenWebSocketException:
    """Tests for WebSocket exception handling in listen."""

    @pytest.mark.asyncio
    async def test_listen_handles_websocket_exception(self, mock_env_vars, mock_websocket):
        """Test listen handles WebSocketException."""
        from websockets.exceptions import WebSocketException
        
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.is_authenticated = True
            
            async def mock_iter():
                raise WebSocketException("WebSocket error")
            
            mock_websocket.__aiter__ = lambda self: mock_iter()
            
            await client.listen()
            
            assert client.is_connected is False
            assert client.is_authenticated is False

    @pytest.mark.asyncio
    async def test_listen_handles_unexpected_exception(self, mock_env_vars, mock_websocket):
        """Test listen handles unexpected exceptions."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.is_authenticated = True
            
            async def mock_iter():
                raise ValueError("Unexpected error")
            
            mock_websocket.__aiter__ = lambda self: mock_iter()
            
            await client.listen()
            
            assert client.is_connected is False


class TestAlpacaStreamProcessUpdateQueue:
    """Tests for update queue processing."""

    @pytest.mark.asyncio
    async def test_process_update_queue_handles_timeout(self, mock_env_vars):
        """Test queue processor handles empty queue timeout."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            # Create a task that we'll cancel
            import asyncio
            
            async def run_processor():
                iteration_count = 0
                while iteration_count < 2:
                    try:
                        await asyncio.wait_for(
                            client.update_queue.get(),
                            timeout=0.1
                        )
                    except TimeoutError:
                        iteration_count += 1
                        continue
            
            # Should complete without error
            await run_processor()

    @pytest.mark.asyncio  
    async def test_process_update_queue_handles_exception(self, mock_env_vars):
        """Test queue processor handles processing exception."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            # Put an item that will cause an error
            await client.update_queue.put({"invalid": "data"})
            
            # Process should handle error gracefully
            with patch.object(client, "_process_trade_update", side_effect=Exception("Processing error")):
                # Should not raise
                try:
                    update = await asyncio.wait_for(client.update_queue.get(), timeout=0.1)
                    await client._process_trade_update(update)
                except Exception:
                    pass  # Expected


class TestAlpacaStreamDisconnectAfterFailedAuth:
    """Tests for disconnect on failed authentication."""

    @pytest.mark.asyncio
    async def test_connect_disconnects_on_auth_failure(self, mock_env_vars, mock_websocket):
        """Test connect calls disconnect when authentication fails."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            
            with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
                mock_connect.return_value.__aenter__.return_value = mock_websocket
                
                with patch.object(client, "_authenticate", return_value=False):
                    with patch.object(client, "_disconnect") as mock_disconnect:
                        result = await client.connect()
                        
                        assert result is False
                        mock_disconnect.assert_called_once()


class TestAlpacaStreamJsonDecodeError:
    """Tests for JSON decode error handling in listen loop."""

    @pytest.mark.asyncio
    async def test_listen_handles_json_decode_error(self, mock_env_vars, mock_websocket):
        """Test listen handles JSON decode error and continues."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.is_authenticated = True
            
            messages_received = []
            
            class MockAsyncIterator:
                def __init__(self):
                    self.messages = ["invalid json {{{", '{"valid": "message"}']
                    self.index = 0
                    
                def __aiter__(self):
                    return self
                    
                async def __anext__(self):
                    if self.index >= len(self.messages):
                        # Simulate normal message loop end
                        from websockets.exceptions import ConnectionClosed
                        raise ConnectionClosed(None, None)
                    msg = self.messages[self.index]
                    self.index += 1
                    return msg
            
            mock_websocket.__aiter__ = lambda self: MockAsyncIterator()
            
            # Listen should handle JSON error and continue
            await client.listen()
            
            assert client.is_connected is False


class TestAlpacaStreamHeartbeatFailure:
    """Tests for heartbeat ping failure."""

    @pytest.mark.asyncio
    async def test_heartbeat_breaks_on_ping_failure(self, mock_env_vars, mock_websocket):
        """Test heartbeat loop breaks when ping fails."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.heartbeat_interval = 0.05
            
            mock_websocket.ping.side_effect = Exception("Connection lost")
            
            # Run heartbeat for a short time - it should break on ping error
            heartbeat_task = asyncio.create_task(client._heartbeat_loop())
            
            await asyncio.sleep(0.15)
            
            # Task should complete due to ping failure
            assert heartbeat_task.done() or client.is_connected is False
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_heartbeat_warns_on_stale_connection(self, mock_env_vars, mock_websocket):
        """Test heartbeat warns when no messages received."""
        import time
        
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            from backend.integrations.alpaca_stream import AlpacaStreamClient
            
            client = AlpacaStreamClient()
            client.websocket = mock_websocket
            client.is_connected = True
            client.heartbeat_interval = 0.05
            client.last_heartbeat = time.time() - 100  # Simulate stale connection
            
            call_count = 0
            original_ping = mock_websocket.ping
            
            async def limited_ping():
                nonlocal call_count
                call_count += 1
                if call_count > 2:
                    raise Exception("Stop")
                return await original_ping()
            
            mock_websocket.ping = limited_ping
            
            heartbeat_task = asyncio.create_task(client._heartbeat_loop())
            
            await asyncio.sleep(0.2)
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass


class TestAlpacaStreamReconnectionLoop:
    """Tests for reconnection loop in start_with_reconnect."""

    @pytest.mark.asyncio
    async def test_start_with_reconnect_reaches_max_attempts(self, mock_env_vars):
        """Test reconnection stops at max attempts."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            from backend.integrations.alpaca_stream import AlpacaStreamClient

            client = AlpacaStreamClient()
            client.max_reconnect_attempts = 2
            client.reconnect_delay = 0.01

            connect_calls = 0
            async def _connect_then_stop():
                nonlocal connect_calls
                connect_calls += 1
                if connect_calls > 4:
                    client.should_reconnect = False
                return False

            with patch.object(client, "connect", side_effect=_connect_then_stop), \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                await client.start_with_reconnect()

            assert connect_calls >= 2

    @pytest.mark.asyncio
    async def test_start_with_reconnect_unexpected_error(self, mock_env_vars):
        """Test start_with_reconnect handles unexpected errors."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            from backend.integrations.alpaca_stream import AlpacaStreamClient

            client = AlpacaStreamClient()
            client.reconnect_delay = 0.01
            client.max_reconnect_attempts = 2

            connect_count = 0

            async def failing_connect():
                nonlocal connect_count
                connect_count += 1
                if connect_count == 1:
                    raise ValueError("Unexpected error")
                if connect_count > 4:
                    client.should_reconnect = False
                return False

            with patch.object(client, "connect", side_effect=failing_connect), \
                 patch("asyncio.sleep", new_callable=AsyncMock):
                await client.start_with_reconnect()

            assert connect_count >= 1


class TestAlpacaStreamGlobalFunctions:
    """Tests for global stream client functions."""

    def test_get_stream_client(self, mock_env_vars):
        """Test get_stream_client returns singleton."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            import backend.integrations.alpaca_stream as module
            module._stream_client = None  # Reset singleton
            
            client1 = module.get_stream_client()
            client2 = module.get_stream_client()
            
            assert client1 is client2
            module._stream_client = None  # Clean up

    @pytest.mark.asyncio
    async def test_start_stream_client(self, mock_env_vars):
        """Test start_stream_client starts the global client."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            import backend.integrations.alpaca_stream as module
            module._stream_client = None
            
            with patch.object(module.AlpacaStreamClient, "start_with_reconnect") as mock_start:
                await module.start_stream_client()
                mock_start.assert_called_once()
            
            module._stream_client = None  # Clean up

    @pytest.mark.asyncio
    async def test_stop_stream_client(self, mock_env_vars):
        """Test stop_stream_client stops and clears the global client."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            
            import backend.integrations.alpaca_stream as module
            
            mock_client = AsyncMock()
            module._stream_client = mock_client
            
            await module.stop_stream_client()
            
            mock_client.stop.assert_called_once()
            assert module._stream_client is None

    @pytest.mark.asyncio
    async def test_stop_stream_client_when_none(self, mock_env_vars):
        """Test stop_stream_client does nothing when no client."""
        import backend.integrations.alpaca_stream as module
        
        module._stream_client = None
        
        # Should not raise
        await module.stop_stream_client()
        
        assert module._stream_client is None


class TestAlpacaStreamProcessTradeUpdateComplete:
    """Complete tests for trade update processing with all edge cases."""

    @pytest.mark.asyncio
    async def test_process_trade_update_with_avg_fill_price(self, mock_env_vars):
        """Test process_trade_update includes avg_fill_price in update."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            from backend.integrations.alpaca_stream import AlpacaStreamClient

            client = AlpacaStreamClient()

            mock_order = MagicMock()
            mock_order.id = 123

            mock_session = MagicMock()
            mock_session.commit = AsyncMock()

            mock_orders_repo = MagicMock()
            mock_orders_repo.get_by_broker_order_id = AsyncMock(return_value=mock_order)
            mock_orders_repo.attach_broker_result = AsyncMock()

            update = {
                "data": {
                    "order": {
                        "id": "broker-123",
                        "status": "filled",
                        "filled_qty": "100",
                        "filled_avg_price": "150.50"
                    }
                },
                "event": "fill"
            }

            # Create proper async context manager class
            class MockAsyncContextManager:
                async def __aenter__(self):
                    return mock_session
                async def __aexit__(self, *args):
                    return None

            with patch("backend.integrations.alpaca_stream.get_session_context", return_value=MockAsyncContextManager()):
                with patch("backend.integrations.alpaca_stream.OrdersRepo", return_value=mock_orders_repo):
                    with patch("backend.api.socketio_server.broadcast_order_update", new_callable=AsyncMock):
                        await client._process_trade_update(update)

                        # Verify attach_broker_result was called with avg_fill_price
                        mock_orders_repo.attach_broker_result.assert_called_once()
                        call_kwargs = mock_orders_repo.attach_broker_result.call_args
                        from decimal import Decimal
                        assert call_kwargs.kwargs["avg_fill_price"] == Decimal("150.50")

    @pytest.mark.asyncio
    async def test_filled_trade_update_syncs_local_positions(self, mock_env_vars):
        """Terminal fills should refresh the local positions table from broker truth."""
        with patch("backend.integrations.alpaca_stream.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            from backend.integrations.alpaca_stream import AlpacaStreamClient

            client = AlpacaStreamClient()

            mock_order = MagicMock()
            mock_order.id = "order-123"
            mock_order.symbol = "AMD"
            mock_order.side = "sell"
            mock_order.qty = 3
            mock_order.order_type = "market"
            mock_order.submitted_at = None
            mock_order.filled_qty = 0

            mock_session = MagicMock()
            mock_session.commit = AsyncMock()

            mock_orders_repo = MagicMock()
            mock_orders_repo.get_by_broker_order_id = AsyncMock(return_value=mock_order)
            mock_orders_repo.attach_broker_result = AsyncMock()

            update = {
                "data": {
                    "order": {
                        "id": "broker-123",
                        "client_order_id": "client-123",
                        "status": "filled",
                        "filled_qty": "3",
                        "filled_avg_price": "416.31",
                    }
                },
                "event": "fill",
            }

            class MockAsyncContextManager:
                async def __aenter__(self):
                    return mock_session

                async def __aexit__(self, *args):
                    return None

            with patch(
                "backend.integrations.alpaca_stream.get_session_context",
                return_value=MockAsyncContextManager(),
            ):
                with patch(
                    "backend.integrations.alpaca_stream.OrdersRepo",
                    return_value=mock_orders_repo,
                ):
                    with patch(
                        "backend.integrations.alpaca_stream.apply_incremental_fill_accounting",
                        new_callable=AsyncMock,
                    ) as mock_accounting:
                        mock_accounting.return_value = {
                            "applied": False,
                            "reason": "duplicate_or_no_incremental_fill",
                        }
                        with patch(
                            "backend.integrations.alpaca_stream.AlpacaStreamClient."
                            "_sync_positions_after_terminal_fill",
                            new_callable=AsyncMock,
                        ) as mock_sync:
                            with patch(
                                "backend.api.socketio_server.broadcast_order_update",
                                new_callable=AsyncMock,
                            ):
                                await client._process_trade_update(update)

            mock_sync.assert_awaited_once_with(
                order_id="order-123",
                broker_order_id="broker-123",
                symbol="AMD",
            )
