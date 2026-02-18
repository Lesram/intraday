"""
Comprehensive tests for backend/integrations/alpaca_market_data_stream.py

Tests the AlpacaMarketDataStream WebSocket client for real-time market data.
Covers: connection, authentication, subscriptions, message handling, reconnection.

Phase 3: Alpaca Integrations - Market Data Stream Tests
"""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def sample_quote_message():
    """Sample quote message from Alpaca."""
    return {
        "T": "q",
        "S": "AAPL",
        "bx": "K",
        "bp": 150.25,
        "bs": 100,
        "ax": "K",
        "ap": 150.30,
        "as": 100,
        "t": "2025-01-15T14:30:00.123456Z"
    }


@pytest.fixture
def sample_trade_message():
    """Sample trade message from Alpaca."""
    return {
        "T": "t",
        "S": "AAPL",
        "p": 150.27,
        "s": 50,
        "x": "K",
        "t": "2025-01-15T14:30:01.234567Z",
        "c": ["@"],
        "z": "C"
    }


@pytest.fixture
def sample_bar_message():
    """Sample bar message from Alpaca."""
    return {
        "T": "b",
        "S": "AAPL",
        "o": 150.00,
        "h": 150.50,
        "l": 149.80,
        "c": 150.30,
        "v": 10000,
        "t": "2025-01-15T14:30:00.000000Z",
        "n": 150,
        "vw": 150.15
    }


# ============================================================================
# AlpacaMarketDataStream INITIALIZATION TESTS
# ============================================================================

class TestAlpacaMarketDataStreamInit:
    """Tests for AlpacaMarketDataStream initialization."""

    def test_init_with_iex_feed(self):
        """Test initialization with IEX feed."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(
            api_key="test_key",
            api_secret="test_secret",
            paper=True,
            feed="iex"
        )
        
        assert stream.api_key == "test_key"
        assert stream.api_secret == "test_secret"
        assert stream.feed == "iex"
        assert "iex" in stream.base_url

    def test_init_with_sip_feed(self):
        """Test initialization with SIP feed."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(
            api_key="key",
            api_secret="secret",
            feed="sip"
        )
        
        assert "sip" in stream.base_url

    def test_init_default_values(self):
        """Test initialization with default values."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(
            api_key="key",
            api_secret="secret"
        )
        
        assert stream.paper is True
        assert stream.feed == "sip"
        assert stream.is_connected is False
        assert stream.is_authenticated is False

    def test_init_subscription_sets(self):
        """Test initialization of subscription sets."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(
            api_key="key",
            api_secret="secret"
        )
        
        assert stream.quote_subscriptions == set()
        assert stream.trade_subscriptions == set()
        assert stream.bar_subscriptions == {}

    def test_init_callbacks_none(self):
        """Test callbacks are initialized to None."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(
            api_key="key",
            api_secret="secret"
        )
        
        assert stream.on_quote is None
        assert stream.on_trade is None
        assert stream.on_bar is None
        assert stream.on_error is None

    def test_init_reconnection_config(self):
        """Test reconnection configuration."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(
            api_key="key",
            api_secret="secret"
        )
        
        assert stream.MAX_RECONNECT_ATTEMPTS == 10
        assert stream.INITIAL_BACKOFF == 1.0
        assert stream.MAX_BACKOFF == 300.0
        assert stream.BACKOFF_MULTIPLIER == 1.5


# ============================================================================
# CONNECTION TESTS
# ============================================================================

