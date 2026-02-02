"""
Unit Tests for MarketDataService

Tests cover:
- Client management (add/remove)
- Subscription management (subscribe/unsubscribe)
- Message broadcasting
- Rate limiting
- Background tasks
- Error handling
- Statistics

Created: October 16, 2025 - Phase 7 Day 1
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.market_data_service import (
    MarketDataService,
    MarketDataStats,
    get_market_data_service,
)


@pytest.fixture
def service():
    """Create a fresh MarketDataService instance for each test"""
    return MarketDataService()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket"""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_alpaca_stream():
    """Create a mock AlpacaMarketDataStream"""
    stream = AsyncMock()
    stream.connect = AsyncMock(return_value=True)
    stream.disconnect = AsyncMock()
    stream.subscribe_quotes = AsyncMock(return_value=True)
    stream.unsubscribe = AsyncMock(return_value=True)
    return stream


class TestClientManagement:
    """Test client connection management"""

    @pytest.mark.asyncio
    async def test_add_client_success(self, service, mock_websocket):
        """Test adding a client successfully"""
        client_id = await service.add_client(mock_websocket)

        assert client_id is not None
        assert client_id in service.clients
        assert service.clients[client_id].websocket == mock_websocket
        assert len(service.clients[client_id].subscriptions) == 0

        # Verify welcome message sent
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "connected"
        assert call_args["client_id"] == client_id

    @pytest.mark.asyncio
    async def test_add_client_max_limit(self, service, mock_websocket):
        """Test adding clients beyond max limit"""
        # Fill up to max clients
        original_max = MarketDataService.MAX_CLIENTS
        MarketDataService.MAX_CLIENTS = 3

        try:
            clients = []
            for _ in range(3):
                ws = AsyncMock()
                ws.send_json = AsyncMock()
                client_id = await service.add_client(ws)
                clients.append(client_id)

            # Try to add one more - should fail
            with pytest.raises(ValueError, match="Maximum clients"):
                await service.add_client(mock_websocket)

        finally:
            MarketDataService.MAX_CLIENTS = original_max

    @pytest.mark.asyncio
    async def test_remove_client(self, service, mock_websocket):
        """Test removing a client"""
        client_id = await service.add_client(mock_websocket)

        await service.remove_client(client_id)

        assert client_id not in service.clients
        mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_client_with_subscriptions(self, service, mock_websocket, mock_alpaca_stream):
        """Test removing a client with active subscriptions"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        client_id = await service.add_client(mock_websocket)
        await service.subscribe(client_id, "AAPL")
        await service.subscribe(client_id, "TSLA")

        await service.remove_client(client_id)

        # Verify client removed
        assert client_id not in service.clients

        # Verify subscriptions cleaned up
        assert "AAPL" not in service.subscriptions
        assert "TSLA" not in service.subscriptions


class TestSubscriptionManagement:
    """Test symbol subscription management"""

    @pytest.mark.asyncio
    async def test_subscribe_success(self, service, mock_websocket, mock_alpaca_stream):
        """Test subscribing to a symbol"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        client_id = await service.add_client(mock_websocket)

        result = await service.subscribe(client_id, "AAPL")

        assert result is True
        assert "AAPL" in service.clients[client_id].subscriptions
        assert client_id in service.subscriptions["AAPL"]

        # Verify Alpaca subscription
        mock_alpaca_stream.subscribe_quotes.assert_called_once_with(["AAPL"])

    @pytest.mark.asyncio
    async def test_subscribe_multiple_clients_same_symbol(self, service, mock_alpaca_stream):
        """Test multiple clients subscribing to same symbol"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        # Add two clients
        ws1 = AsyncMock()
        ws1.send_json = AsyncMock()
        client1 = await service.add_client(ws1)

        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()
        client2 = await service.add_client(ws2)

        # Both subscribe to AAPL
        await service.subscribe(client1, "AAPL")
        await service.subscribe(client2, "AAPL")

        # Verify both clients subscribed
        assert client1 in service.subscriptions["AAPL"]
        assert client2 in service.subscriptions["AAPL"]

        # Alpaca should only be called once (for first subscription)
        assert mock_alpaca_stream.subscribe_quotes.call_count == 1

    @pytest.mark.asyncio
    async def test_subscribe_symbol_normalization(self, service, mock_websocket, mock_alpaca_stream):
        """Test symbol is normalized to uppercase"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        client_id = await service.add_client(mock_websocket)

        await service.subscribe(client_id, "aapl")

        assert "AAPL" in service.subscriptions
        assert "aapl" not in service.subscriptions

    @pytest.mark.asyncio
    async def test_subscribe_max_symbols_per_client(self, service, mock_websocket, mock_alpaca_stream):
        """Test max symbols per client limit"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        original_max = MarketDataService.MAX_SYMBOLS_PER_CLIENT
        MarketDataService.MAX_SYMBOLS_PER_CLIENT = 3

        try:
            client_id = await service.add_client(mock_websocket)

            # Subscribe to max symbols
            await service.subscribe(client_id, "AAPL")
            await service.subscribe(client_id, "TSLA")
            await service.subscribe(client_id, "MSFT")

            # Try one more - should fail
            with pytest.raises(ValueError, match="Client symbol limit"):
                await service.subscribe(client_id, "GOOGL")

        finally:
            MarketDataService.MAX_SYMBOLS_PER_CLIENT = original_max

    @pytest.mark.asyncio
    async def test_unsubscribe_success(self, service, mock_websocket, mock_alpaca_stream):
        """Test unsubscribing from a symbol"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        client_id = await service.add_client(mock_websocket)
        await service.subscribe(client_id, "AAPL")

        result = await service.unsubscribe(client_id, "AAPL")

        assert result is True
        assert "AAPL" not in service.clients[client_id].subscriptions
        assert "AAPL" not in service.subscriptions

        # Verify Alpaca unsubscription (since last client)
        mock_alpaca_stream.unsubscribe.assert_called_once_with(["AAPL"])

    @pytest.mark.asyncio
    async def test_unsubscribe_multiple_clients(self, service, mock_alpaca_stream):
        """Test unsubscribing when multiple clients are subscribed"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        # Add two clients
        ws1 = AsyncMock()
        ws1.send_json = AsyncMock()
        client1 = await service.add_client(ws1)

        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()
        client2 = await service.add_client(ws2)

        # Both subscribe to AAPL
        await service.subscribe(client1, "AAPL")
        await service.subscribe(client2, "AAPL")

        # Client 1 unsubscribes
        await service.unsubscribe(client1, "AAPL")

        # Client 2 should still be subscribed
        assert client2 in service.subscriptions["AAPL"]

        # Alpaca should NOT unsubscribe (client 2 still needs it)
        mock_alpaca_stream.unsubscribe.assert_not_called()

        # Client 2 unsubscribes
        await service.unsubscribe(client2, "AAPL")

        # Now Alpaca should unsubscribe
        mock_alpaca_stream.unsubscribe.assert_called_once()


class TestMessageBroadcasting:
    """Test message broadcasting to clients"""

    @pytest.mark.asyncio
    async def test_broadcast_quote(self, service, mock_alpaca_stream):
        """Test broadcasting a quote to subscribed clients"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True
        service.is_running = True

        # Start background broadcaster
        service.background_tasks.append(
            asyncio.create_task(service._message_broadcaster())
        )

        # Add two clients, both subscribe to AAPL
        ws1 = AsyncMock()
        ws1.send_json = AsyncMock()
        client1 = await service.add_client(ws1)
        await service.subscribe(client1, "AAPL")

        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()
        client2 = await service.add_client(ws2)
        await service.subscribe(client2, "AAPL")

        # Broadcast quote
        quote_data = {
            "bid": 150.25,
            "ask": 150.30,
            "last": 150.28
        }

        await service.broadcast_quote("AAPL", quote_data)

        # Allow broadcaster to process
        await asyncio.sleep(0.1)

        # Both clients should receive the quote
        assert ws1.send_json.call_count >= 2  # Welcome + quote
        assert ws2.send_json.call_count >= 2  # Welcome + quote

        # Cleanup
        service.is_running = False
        for task in service.background_tasks:
            task.cancel()

    @pytest.mark.asyncio
    async def test_rate_limiting(self, service):
        """Test message rate limiting"""
        # Send messages rapidly
        for _ in range(15):  # More than limit (10)
            result = service._check_rate_limit("AAPL")

        # Should hit rate limit
        result = service._check_rate_limit("AAPL")
        assert result is False  # Rate limit exceeded

    @pytest.mark.asyncio
    async def test_broadcast_only_to_subscribers(self, service, mock_alpaca_stream):
        """Test quote is only sent to subscribed clients"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True
        service.is_running = True

        # Start broadcaster
        service.background_tasks.append(
            asyncio.create_task(service._message_broadcaster())
        )

        # Client 1 subscribes to AAPL
        ws1 = AsyncMock()
        ws1.send_json = AsyncMock()
        client1 = await service.add_client(ws1)
        await service.subscribe(client1, "AAPL")

        # Client 2 subscribes to TSLA
        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()
        client2 = await service.add_client(ws2)
        await service.subscribe(client2, "TSLA")

        # Broadcast AAPL quote
        await service.broadcast_quote("AAPL", {"last": 150.00})
        await asyncio.sleep(0.1)

        # Client 1 should receive it
        aapl_calls = [call for call in ws1.send_json.call_args_list
                     if len(call[0]) > 0 and call[0][0].get("type") == "quote"]
        assert len(aapl_calls) > 0

        # Client 2 should NOT receive it (subscribed to TSLA, not AAPL)
        quote_calls = [call for call in ws2.send_json.call_args_list
                      if len(call[0]) > 0 and call[0][0].get("type") == "quote"
                      and call[0][0].get("symbol") == "AAPL"]
        assert len(quote_calls) == 0

        # Cleanup
        service.is_running = False
        for task in service.background_tasks:
            task.cancel()


class TestBackgroundTasks:
    """Test background tasks (heartbeat, cleanup)"""

    @pytest.mark.asyncio
    async def test_heartbeat_monitor(self, service, mock_websocket):
        """Test heartbeat monitoring sends pings"""
        service.is_running = True
        # Patch heartbeat interval to be very short for testing
        original_interval = MarketDataService.HEARTBEAT_INTERVAL
        MarketDataService.HEARTBEAT_INTERVAL = 0.05  # 50ms for testing

        try:
            await service.add_client(mock_websocket)

            # Start heartbeat task
            task = asyncio.create_task(service._heartbeat_monitor())
            service.background_tasks.append(task)

            # Wait long enough for at least one heartbeat cycle
            await asyncio.sleep(0.15)

            # Cleanup
            service.is_running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify ping was sent (in addition to welcome message)
            ping_calls = [call for call in mock_websocket.send_json.call_args_list
                         if len(call[0]) > 0 and call[0][0].get("type") == "ping"]
            assert len(ping_calls) > 0
        finally:
            MarketDataService.HEARTBEAT_INTERVAL = original_interval


class TestStatistics:
    """Test service statistics"""

    @pytest.mark.asyncio
    async def test_get_stats(self, service, mock_websocket, mock_alpaca_stream):
        """Test getting service statistics"""
        # Mock the alpaca stream to avoid real connection
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True
        service.is_running = True
        service.start_time = datetime.now(UTC)

        await service.add_client(mock_websocket)

        stats = service.get_stats()

        assert isinstance(stats, MarketDataStats)
        assert stats.total_clients == 1
        assert stats.uptime_seconds >= 0

        # Cleanup
        service.is_running = False

    @pytest.mark.asyncio
    async def test_get_subscriptions_for_client(self, service, mock_websocket, mock_alpaca_stream):
        """Test getting client subscriptions"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        client_id = await service.add_client(mock_websocket)
        await service.subscribe(client_id, "AAPL")
        await service.subscribe(client_id, "TSLA")

        subscriptions = service.get_subscriptions_for_client(client_id)

        assert "AAPL" in subscriptions
        assert "TSLA" in subscriptions
        assert len(subscriptions) == 2

    @pytest.mark.asyncio
    async def test_get_subscribers_for_symbol(self, service, mock_alpaca_stream):
        """Test getting subscribers for a symbol"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        # Two clients subscribe to AAPL
        ws1 = AsyncMock()
        ws1.send_json = AsyncMock()
        client1 = await service.add_client(ws1)
        await service.subscribe(client1, "AAPL")

        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()
        client2 = await service.add_client(ws2)
        await service.subscribe(client2, "AAPL")

        subscribers = service.get_subscribers_for_symbol("AAPL")

        assert client1 in subscribers
        assert client2 in subscribers
        assert len(subscribers) == 2


class TestServiceLifecycle:
    """Test service start/stop lifecycle"""

    @pytest.mark.asyncio
    @patch('backend.services.market_data_service.AlpacaMarketDataStream')
    async def test_start_service(self, mock_stream_class):
        """Test starting the service"""
        mock_stream = AsyncMock()
        mock_stream.connect = AsyncMock(return_value=True)
        mock_stream_class.return_value = mock_stream

        service = MarketDataService()

        await service.start("test_key", "test_secret", paper=True)

        assert service.is_running is True
        assert service.alpaca_connected is True
        assert service.start_time is not None
        assert len(service.background_tasks) > 0

        await service.stop()

    @pytest.mark.asyncio
    @patch('backend.services.market_data_service.AlpacaMarketDataStream')
    async def test_stop_service(self, mock_stream_class):
        """Test stopping the service"""
        mock_stream = AsyncMock()
        mock_stream.connect = AsyncMock(return_value=True)
        mock_stream.disconnect = AsyncMock()
        mock_stream_class.return_value = mock_stream

        service = MarketDataService()
        await service.start("test_key", "test_secret")

        await service.stop()

        assert service.is_running is False
        assert len(service.clients) == 0
        mock_stream.disconnect.assert_called_once()


class TestErrorHandling:
    """Test error handling scenarios"""

    @pytest.mark.asyncio
    async def test_subscribe_nonexistent_client(self, service):
        """Test subscribing with invalid client ID"""
        with pytest.raises(ValueError, match="Client not found"):
            await service.subscribe("invalid_client_id", "AAPL")

    @pytest.mark.asyncio
    async def test_alpaca_connection_failure(self, service, mock_websocket, mock_alpaca_stream):
        """Test handling Alpaca connection failure during subscription"""
        service.alpaca_stream = mock_alpaca_stream
        service.alpaca_connected = True

        # Make Alpaca subscription fail
        mock_alpaca_stream.subscribe_quotes = AsyncMock(side_effect=Exception("Connection failed"))

        client_id = await service.add_client(mock_websocket)

        result = await service.subscribe(client_id, "AAPL")

        # Should handle error gracefully
        assert result is False
        # Subscription should be rolled back
        assert "AAPL" not in service.clients[client_id].subscriptions


class TestSingletonPattern:
    """Test singleton service instance"""

    def test_get_service_singleton(self):
        """Test get_market_data_service returns singleton"""
        service1 = get_market_data_service()
        service2 = get_market_data_service()

        assert service1 is service2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=backend.services.market_data_service", "--cov-report=term-missing"])
