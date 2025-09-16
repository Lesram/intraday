"""
Integration tests for AlpacaClient with real code path coverage.
Tests actual implementation with strategic mocking.
"""

import asyncio
from datetime import UTC, datetime, timedelta
import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import unittest

import pandas as pd
import pytest

# Set test environment to avoid ML issues
os.environ["DISABLE_ML"] = "1"


@pytest.fixture
def mock_alpaca_dependencies():
    """Mock alpaca-py dependencies with realistic behavior."""
    # Create mock modules
    mock_modules = {
        'alpaca.common.exceptions': Mock(),
        'alpaca.data.historical': Mock(),
        'alpaca.data.live': Mock(), 
        'alpaca.data.requests': Mock(),
        'alpaca.data.timeframe': Mock(),
        'alpaca.trading.client': Mock(),
        'alpaca.trading.enums': Mock(),
        'alpaca.trading.requests': Mock(),
    }
    
    # Create realistic mock classes
    class MockTradingClient:
        def __init__(self, *args, **kwargs):
            pass
        
        def get_account(self):
            account = Mock()
            account.account_number = "TEST123456"
            account.buying_power = 50000.0
            account.equity = 75000.0
            account.cash = 25000.0
            account.portfolio_value = 75000.0
            account.daytrade_count = 2
            return account
        
        def submit_order(self, order_request):
            order = Mock()
            order.id = "order_12345"
            order.symbol = order_request.symbol
            order.side = Mock()
            order.side.value = "buy"
            order.qty = order_request.qty
            order.filled_qty = 0
            order.filled_avg_price = None
            order.status = Mock()
            order.status.value = "new"
            order.created_at = datetime.now(UTC)
            return order
        
        def cancel_order_by_id(self, order_id):
            return True
        
        def get_orders(self, request):
            order = Mock()
            order.id = "order_67890"
            order.symbol = "AAPL"
            order.side = Mock()
            order.side.value = "buy" 
            order.qty = 100
            order.filled_qty = 0
            order.order_type = Mock()
            order.order_type.value = "market"
            order.status = Mock()
            order.status.value = "new"
            order.submitted_at = datetime.now(UTC)
            order.filled_at = None
            order.limit_price = None
            order.filled_avg_price = None
            return [order]
        
        def get_all_positions(self):
            position = Mock()
            position.symbol = "AAPL"
            position.qty = 100
            position.market_value = 15000.0
            position.avg_entry_price = 150.0
            position.unrealized_pl = 500.0
            position.unrealized_plpc = 0.033
            return [position]
    
    class MockStockHistoricalDataClient:
        def __init__(self, *args, **kwargs):
            pass
        
        def get_stock_bars(self, request):
            bars = Mock()
            data = {
                'timestamp': [datetime.now(UTC) - timedelta(days=i) for i in range(5, 0, -1)],
                'open': [150.0, 151.0, 152.0, 153.0, 154.0],
                'high': [155.0, 156.0, 157.0, 158.0, 159.0],
                'low': [149.0, 150.0, 151.0, 152.0, 153.0],
                'close': [152.0, 153.0, 154.0, 155.0, 156.0],
                'volume': [1000000, 1100000, 1200000, 1300000, 1400000]
            }
            bars.df = pd.DataFrame(data)
            return bars
        
        def get_stock_latest_quote(self, request):
            quote = Mock()
            quote.bid_price = 155.95
            quote.ask_price = 156.05
            return {"AAPL": quote}
    
    class MockCryptoHistoricalDataClient:
        def __init__(self, *args, **kwargs):
            pass
        
        def get_crypto_bars(self, request):
            bars = Mock()
            data = {
                'timestamp': [datetime.now(UTC) - timedelta(hours=i) for i in range(5, 0, -1)],
                'open': [45000.0, 45100.0, 45200.0, 45300.0, 45400.0],
                'high': [45500.0, 45600.0, 45700.0, 45800.0, 45900.0],
                'low': [44500.0, 44600.0, 44700.0, 44800.0, 44900.0],
                'close': [45200.0, 45300.0, 45400.0, 45500.0, 45600.0],
                'volume': [100.0, 110.0, 120.0, 130.0, 140.0]
            }
            bars.df = pd.DataFrame(data)
            return bars
        
        def get_crypto_latest_bar(self, symbol_or_symbols):
            bar = Mock()
            bar.close = 45750.0
            return {"BTC/USD": bar}
    
    # Mock request classes
    class MockOrderRequest:
        def __init__(self, symbol=None, qty=None, side=None, time_in_force=None, 
                     limit_price=None, **kwargs):
            self.symbol = symbol
            self.qty = qty
            self.side = side
            self.time_in_force = time_in_force
            self.limit_price = limit_price
            # Handle any additional kwargs
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    class MockDataStream:
        def __init__(self, *args, **kwargs):
            pass
        
        def subscribe_bars(self, callback, *symbols):
            pass
        
        def subscribe_quotes(self, callback, *symbols):
            pass
        
        async def _run_forever(self):
            await asyncio.sleep(0.1)
            return
        
        def close(self):
            pass
    
    # Mock enums
    mock_order_side = Mock()
    mock_order_side.BUY = "buy"
    mock_order_side.SELL = "sell"
    
    mock_time_in_force = Mock()
    mock_time_in_force.GTC = "gtc"
    mock_time_in_force.IOC = "ioc"
    
    mock_timeframe = Mock()
    mock_timeframe.Minute = "1Min"
    mock_timeframe.Hour = "1Hour"
    mock_timeframe.Day = "1Day"
    
    # Apply all patches
    patches = [
        patch.dict('sys.modules', mock_modules),
        patch('backend.data.alpaca_client.TradingClient', MockTradingClient),
        patch('backend.data.alpaca_client.StockHistoricalDataClient', MockStockHistoricalDataClient),
        patch('backend.data.alpaca_client.CryptoHistoricalDataClient', MockCryptoHistoricalDataClient),
        patch('backend.data.alpaca_client.StockDataStream', MockDataStream),
        patch('backend.data.alpaca_client.CryptoDataStream', MockDataStream),
        patch('backend.data.alpaca_client.MarketOrderRequest', MockOrderRequest),
        patch('backend.data.alpaca_client.LimitOrderRequest', MockOrderRequest),
        patch('backend.data.alpaca_client.GetOrdersRequest', MockOrderRequest),
        patch('backend.data.alpaca_client.StockBarsRequest', MockOrderRequest),
        patch('backend.data.alpaca_client.CryptoBarsRequest', MockOrderRequest),
        patch('backend.data.alpaca_client.StockLatestQuoteRequest', MockOrderRequest),
        patch('backend.data.alpaca_client.OrderSide', mock_order_side),
        patch('backend.data.alpaca_client.TimeInForce', mock_time_in_force),
        patch('backend.data.alpaca_client.TimeFrame', mock_timeframe),
        patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True),
        patch('backend.data.alpaca_client.validate_symbol', return_value=True),
        patch('backend.data.alpaca_client.record_alpaca_request'),
        patch('backend.data.alpaca_client.record_latency'),
        patch('backend.data.alpaca_client.trace_span'),
        patch('backend.data.alpaca_client.get_structured_logger'),
        patch('backend.data.alpaca_client.audit_logger')
    ]
    
    # Start all patches
    started_patches = [p.start() for p in patches]
    
    # Configure trace span mock
    mock_trace = started_patches[19]  # trace_span patch
    mock_span = Mock()
    mock_trace.return_value.__enter__ = Mock(return_value=mock_span)
    mock_trace.return_value.__exit__ = Mock(return_value=None)
    
    # Configure structured logger mock
    mock_logger = started_patches[20]  # get_structured_logger patch
    mock_structured_logger = Mock()
    mock_logger.return_value = mock_structured_logger
    
    try:
        yield
    finally:
        # Stop all patches
        for p in patches:
            p.stop()


