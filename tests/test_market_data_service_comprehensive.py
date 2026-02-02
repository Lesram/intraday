"""
Comprehensive tests for backend.services.market_data_service

Targets 70%+ coverage for MarketDataService:
- Client connection management
- Subscription handling
- Rate limiting
- Stats and monitoring
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.market_data_service import (
    ClientConnection,
    MarketDataService,
    MarketDataStats,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def service():
    """Create a MarketDataService instance"""
    return MarketDataService()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket"""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ============================================================================
# CLIENT CONNECTION TESTS
# ============================================================================

class TestClientConnection:
    """Tests for ClientConnection dataclass"""
    
    def test_create_connection(self):
        """Test creating a client connection"""
        ws = MagicMock()
        conn = ClientConnection(
            client_id="test-123",
            websocket=ws,
        )
        
        assert conn.client_id == "test-123"
        assert conn.websocket == ws
        assert isinstance(conn.subscriptions, set)
        assert len(conn.subscriptions) == 0
        assert conn.message_count == 0
        
    def test_connection_with_subscriptions(self):
        """Test connection with pre-populated subscriptions"""
        ws = MagicMock()
        conn = ClientConnection(
            client_id="test-456",
            websocket=ws,
            subscriptions={"AAPL", "GOOG"},
        )
        
        assert len(conn.subscriptions) == 2
        assert "AAPL" in conn.subscriptions


# ============================================================================
# MARKET DATA STATS TESTS
# ============================================================================

class TestMarketDataStats:
    """Tests for MarketDataStats dataclass"""
    
    def test_create_default_stats(self):
        """Test creating stats with defaults"""
        stats = MarketDataStats()
        
        assert stats.total_clients == 0
        assert stats.total_subscriptions == 0
        assert stats.total_messages_sent == 0
        assert stats.alpaca_connected is False
        
    def test_create_custom_stats(self):
        """Test creating stats with values"""
        stats = MarketDataStats(
            total_clients=5,
            total_subscriptions=25,
            total_messages_sent=1000,
            uptime_seconds=3600,
            alpaca_connected=True,
        )
        
        assert stats.total_clients == 5
        assert stats.total_subscriptions == 25
        assert stats.alpaca_connected is True


# ============================================================================
# SERVICE INITIALIZATION TESTS
# ============================================================================

class TestMarketDataServiceInit:
    """Tests for MarketDataService initialization"""
    
    def test_init_defaults(self, service):
        """Test default initialization"""
        assert service.clients == {}
        assert service.is_running is False
        assert service.alpaca_connected is False
        assert service.alpaca_stream is None
        
    def test_init_constants(self, service):
        """Test configuration constants"""
        assert service.MAX_CLIENTS == 100
        assert service.MAX_SYMBOLS_PER_CLIENT == 100
        assert service.MAX_TOTAL_SYMBOLS == 500
        assert service.HEARTBEAT_INTERVAL == 30


# ============================================================================
# CLIENT MANAGEMENT TESTS
# ============================================================================

class TestClientManagement:
    """Tests for client connection management"""
    
    @pytest.mark.asyncio
    async def test_add_client(self, service, mock_websocket):
        """Test adding a client"""
        client_id = await service.add_client(mock_websocket)
        
        assert client_id is not None
        assert len(client_id) > 0
        assert client_id in service.clients
        assert service.clients[client_id].websocket == mock_websocket
        
    @pytest.mark.asyncio
    async def test_add_client_max_limit(self, service, mock_websocket):
        """Test max client limit"""
        # Add max clients
        for _ in range(service.MAX_CLIENTS):
            ws = AsyncMock()
            ws.send_json = AsyncMock()
            await service.add_client(ws)
            
        # Should raise on exceeding limit
        with pytest.raises(ValueError, match="Maximum clients"):
            await service.add_client(mock_websocket)
            
    @pytest.mark.asyncio
    async def test_remove_client(self, service, mock_websocket):
        """Test removing a client"""
        client_id = await service.add_client(mock_websocket)
        
        await service.remove_client(client_id)
        
        assert client_id not in service.clients
        mock_websocket.close.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_remove_nonexistent_client(self, service):
        """Test removing non-existent client"""
        # Should not raise
        await service.remove_client("nonexistent-id")


# ============================================================================
# SUBSCRIPTION TESTS
# ============================================================================