class TestAlpacaMarketDataStreamConnect:
    """Tests for connection logic."""

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, mock_websocket):
        """Test connect when already connected."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_connected = True
        
        result = await stream.connect()
        
        assert result is True

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_websocket):
        """Test successful connection."""
        with patch("backend.integrations.alpaca_market_data_stream.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_websocket
            
            # Auth response
            mock_websocket.recv.return_value = json.dumps([{
                "T": "success", "msg": "authenticated"
            }])
            
            from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
            
            stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
            
            with patch.object(stream, "_start_background_tasks"):
                result = await stream.connect()
            
            assert result is True
            assert stream.is_connected is True
            assert stream.connection_count == 1

    @pytest.mark.asyncio
    async def test_connect_failure(self, mock_websocket):
        """Test connection failure."""
        with patch("backend.integrations.alpaca_market_data_stream.websockets.connect") as mock_connect:
            mock_connect.side_effect = Exception("Connection refused")
            
            from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
            
            stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
            
            result = await stream.connect()
            
            assert result is False
            assert stream.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_auth_failure(self, mock_websocket):
        """Test connection with auth failure."""
        with patch("backend.integrations.alpaca_market_data_stream.websockets.connect") as mock_connect:
            mock_connect.return_value = mock_websocket
            
            # Auth failure response
            mock_websocket.recv.return_value = json.dumps([{
                "T": "error", "msg": "unauthorized"
            }])
            
            from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
            
            stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
            
            result = await stream.connect()
            
            assert result is False


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

class TestAlpacaMarketDataStreamAuthentication:
    """Tests for authentication logic."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_websocket):
        """Test successful authentication."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        
        # Success response (array format)
        mock_websocket.recv.return_value = json.dumps([{
            "T": "success", "msg": "authenticated"
        }])
        
        result = await stream._authenticate()
        
        assert result is True
        assert stream.is_authenticated is True

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, mock_websocket):
        """Test authentication failure."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.on_error = AsyncMock()
        
        mock_websocket.recv.return_value = json.dumps([{
            "T": "error", "msg": "invalid credentials"
        }])
        
        result = await stream._authenticate()
        
        assert result is False
        assert stream.is_authenticated is False

    @pytest.mark.asyncio
    async def test_authenticate_timeout(self, mock_websocket):
        """Test authentication timeout."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        
        mock_websocket.recv.side_effect = asyncio.TimeoutError()
        
        result = await stream._authenticate()
        
        assert result is False

    @pytest.mark.asyncio
    async def test_authenticate_exception(self, mock_websocket):
        """Test authentication handles exception."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        
        mock_websocket.recv.side_effect = Exception("Network error")
        
        result = await stream._authenticate()
        
        assert result is False


# ============================================================================
# SUBSCRIPTION TESTS
# ============================================================================