class TestAlpacaClientIntegration:
    """Integration tests that exercise real code paths."""
    
    def test_client_initialization_success(self, mock_alpaca_dependencies):
        """Test successful client initialization."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient(
            api_key="test_key_123",
            secret_key="test_secret_456",
            paper=True,
            test_mode=True
        )
        
        assert client.api_key == "test_key_123"
        assert client.secret_key == "test_secret_456"
        assert client.paper is True
        assert client.test_mode is True
        # In test mode, connected is False for safety (graceful degradation)
        assert client.connected is False
        assert client.min_request_interval == 0.2
        assert isinstance(client.data_callbacks, list)
        assert len(client.data_callbacks) == 0
    
    def test_get_historical_data_stock(self, mock_alpaca_dependencies):
        """Test historical data retrieval for stocks."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        result = client.get_historical_data(
            symbol="AAPL",
            timeframe="1Day", 
            start="2024-01-01",
            end="2024-01-05"
        )
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        assert "timestamp" in result.columns
        assert "open" in result.columns
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns
    
    def test_get_historical_data_crypto(self, mock_alpaca_dependencies):
        """Test historical data retrieval for crypto.""" 
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        result = client.get_historical_data(
            symbol="BTC/USD",
            timeframe="1Hour",
            start="2024-01-01",
            end="2024-01-02"
        )
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        # Crypto should be detected by the "/" in symbol
    
    def test_get_historical_data_invalid_timeframe(self, mock_alpaca_dependencies):
        """Test historical data with invalid timeframe."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        with pytest.raises(ValueError) as exc_info:
            client.get_historical_data("AAPL", timeframe="invalid")
        
        assert "Unsupported timeframe" in str(exc_info.value)
    
    def test_get_historical_data_invalid_symbol(self, mock_alpaca_dependencies):
        """Test historical data with invalid symbol."""
        from backend.data.alpaca_client import AlpacaClient
        
        with patch('backend.data.alpaca_client.validate_symbol', return_value=False):
            client = AlpacaClient("test_key", "test_secret", test_mode=True)
            
            with pytest.raises(ValueError) as exc_info:
                client.get_historical_data("INVALID")
            
            assert "Invalid symbol format" in str(exc_info.value)
    
    def test_submit_market_order(self, mock_alpaca_dependencies):
        """Test market order submission."""
        from backend.data.alpaca_client import AlpacaClient, OrderResult
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        result = client.submit_order(
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="market"
        )
        
        assert isinstance(result, OrderResult)
        assert result.order_id == "order_12345"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.quantity == 100
        assert result.status == "new"
    
    def test_submit_limit_order(self, mock_alpaca_dependencies):
        """Test limit order submission."""
        from backend.data.alpaca_client import AlpacaClient, OrderResult
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        result = client.submit_order(
            symbol="AAPL",
            qty=100,
            side="buy", 
            order_type="limit",
            limit_price=150.0
        )
        
        assert isinstance(result, OrderResult)
        assert result.order_id == "order_12345"
    
    def test_submit_limit_order_no_price_error(self, mock_alpaca_dependencies):
        """Test limit order without price raises error."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        with pytest.raises(ValueError) as exc_info:
            client.submit_order(
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="limit"
            )
        
        assert "Limit price required" in str(exc_info.value)
    
    def test_submit_order_invalid_type_error(self, mock_alpaca_dependencies):
        """Test invalid order type raises error."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        with pytest.raises(ValueError) as exc_info:
            client.submit_order(
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="invalid"
            )
        
        assert "Unsupported order type" in str(exc_info.value)
    
    def test_cancel_order(self, mock_alpaca_dependencies):
        """Test order cancellation."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        result = client.cancel_order("order_12345")
        
        assert result is True
    
    def test_get_account_status(self, mock_alpaca_dependencies):
        """Test account status retrieval."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        result = client.get_account_status()
        
        assert isinstance(result, dict)
        assert "account_number" in result
        assert "equity" in result
        assert "cash" in result
        assert "buying_power" in result
        assert "positions" in result
        assert result["account_number"] == "TEST123456"
        assert result["equity"] == 75000.0
        # In test mode, positions are intentionally empty for safety
        assert len(result["positions"]) == 0
    
    def test_get_recent_orders(self, mock_alpaca_dependencies):
        """Test recent orders retrieval."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        result = client.get_recent_orders(limit=10)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "order_67890"
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["side"] == "buy"
    
    def test_get_current_price_stock(self, mock_alpaca_dependencies):
        """Test current price retrieval for stocks."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        price = client.get_current_price("AAPL")
        
        # Should be average of bid/ask: (155.95 + 156.05) / 2 = 156.0
        assert price == 156.0
    
    def test_get_current_price_crypto(self, mock_alpaca_dependencies):
        """Test current price retrieval for crypto."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        price = client.get_current_price("BTC/USD")
        
        # Should be close price from latest bar
        assert price == 45750.0
    
    def test_get_current_price_not_found(self, mock_alpaca_dependencies):
        """Test current price when symbol not found."""
        from backend.data.alpaca_client import AlpacaClient
        
        with patch('backend.data.alpaca_client.StockHistoricalDataClient') as mock_stock_client:
            mock_client_instance = Mock()
            mock_client_instance.get_stock_latest_quote.return_value = {}  # Empty response
            mock_stock_client.return_value = mock_client_instance
            
            client = AlpacaClient("test_key", "test_secret", test_mode=True)
            price = client.get_current_price("NOTFOUND")
            
            assert price is None
    
    def test_rate_limiting(self, mock_alpaca_dependencies):
        """Test rate limiting functionality."""
        from backend.data.alpaca_client import AlpacaClient
        import time
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        start_time = time.time()
        
        # Make multiple rapid calls
        client._rate_limit()
        client._rate_limit()
        client._rate_limit()
        
        elapsed = time.time() - start_time
        
        # Should have some delay due to rate limiting (0.2s per call minimum)
        assert elapsed >= 0.4
    
    def test_add_data_callback(self, mock_alpaca_dependencies):
        """Test adding data callback."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        
        def sample_callback(data):
            pass
        
        client.add_data_callback(sample_callback)
        
        assert sample_callback in client.data_callbacks
        assert len(client.data_callbacks) == 1
    
    def test_disconnect(self, mock_alpaca_dependencies):
        """Test disconnection from streams."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        client.connected = True
        
        client.disconnect()
        
        assert client.connected is False
    
    def test_destructor_cleanup(self, mock_alpaca_dependencies):
        """Test cleanup on destruction."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient("test_key", "test_secret", test_mode=True)
        client.connected = True
        
        client.__del__()
        
        assert client.connected is False


class TestAlpacaClientDataStructures:
    """Test data structure classes."""
    
    def test_market_data_creation(self):
        """Test MarketData dataclass."""
        from backend.data.alpaca_client import MarketData
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.now(UTC),
            open=150.0,
            high=155.0,
            low=149.0,
            close=152.0,
            volume=1000000,
            vwap=151.5
        )
        
        assert data.symbol == "AAPL"
        assert data.open == 150.0
        assert data.high == 155.0
        assert data.low == 149.0
        assert data.close == 152.0
        assert data.volume == 1000000
        assert data.vwap == 151.5
    
    def test_order_result_creation(self):
        """Test OrderResult dataclass."""
        from backend.data.alpaca_client import OrderResult
        
        result = OrderResult(
            order_id="test123",
            symbol="AAPL",
            side="buy",
            quantity=100.0,
            filled_quantity=50.0,
            price=150.0,
            status="partially_filled",
            timestamp=datetime.now(UTC)
        )
        
        assert result.order_id == "test123"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.quantity == 100.0
        assert result.filled_quantity == 50.0
        assert result.price == 150.0
        assert result.status == "partially_filled"


if __name__ == "__main__":
    pytest.main([__file__])