class TestSubscription:
    """Tests for subscription management"""
    
    @pytest.mark.asyncio
    async def test_subscribe_success(self, service, mock_websocket):
        """Test successful subscription"""
        client_id = await service.add_client(mock_websocket)
        
        # Mock Alpaca stream
        service.alpaca_stream = AsyncMock()
        service.alpaca_stream.subscribe_quotes = AsyncMock()
        
        result = await service.subscribe(client_id, "AAPL")
        
        assert result is True
        assert "AAPL" in service.clients[client_id].subscriptions
        assert client_id in service.subscriptions["AAPL"]
        
    @pytest.mark.asyncio
    async def test_subscribe_symbol_normalized(self, service, mock_websocket):
        """Test symbol is normalized to uppercase"""
        client_id = await service.add_client(mock_websocket)
        service.alpaca_stream = AsyncMock()
        service.alpaca_stream.subscribe_quotes = AsyncMock()
        
        await service.subscribe(client_id, "aapl")
        
        assert "AAPL" in service.clients[client_id].subscriptions
        
    @pytest.mark.asyncio
    async def test_subscribe_client_not_found(self, service):
        """Test subscribe with non-existent client"""
        with pytest.raises(ValueError, match="Client not found"):
            await service.subscribe("nonexistent", "AAPL")
            
    @pytest.mark.asyncio
    async def test_subscribe_max_symbols_per_client(self, service, mock_websocket):
        """Test max symbols per client limit"""
        client_id = await service.add_client(mock_websocket)
        service.alpaca_stream = AsyncMock()
        service.alpaca_stream.subscribe_quotes = AsyncMock()
        
        # Subscribe to max symbols
        for i in range(service.MAX_SYMBOLS_PER_CLIENT):
            await service.subscribe(client_id, f"SYM{i}")
            
        # Should raise on exceeding limit
        with pytest.raises(ValueError, match="Client symbol limit"):
            await service.subscribe(client_id, "EXTRA")
            
    @pytest.mark.asyncio
    async def test_unsubscribe(self, service, mock_websocket):
        """Test unsubscription"""
        client_id = await service.add_client(mock_websocket)
        service.alpaca_stream = AsyncMock()
        service.alpaca_stream.subscribe_quotes = AsyncMock()
        service.alpaca_stream.unsubscribe_quotes = AsyncMock()
        
        await service.subscribe(client_id, "AAPL")
        result = await service.unsubscribe(client_id, "AAPL")
        
        assert result is True
        assert "AAPL" not in service.clients[client_id].subscriptions
        
    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_client(self, service):
        """Test unsubscribe with non-existent client"""
        result = await service.unsubscribe("nonexistent", "AAPL")
        assert result is False


# ============================================================================
# SERVICE LIFECYCLE TESTS
# ============================================================================

class TestServiceLifecycle:
    """Tests for service start/stop"""
    
    @pytest.mark.asyncio
    async def test_start_service(self, service):
        """Test starting the service"""
        with patch("backend.services.market_data_service.AlpacaMarketDataStream") as mock_stream:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock(return_value=True)
            mock_stream.return_value = mock_instance
            
            await service.start("api_key", "api_secret", paper=True)
            
            assert service.is_running is True
            assert service.alpaca_connected is True
            assert service.start_time is not None
            
            # Cleanup
            await service.stop()
            
    @pytest.mark.asyncio
    async def test_start_already_running(self, service):
        """Test starting when already running"""
        service.is_running = True
        
        # Should return early without error
        await service.start("api_key", "api_secret")
        
    @pytest.mark.asyncio
    async def test_stop_service(self, service):
        """Test stopping the service"""
        service.is_running = True
        service.alpaca_stream = AsyncMock()
        service.alpaca_stream.disconnect = AsyncMock()
        
        await service.stop()
        
        assert service.is_running is False
        assert service.alpaca_connected is False


# ============================================================================
# RATE LIMITING TESTS
# ============================================================================

class TestRateLimiting:
    """Tests for rate limiting"""
    
    def test_rate_limiters_initialized(self, service):
        """Test rate limiters are initialized"""
        from collections import defaultdict
        
        assert isinstance(service.rate_limiters, defaultdict)
        
    @pytest.mark.asyncio
    async def test_message_rate_limit(self, service):
        """Test message rate limit constant"""
        assert service.MESSAGE_RATE_LIMIT == 10


# ============================================================================
# HELPER METHOD TESTS  
# ============================================================================

class TestHelperMethods:
    """Tests for private helper methods"""
    
    @pytest.mark.asyncio
    async def test_send_to_client_success(self, service, mock_websocket):
        """Test sending message to client"""
        client_id = await service.add_client(mock_websocket)
        
        await service._send_to_client(client_id, {"type": "test", "data": "hello"})
        
        mock_websocket.send_json.assert_called()
        
    @pytest.mark.asyncio
    async def test_send_to_client_not_found(self, service):
        """Test sending to non-existent client"""
        # Should not raise
        await service._send_to_client("nonexistent", {"type": "test"})


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegrationScenarios:
    """Tests for integrated scenarios"""
    
    @pytest.mark.asyncio
    async def test_full_subscription_flow(self, service, mock_websocket):
        """Test complete subscription workflow"""
        # Add client
        client_id = await service.add_client(mock_websocket)
        
        # Mock Alpaca
        service.alpaca_stream = AsyncMock()
        service.alpaca_stream.subscribe_quotes = AsyncMock()
        service.alpaca_stream.unsubscribe_quotes = AsyncMock()
        
        # Subscribe to multiple symbols
        await service.subscribe(client_id, "AAPL")
        await service.subscribe(client_id, "GOOG")
        await service.subscribe(client_id, "MSFT")
        
        assert len(service.clients[client_id].subscriptions) == 3
        
        # Unsubscribe from one
        await service.unsubscribe(client_id, "GOOG")
        
        assert len(service.clients[client_id].subscriptions) == 2
        assert "GOOG" not in service.clients[client_id].subscriptions
        
        # Remove client (should cleanup remaining)
        await service.remove_client(client_id)
        
        assert client_id not in service.clients
        
    @pytest.mark.asyncio
    async def test_multiple_clients_same_symbol(self, service):
        """Test multiple clients subscribing to same symbol"""
        service.alpaca_stream = AsyncMock()
        service.alpaca_stream.subscribe_quotes = AsyncMock()
        
        # Create multiple clients
        clients = []
        for _ in range(3):
            ws = AsyncMock()
            ws.send_json = AsyncMock()
            ws.close = AsyncMock()
            client_id = await service.add_client(ws)
            clients.append(client_id)
            
        # All subscribe to AAPL
        for client_id in clients:
            await service.subscribe(client_id, "AAPL")
            
        # AAPL should have all clients
        assert len(service.subscriptions["AAPL"]) == 3
        
        # Alpaca subscribe should only be called once
        service.alpaca_stream.subscribe_quotes.assert_called_once()