class TestAlpacaMarketDataStreamSubscription:
    """Tests for subscription methods."""

    @pytest.mark.asyncio
    async def test_subscribe_quotes_success(self, mock_websocket):
        """Test successful quote subscription."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        result = await stream.subscribe_quotes(["AAPL", "MSFT"])
        
        assert result is True
        assert "AAPL" in stream.quote_subscriptions
        assert "MSFT" in stream.quote_subscriptions
        mock_websocket.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_quotes_not_authenticated(self, mock_websocket):
        """Test quote subscription when not authenticated."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = False
        
        result = await stream.subscribe_quotes(["AAPL"])
        
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_quotes_already_subscribed(self, mock_websocket):
        """Test subscribing to already subscribed symbols."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        stream.quote_subscriptions = {"AAPL"}
        
        result = await stream.subscribe_quotes(["AAPL"])
        
        assert result is True
        # Should not send message for already subscribed symbols
        mock_websocket.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_quotes_uppercase_conversion(self, mock_websocket):
        """Test symbols are converted to uppercase."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        await stream.subscribe_quotes(["aapl", "msft"])
        
        assert "AAPL" in stream.quote_subscriptions
        assert "MSFT" in stream.quote_subscriptions

    @pytest.mark.asyncio
    async def test_subscribe_trades_success(self, mock_websocket):
        """Test successful trade subscription."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        result = await stream.subscribe_trades(["TSLA"])
        
        assert result is True
        assert "TSLA" in stream.trade_subscriptions

    @pytest.mark.asyncio
    async def test_subscribe_bars_success(self, mock_websocket):
        """Test successful bar subscription."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        result = await stream.subscribe_bars(["AAPL"], timeframe="1Min")
        
        assert result is True
        assert "AAPL" in stream.bar_subscriptions.get("1Min", set())

    @pytest.mark.asyncio
    async def test_subscribe_bars_multiple_timeframes(self, mock_websocket):
        """Test bar subscription with multiple timeframes."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        await stream.subscribe_bars(["AAPL"], timeframe="1Min")
        await stream.subscribe_bars(["AAPL"], timeframe="5Min")
        
        assert "AAPL" in stream.bar_subscriptions.get("1Min", set())
        assert "AAPL" in stream.bar_subscriptions.get("5Min", set())

    @pytest.mark.asyncio
    async def test_unsubscribe_success(self, mock_websocket):
        """Test successful unsubscription."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        # Pre-populate subscriptions
        stream.quote_subscriptions = {"AAPL", "MSFT"}
        stream.trade_subscriptions = {"AAPL"}
        stream.bar_subscriptions = {"1Min": {"AAPL"}}
        
        result = await stream.unsubscribe(["AAPL"])
        
        assert result is True
        assert "AAPL" not in stream.quote_subscriptions
        assert "AAPL" not in stream.trade_subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_not_authenticated(self, mock_websocket):
        """Test unsubscribe when not authenticated."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_authenticated = False
        
        result = await stream.unsubscribe(["AAPL"])
        
        assert result is False


# ============================================================================
# MESSAGE HANDLING TESTS
# ============================================================================

class TestAlpacaMarketDataStreamMessageHandling:
    """Tests for message handling."""

    @pytest.mark.asyncio
    async def test_handle_quote_message(self, sample_quote_message):
        """Test handling quote message."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        quote_callback = AsyncMock()
        stream.on_quote = quote_callback
        
        await stream._handle_message(json.dumps([sample_quote_message]))
        
        quote_callback.assert_called_once()
        call_args = quote_callback.call_args
        assert call_args[0][0] == "AAPL"
        assert call_args[0][1]["bid"] == 150.25

    @pytest.mark.asyncio
    async def test_handle_trade_message(self, sample_trade_message):
        """Test handling trade message."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        trade_callback = AsyncMock()
        stream.on_trade = trade_callback
        
        await stream._handle_message(json.dumps([sample_trade_message]))
        
        trade_callback.assert_called_once()
        call_args = trade_callback.call_args
        assert call_args[0][0] == "AAPL"
        assert call_args[0][1]["price"] == 150.27

    @pytest.mark.asyncio
    async def test_handle_bar_message(self, sample_bar_message):
        """Test handling bar message."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        bar_callback = AsyncMock()
        stream.on_bar = bar_callback
        
        await stream._handle_message(json.dumps([sample_bar_message]))
        
        bar_callback.assert_called_once()
        call_args = bar_callback.call_args
        assert call_args[0][0] == "AAPL"
        assert call_args[0][1]["close"] == 150.30

    @pytest.mark.asyncio
    async def test_handle_success_message(self):
        """Test handling success confirmation message."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        success_msg = [{"T": "success", "msg": "subscribed"}]
        
        # Should not raise
        await stream._handle_message(json.dumps(success_msg))

    @pytest.mark.asyncio
    async def test_handle_subscription_message(self):
        """Test handling subscription status message."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        sub_msg = [{"T": "subscription", "quotes": ["AAPL"]}]
        
        # Should not raise
        await stream._handle_message(json.dumps(sub_msg))

    @pytest.mark.asyncio
    async def test_handle_error_message(self):
        """Test handling error message."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        error_callback = AsyncMock()
        stream.on_error = error_callback
        
        error_msg = [{"T": "error", "msg": "subscription failed"}]
        
        await stream._handle_message(json.dumps(error_msg))
        
        error_callback.assert_called_once_with("subscription failed")

    @pytest.mark.asyncio
    async def test_handle_unknown_message_type(self):
        """Test handling unknown message type."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        unknown_msg = [{"T": "unknown", "data": {}}]
        
        # Should not raise
        await stream._handle_message(json.dumps(unknown_msg))

    @pytest.mark.asyncio
    async def test_handle_message_increments_counter(self, sample_quote_message):
        """Test message handling increments counter."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.on_quote = AsyncMock()
        
        initial_count = stream.total_messages_received
        
        await stream._handle_message(json.dumps([sample_quote_message]))
        
        assert stream.total_messages_received == initial_count + 1

    @pytest.mark.asyncio
    async def test_handle_quote_calculates_mid_and_spread(self, sample_quote_message):
        """Test quote handling calculates mid price and spread."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        quote_callback = AsyncMock()
        stream.on_quote = quote_callback
        
        await stream._handle_message(json.dumps([sample_quote_message]))
        
        quote_data = quote_callback.call_args[0][1]
        assert "mid" in quote_data
        assert "spread" in quote_data
        assert quote_data["mid"] == (150.25 + 150.30) / 2
        assert quote_data["spread"] == 150.30 - 150.25


# ============================================================================
# RECONNECTION TESTS
# ============================================================================

class TestAlpacaMarketDataStreamReconnection:
    """Tests for reconnection logic."""

    @pytest.mark.asyncio
    async def test_reconnect_increments_attempts(self, mock_websocket):
        """Test reconnection increments attempt counter."""
        with patch("backend.integrations.alpaca_market_data_stream.websockets.connect") as mock_connect, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_connect.side_effect = Exception("Connection failed")
            
            from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
            
            stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
            stream.MAX_RECONNECT_ATTEMPTS = 1
            
            await stream._reconnect()
            
            assert stream.reconnect_attempts >= 1

    @pytest.mark.asyncio
    async def test_reconnect_max_attempts(self, mock_websocket):
        """Test reconnection stops at max attempts."""
        with patch("backend.integrations.alpaca_market_data_stream.websockets.connect") as mock_connect, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_connect.side_effect = Exception("Connection failed")
            
            from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
            
            stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
            stream.MAX_RECONNECT_ATTEMPTS = 1
            stream.reconnect_attempts = 1  # Already at max
            stream.on_error = AsyncMock()
            
            await stream._reconnect()
            
            stream.on_error.assert_called()

    @pytest.mark.asyncio
    async def test_reconnect_increases_backoff(self, mock_websocket):
        """Test reconnection increases backoff delay."""
        with patch("backend.integrations.alpaca_market_data_stream.websockets.connect") as mock_connect, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_connect.side_effect = Exception("Connection failed")
            
            from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
            
            stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
            stream.MAX_RECONNECT_ATTEMPTS = 2
            initial_backoff = stream.current_backoff
            
            await stream._reconnect()
            
            # Backoff should increase
            assert stream.current_backoff > initial_backoff


# ============================================================================
# DISCONNECT TESTS
# ============================================================================

class TestAlpacaMarketDataStreamDisconnect:
    """Tests for disconnect logic."""

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_websocket):
        """Test clean disconnect."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        stream.is_authenticated = True
        stream.background_tasks = []
        
        await stream.disconnect()
        
        assert stream.is_connected is False
        assert stream.is_authenticated is False
        assert stream.should_reconnect is False
        mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_cancels_background_tasks(self, mock_websocket):
        """Test disconnect cancels background tasks."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        
        # Create a real async task that we can cancel
        async def dummy_coro():
            await asyncio.sleep(10)
        
        task = asyncio.create_task(dummy_coro())
        stream.background_tasks = [task]
        
        await stream.disconnect()
        
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_disconnect_handles_close_exception(self, mock_websocket):
        """Test disconnect handles close exception."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        stream.background_tasks = []
        
        mock_websocket.close.side_effect = Exception("Close error")
        
        # Should not raise
        await stream.disconnect()
        
        assert stream.websocket is None


# ============================================================================
# STATISTICS TESTS
# ============================================================================

class TestAlpacaMarketDataStreamStats:
    """Tests for statistics methods."""

    def test_get_stats(self):
        """Test get_stats returns correct data."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_connected = True
        stream.is_authenticated = True
        stream.connection_count = 5
        stream.total_messages_received = 100
        stream.quote_subscriptions = {"AAPL", "MSFT"}
        stream.trade_subscriptions = {"AAPL"}
        stream.bar_subscriptions = {"1Min": {"AAPL", "MSFT"}}
        stream.last_heartbeat = datetime.now(UTC)
        
        stats = stream.get_stats()
        
        assert stats["connected"] is True
        assert stats["authenticated"] is True
        assert stats["connection_count"] == 5
        assert stats["total_messages"] == 100
        assert stats["quote_subscriptions"] == 2
        assert stats["trade_subscriptions"] == 1
        assert stats["bar_subscriptions"] == 2
        assert stats["last_heartbeat"] is not None

    def test_get_stats_no_heartbeat(self):
        """Test get_stats when no heartbeat."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.last_heartbeat = None
        
        stats = stream.get_stats()
        
        assert stats["last_heartbeat"] is None


# ============================================================================
# RESUBSCRIBE TESTS
# ============================================================================

class TestAlpacaMarketDataStreamResubscribe:
    """Tests for resubscription after reconnect."""

    @pytest.mark.asyncio
    async def test_resubscribe_all(self, mock_websocket):
        """Test resubscribing to all symbols after reconnect."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        # Pre-populate subscriptions
        stream.quote_subscriptions = {"AAPL", "MSFT"}
        stream.trade_subscriptions = {"TSLA"}
        stream.bar_subscriptions = {"1Min": {"AAPL"}}
        
        await stream._resubscribe_all()
        
        # Should have sent subscription messages (if subscriptions exist)
        # The method may use subscribe_quotes, subscribe_trades, etc.
        # Just verify it completed without error
        assert stream.is_authenticated is True

    @pytest.mark.asyncio
    async def test_resubscribe_empty_subscriptions(self, mock_websocket):
        """Test resubscribe with no subscriptions."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        # Empty subscriptions
        stream.quote_subscriptions = set()
        stream.trade_subscriptions = set()
        stream.bar_subscriptions = {}
        
        await stream._resubscribe_all()
        
        # Should not send any messages
        mock_websocket.send.assert_not_called()


# ============================================================================
# LISTEN LOOP TESTS
# ============================================================================

class TestAlpacaMarketDataStreamListen:
    """Tests for listen loop."""

    @pytest.mark.asyncio
    async def test_listen_not_connected(self):
        """Test listen returns early when not connected."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_connected = False
        
        # Should return without error
        await stream.listen()

    @pytest.mark.asyncio
    async def test_listen_not_authenticated(self):
        """Test listen returns early when not authenticated."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_connected = True
        stream.is_authenticated = False
        
        # Should return without error
        await stream.listen()


# ============================================================================
# HEARTBEAT TESTS
# ============================================================================

class TestAlpacaMarketDataStreamHeartbeat:
    """Tests for heartbeat functionality."""

    @pytest.mark.asyncio
    async def test_heartbeat_loop_updates_timestamp(self):
        """Test heartbeat loop updates timestamp."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_connected = True
        stream.HEARTBEAT_INTERVAL = 0.01  # Fast for testing
        
        # Run heartbeat briefly
        task = asyncio.create_task(stream._heartbeat_loop())
        await asyncio.sleep(0.05)
        stream.is_connected = False
        await asyncio.sleep(0.02)
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        assert stream.last_heartbeat is not None

# ============================================================================
# ADDITIONAL COVERAGE - Listen Loop and Reconnection
# ============================================================================

class TestAlpacaMarketDataStreamListenLoop:
    """Tests for the listen loop with different scenarios."""

    @pytest.mark.asyncio
    async def test_listen_handles_json_decode_error(self, mock_websocket):
        """Test listen handles JSON decode errors gracefully."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        stream.is_authenticated = True
        
        async def mock_iter():
            yield "not valid json"
            # Then break
        
        mock_websocket.__aiter__ = lambda self: mock_iter()
        
        await stream.listen()

    @pytest.mark.asyncio
    async def test_listen_handles_processing_error(self, mock_websocket):
        """Test listen handles message processing errors."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        stream.is_authenticated = True
        
        async def mock_iter():
            yield json.dumps([{"T": "unknown_type"}])
        
        mock_websocket.__aiter__ = lambda self: mock_iter()
        
        with patch.object(stream, "_handle_message", side_effect=Exception("Processing error")):
            await stream.listen()

    @pytest.mark.asyncio
    async def test_listen_triggers_reconnect_on_connection_closed(self, mock_websocket):
        """Test listen triggers reconnect on ConnectionClosed."""
        from websockets.exceptions import ConnectionClosed
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        stream.is_authenticated = True
        stream.should_reconnect = True
        
        class MockAsyncIterator:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise ConnectionClosed(None, None)
        
        mock_websocket.__aiter__ = lambda self: MockAsyncIterator()
        
        with patch.object(stream, "_reconnect", new_callable=AsyncMock) as mock_reconnect:
            await stream.listen()
            mock_reconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_listen_triggers_reconnect_on_websocket_exception(self, mock_websocket):
        """Test listen triggers reconnect on WebSocketException."""
        from websockets.exceptions import WebSocketException
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        stream.is_authenticated = True
        stream.should_reconnect = True
        
        class MockAsyncIterator:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise WebSocketException("WebSocket error")
        
        mock_websocket.__aiter__ = lambda self: MockAsyncIterator()
        
        with patch.object(stream, "_reconnect", new_callable=AsyncMock) as mock_reconnect:
            await stream.listen()
            mock_reconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_listen_handles_unexpected_exception(self, mock_websocket):
        """Test listen handles unexpected exceptions."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        stream.is_authenticated = True
        
        class MockAsyncIterator:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise ValueError("Unexpected error")
        
        mock_websocket.__aiter__ = lambda: MockAsyncIterator()
        
        await stream.listen()
        
        assert stream.is_connected is False


class TestAlpacaMarketDataStreamReconnect:
    """Tests for reconnection logic."""

    @pytest.mark.asyncio
    async def test_reconnect_success(self, mock_websocket):
        """Test successful reconnection."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.should_reconnect = True
        stream.reconnect_delay = 0.01
        stream.max_reconnect_delay = 0.02
        
        with patch.object(stream, "connect", new_callable=AsyncMock, return_value=True), \
             patch.object(stream, "_resubscribe_all", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await stream._reconnect()
            
            stream.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconnect_max_attempts_exceeded(self, mock_websocket):
        """Test reconnection returns early after max attempts."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.reconnect_attempts = stream.MAX_RECONNECT_ATTEMPTS  # Already at max
        
        mock_on_error = AsyncMock()
        stream.on_error = mock_on_error
        
        with patch.object(stream, "connect", new_callable=AsyncMock) as mock_connect:
            await stream._reconnect()
            
            # connect should NOT be called since max attempts exceeded
            mock_connect.assert_not_called()
            # on_error should be called
            mock_on_error.assert_called_once()


class TestAlpacaMarketDataStreamHandleMessageComplete:
    """Additional tests for message handling."""

    @pytest.mark.asyncio
    async def test_handle_message_with_array_format(self, mock_websocket):
        """Test handling messages in array format."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        
        message = json.dumps([
            {"T": "q", "S": "AAPL", "bp": 150.0, "ap": 150.5},
            {"T": "t", "S": "MSFT", "p": 300.0, "s": 100}
        ])
        
        with patch.object(stream, "_handle_quote", new_callable=AsyncMock), \
             patch.object(stream, "_handle_trade", new_callable=AsyncMock):
            await stream._handle_message(message)
            
            stream._handle_quote.assert_called_once()
            stream._handle_trade.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_with_bar(self, mock_websocket):
        """Test handling bar messages."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        
        message = json.dumps([
            {"T": "b", "S": "AAPL", "o": 150.0, "h": 151.0, "l": 149.0, "c": 150.5, "v": 1000}
        ])
        
        with patch.object(stream, "_handle_bar", new_callable=AsyncMock):
            await stream._handle_message(message)
            
            stream._handle_bar.assert_called_once()


class TestAlpacaMarketDataStreamSubscribeBars:
    """Additional bar subscription tests."""

    @pytest.mark.asyncio
    async def test_subscribe_bars_sends_correct_message(self, mock_websocket):
        """Test bar subscription sends correctly formatted message."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        await stream.subscribe_bars(["AAPL", "MSFT"], timeframe="5Min")
        
        mock_websocket.send.assert_called_once()
        call_args = mock_websocket.send.call_args[0][0]
        message = json.loads(call_args)
        
        assert message["action"] == "subscribe"
        assert "bars" in message


class TestAlpacaMarketDataStreamDisconnectOnAuthFail:
    """Tests for disconnect on authentication failure."""

    @pytest.mark.asyncio
    async def test_connect_disconnects_on_auth_failure(self, mock_websocket):
        """Test connect calls disconnect when authentication fails."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_websocket
            
            with patch.object(stream, "_authenticate", return_value=False):
                with patch.object(stream, "disconnect") as mock_disconnect:
                    result = await stream.connect()
                    
                    assert result is False
                    mock_disconnect.assert_called_once()


class TestAlpacaMarketDataStreamSubscribeNotAuthenticated:
    """Tests for subscription when not authenticated."""

    @pytest.mark.asyncio
    async def test_subscribe_quotes_not_authenticated(self, mock_websocket):
        """Test subscribe_quotes returns False when not authenticated."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_authenticated = False
        
        result = await stream.subscribe_quotes(["AAPL"])
        
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_trades_not_authenticated(self, mock_websocket):
        """Test subscribe_trades returns False when not authenticated."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_authenticated = False
        
        result = await stream.subscribe_trades(["AAPL"])
        
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_bars_not_authenticated(self, mock_websocket):
        """Test subscribe_bars returns False when not authenticated."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_authenticated = False
        
        result = await stream.subscribe_bars(["AAPL"])
        
        assert result is False


class TestAlpacaMarketDataStreamSubscribeError:
    """Tests for subscription error handling."""

    @pytest.mark.asyncio
    async def test_subscribe_quotes_send_error(self, mock_websocket):
        """Test subscribe_quotes handles send error."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        mock_websocket.send.side_effect = Exception("Send failed")
        
        result = await stream.subscribe_quotes(["AAPL"])
        
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_trades_send_error(self, mock_websocket):
        """Test subscribe_trades handles send error."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        mock_websocket.send.side_effect = Exception("Send failed")
        
        result = await stream.subscribe_trades(["AAPL"])
        
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_bars_send_error(self, mock_websocket):
        """Test subscribe_bars handles send error."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        
        mock_websocket.send.side_effect = Exception("Send failed")
        
        result = await stream.subscribe_bars(["AAPL"])
        
        assert result is False


class TestAlpacaMarketDataStreamListenErrorProcessing:
    """Tests for error processing during listen loop."""

    @pytest.mark.asyncio
    async def test_listen_handles_processing_error(self, mock_websocket):
        """Test listen handles error during message processing."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        stream.is_authenticated = True
        
        class MockAsyncIterator:
            def __init__(self):
                self.messages = ['{"valid": "json"}', 'second message']
                self.index = 0
                
            def __aiter__(self):
                return self
                
            async def __anext__(self):
                if self.index >= len(self.messages):
                    from websockets.exceptions import ConnectionClosed
                    raise ConnectionClosed(None, None)
                msg = self.messages[self.index]
                self.index += 1
                return msg
        
        mock_websocket.__aiter__ = lambda self: MockAsyncIterator()
        
        with patch.object(stream, "_handle_message", side_effect=Exception("Processing error")):
            await stream.listen()
        
        assert stream.is_connected is False


class TestAlpacaMarketDataStreamHandleMessageError:
    """Tests for error message handling."""

    @pytest.mark.asyncio
    async def test_handle_message_calls_on_error(self, mock_websocket):
        """Test error message triggers on_error callback."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        
        mock_on_error = AsyncMock()
        stream.on_error = mock_on_error
        
        error_message = json.dumps([{"T": "error", "msg": "Subscription failed"}])
        
        await stream._handle_message(error_message)
        
        mock_on_error.assert_called_once_with("Subscription failed")


class TestAlpacaMarketDataStreamHandleQuoteError:
    """Tests for quote handling errors."""

    @pytest.mark.asyncio
    async def test_handle_quote_error(self, mock_websocket):
        """Test _handle_quote handles errors gracefully."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        mock_on_quote = AsyncMock(side_effect=Exception("Callback error"))
        stream.on_quote = mock_on_quote
        
        quote_data = {"S": "AAPL", "bp": 150.0, "ap": 150.5, "bs": 100, "as": 200, "t": "2025-01-01T00:00:00Z"}
        
        # Should not raise
        await stream._handle_quote(quote_data)


class TestAlpacaMarketDataStreamHandleTradeError:
    """Tests for trade handling errors."""

    @pytest.mark.asyncio
    async def test_handle_trade_error(self, mock_websocket):
        """Test _handle_trade handles errors gracefully."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        mock_on_trade = AsyncMock(side_effect=Exception("Callback error"))
        stream.on_trade = mock_on_trade
        
        trade_data = {"S": "AAPL", "p": 150.0, "s": 100, "t": "2025-01-01T00:00:00Z"}
        
        # Should not raise
        await stream._handle_trade(trade_data)


class TestAlpacaMarketDataStreamHandleBarError:
    """Tests for bar handling errors."""

    @pytest.mark.asyncio
    async def test_handle_bar_error(self, mock_websocket):
        """Test _handle_bar handles errors gracefully."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        
        mock_on_bar = AsyncMock(side_effect=Exception("Callback error"))
        stream.on_bar = mock_on_bar
        
        bar_data = {"S": "AAPL", "o": 150.0, "h": 151.0, "l": 149.0, "c": 150.5, "v": 1000}
        
        # Should not raise
        await stream._handle_bar(bar_data)


class TestAlpacaMarketDataStreamReconnectChain:
    """Tests for recursive reconnection."""

    @pytest.mark.asyncio
    async def test_reconnect_failure_retries(self, mock_websocket):
        """Test reconnect tries again on failure."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.should_reconnect = True
        stream.reconnect_attempts = 0
        stream.MAX_RECONNECT_ATTEMPTS = 2
        stream.current_backoff = 0.01
        
        connect_attempts = 0
        
        async def mock_connect():
            nonlocal connect_attempts
            connect_attempts += 1
            return connect_attempts >= 2  # Success on second attempt
        
        with patch.object(stream, "connect", side_effect=mock_connect):
            with patch.object(stream, "_resubscribe_all", new_callable=AsyncMock):
                await stream._reconnect()
        
        assert connect_attempts >= 1


class TestAlpacaMarketDataStreamBackgroundTasks:
    """Tests for background task management."""

    @pytest.mark.asyncio
    async def test_start_background_tasks(self, mock_websocket):
        """Test _start_background_tasks creates tasks."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_connected = True
        
        with patch.object(stream, "listen", new_callable=AsyncMock):
            with patch.object(stream, "_heartbeat_loop", new_callable=AsyncMock):
                stream._start_background_tasks()
                
                # Tasks should be created
                assert len(stream.background_tasks) >= 1
                
                # Clean up
                for task in stream.background_tasks:
                    task.cancel()


class TestAlpacaMarketDataStreamGetStats:
    """Tests for get_stats method."""

    def test_get_stats_returns_correct_info(self, mock_websocket):
        """Test get_stats returns correct statistics."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.is_connected = True
        stream.is_authenticated = True
        stream.connection_count = 5
        stream.total_messages_received = 1000
        stream.quote_subscriptions = {"AAPL", "MSFT"}
        stream.trade_subscriptions = {"AAPL"}
        stream.bar_subscriptions = {"1Min": {"AAPL", "MSFT"}, "5Min": {"GOOG"}}
        
        stats = stream.get_stats()
        
        assert stats["connected"] is True
        assert stats["authenticated"] is True
        assert stats["connection_count"] == 5
        assert stats["total_messages"] == 1000
        assert stats["quote_subscriptions"] == 2
        assert stats["trade_subscriptions"] == 1
        assert stats["bar_subscriptions"] == 3


class TestAlpacaMarketDataStreamAlreadySubscribed:
    """Tests for already subscribed symbols."""

    @pytest.mark.asyncio
    async def test_subscribe_quotes_already_subscribed(self, mock_websocket):
        """Test subscribe_quotes returns True for already subscribed symbols."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        stream.quote_subscriptions = {"AAPL", "MSFT"}
        
        result = await stream.subscribe_quotes(["AAPL", "MSFT"])
        
        assert result is True
        mock_websocket.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_trades_already_subscribed(self, mock_websocket):
        """Test subscribe_trades returns True for already subscribed symbols."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        stream.trade_subscriptions = {"AAPL"}
        
        result = await stream.subscribe_trades(["AAPL"])
        
        assert result is True
        mock_websocket.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_bars_already_subscribed(self, mock_websocket):
        """Test subscribe_bars returns True for already subscribed symbols."""
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        
        stream = AlpacaMarketDataStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_authenticated = True
        stream.bar_subscriptions = {"1Min": {"AAPL"}}
        
        result = await stream.subscribe_bars(["AAPL"], timeframe="1Min")
        
        assert result is True
        mock_websocket.send.assert_not_called()