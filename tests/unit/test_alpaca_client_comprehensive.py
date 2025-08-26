"""
Comprehensive tests for the AlpacaClient module.
Covers all major functionality including trading, market data, streaming, and observability.
"""

import asyncio
from datetime import UTC, datetime, timedelta
import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import unittest

import pandas as pd
import pytest

from backend.data.alpaca_client import (
    ALPACA_AVAILABLE,
    AlpacaClient,
    MarketData,
    OrderResult,
)


# Mock classes for testing without alpaca-py dependency
class MockTradingClient:
    """Mock Alpaca trading client."""
    
    def __init__(self, *args, **kwargs):
        self.account_data = MagicMock()
        self.account_data.account_number = "TEST123456"
        self.account_data.buying_power = 50000.0
        self.account_data.equity = 75000.0
        self.account_data.cash = 25000.0
        self.account_data.portfolio_value = 75000.0
        self.account_data.daytrade_count = 2
        
    def get_account(self):
        return self.account_data
    
    def submit_order(self, order_request):
        """Mock order submission."""
        mock_order = MagicMock()
        mock_order.id = "test_order_123"
        mock_order.symbol = order_request.symbol
        mock_order.side = order_request.side
        mock_order.qty = order_request.qty
        mock_order.filled_qty = 0
        mock_order.filled_avg_price = None
        mock_order.status = MagicMock()
        mock_order.status.value = "new"
        mock_order.created_at = datetime.now(UTC)
        return mock_order
    
    def cancel_order_by_id(self, order_id):
        """Mock order cancellation."""
        return True
    
    def get_orders(self, request):
        """Mock get orders."""
        mock_order = MagicMock()
        mock_order.id = "test_order_456"
        mock_order.symbol = "AAPL"
        mock_order.side = MagicMock()
        mock_order.side.value = "buy"
        mock_order.qty = 100
        mock_order.filled_qty = 0
        mock_order.order_type = MagicMock()
        mock_order.order_type.value = "market"
        mock_order.status = MagicMock()
        mock_order.status.value = "new"
        mock_order.submitted_at = datetime.now(UTC)
        mock_order.filled_at = None
        mock_order.limit_price = None
        mock_order.filled_avg_price = None
        return [mock_order]
    
    def get_all_positions(self):
        """Mock positions."""
        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.qty = 100
        mock_position.market_value = 15000.0
        mock_position.avg_entry_price = 150.0
        mock_position.unrealized_pl = 500.0
        mock_position.unrealized_plpc = 0.033
        return [mock_position]


class MockStockHistoricalDataClient:
    """Mock stock historical data client."""
    
    def __init__(self, *args, **kwargs):
        pass
    
    def get_stock_bars(self, request):
        """Mock stock bars."""
        # Create mock bars response
        mock_bars = MagicMock()
        
        # Create sample DataFrame
        data = {
            'timestamp': [datetime.now(UTC) - timedelta(days=i) for i in range(5, 0, -1)],
            'open': [150.0 + i for i in range(5)],
            'high': [155.0 + i for i in range(5)],
            'low': [149.0 + i for i in range(5)],
            'close': [152.0 + i for i in range(5)],
            'volume': [1000000 + i * 10000 for i in range(5)]
        }
        mock_bars.df = pd.DataFrame(data)
        return mock_bars
    
    def get_stock_latest_quote(self, request):
        """Mock latest quote."""
        mock_quote = MagicMock()
        mock_quote.bid_price = 151.95
        mock_quote.ask_price = 152.05
        return {"AAPL": mock_quote}


class MockCryptoHistoricalDataClient:
    """Mock crypto historical data client."""
    
    def __init__(self, *args, **kwargs):
        pass
    
    def get_crypto_bars(self, request):
        """Mock crypto bars."""
        mock_bars = MagicMock()
        
        # Create sample DataFrame
        data = {
            'timestamp': [datetime.now(UTC) - timedelta(days=i) for i in range(5, 0, -1)],
            'open': [45000.0 + i * 100 for i in range(5)],
            'high': [46000.0 + i * 100 for i in range(5)],
            'low': [44000.0 + i * 100 for i in range(5)],
            'close': [45500.0 + i * 100 for i in range(5)],
            'volume': [100.0 + i for i in range(5)]
        }
        mock_bars.df = pd.DataFrame(data)
        return mock_bars
    
    def get_crypto_latest_bar(self, symbol_or_symbols):
        """Mock latest crypto bar."""
        mock_bar = MagicMock()
        mock_bar.close = 45750.0
        return {"BTC/USD": mock_bar}


class MockOrderRequest:
    """Mock order request classes."""
    def __init__(self, symbol, qty, side, time_in_force, **kwargs):
        self.symbol = symbol
        self.qty = qty
        self.side = side
        self.time_in_force = time_in_force
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockDataStream:
    """Mock data stream classes."""
    def __init__(self, *args, **kwargs):
        pass
    
    def subscribe_bars(self, callback, *symbols):
        pass
    
    def subscribe_quotes(self, callback, *symbols):
        pass
    
    async def _run_forever(self):
        """Mock stream runner."""
        await asyncio.sleep(0.1)  # Short sleep for testing
        return
    
    def close(self):
        pass


@pytest.fixture
def mock_alpaca_imports():
    """Mock all alpaca-py imports for testing."""
    with patch.dict('sys.modules', {
        'alpaca.common.exceptions': Mock(),
        'alpaca.data.historical': Mock(),
        'alpaca.data.live': Mock(),
        'alpaca.data.requests': Mock(),
        'alpaca.data.timeframe': Mock(),
        'alpaca.trading.client': Mock(),
        'alpaca.trading.enums': Mock(),
        'alpaca.trading.requests': Mock(),
    }):
        # Mock the main imports
        with patch('backend.data.alpaca_client.TradingClient', MockTradingClient), \
             patch('backend.data.alpaca_client.StockHistoricalDataClient', MockStockHistoricalDataClient), \
             patch('backend.data.alpaca_client.CryptoHistoricalDataClient', MockCryptoHistoricalDataClient), \
             patch('backend.data.alpaca_client.StockDataStream', MockDataStream), \
             patch('backend.data.alpaca_client.CryptoDataStream', MockDataStream), \
             patch('backend.data.alpaca_client.MarketOrderRequest', MockOrderRequest), \
             patch('backend.data.alpaca_client.LimitOrderRequest', MockOrderRequest), \
             patch('backend.data.alpaca_client.GetOrdersRequest', MockOrderRequest), \
             patch('backend.data.alpaca_client.StockBarsRequest', MockOrderRequest), \
             patch('backend.data.alpaca_client.CryptoBarsRequest', MockOrderRequest), \
             patch('backend.data.alpaca_client.StockLatestQuoteRequest', MockOrderRequest), \
             patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True):
            
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
            
            with patch('backend.data.alpaca_client.OrderSide', mock_order_side), \
                 patch('backend.data.alpaca_client.TimeInForce', mock_time_in_force), \
                 patch('backend.data.alpaca_client.TimeFrame', mock_timeframe):
                yield


@pytest.fixture
def alpaca_client(mock_alpaca_imports):
    """Create AlpacaClient instance for testing."""
    with patch('backend.data.alpaca_client.validate_symbol', return_value=True):
        client = AlpacaClient(
            api_key="test_key",
            secret_key="test_secret",
            paper=True,
            test_mode=True
        )
        return client


class TestAlpacaClientInitialization:
    """Test AlpacaClient initialization."""
    
    def test_init_without_alpaca_available(self):
        """Test initialization when alpaca-py is not available."""
        with patch('backend.data.alpaca_client.ALPACA_AVAILABLE', False):
            with pytest.raises(ImportError) as exc_info:
                AlpacaClient("test_key", "test_secret")
            
            assert "alpaca-py library is not installed" in str(exc_info.value)
    
    def test_init_paper_trading(self, mock_alpaca_imports):
        """Test initialization with paper trading."""
        with patch('backend.data.alpaca_client.validate_symbol', return_value=True):
            client = AlpacaClient(
                api_key="test_key",
                secret_key="test_secret",
                paper=True,
                test_mode=True
            )
        
        assert client.api_key == "test_key"
        assert client.secret_key == "test_secret"
        assert client.paper is True
        assert client.test_mode is True
        assert client.connected is True
    
    def test_init_live_trading(self, mock_alpaca_imports):
        """Test initialization with live trading."""
        with patch('backend.data.alpaca_client.validate_symbol', return_value=True):
            client = AlpacaClient(
                api_key="live_key",
                secret_key="live_secret",
                paper=False,
                test_mode=True
            )
        
        assert client.paper is False
    
    def test_init_connection_failure_test_mode(self, mock_alpaca_imports):
        """Test initialization with connection failure in test mode."""
        with patch('backend.data.alpaca_client.validate_symbol', return_value=True), \
             patch.object(MockTradingClient, 'get_account', side_effect=Exception("Connection failed")):
            
            client = AlpacaClient(
                api_key="test_key",
                secret_key="test_secret",
                test_mode=True
            )
            
            # In test mode, should continue despite error
            assert client.connected is False
    
    def test_init_connection_failure_non_test_mode(self, mock_alpaca_imports):
        """Test initialization with connection failure in non-test mode."""
        with patch('backend.data.alpaca_client.validate_symbol', return_value=True), \
             patch.object(MockTradingClient, 'get_account', side_effect=Exception("Connection failed")):
            
            with pytest.raises(Exception):
                AlpacaClient(
                    api_key="test_key",
                    secret_key="test_secret",
                    test_mode=False
                )


class TestAlpacaClientHistoricalData:
    """Test historical data functionality."""
    
    def test_get_historical_data_stock_success(self, alpaca_client):
        """Test successful historical data retrieval for stocks."""
        result = alpaca_client.get_historical_data(
            symbol="AAPL",
            timeframe="1Day",
            start="2024-01-01",
            end="2024-01-05"
        )
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        assert "timestamp" in result.columns
        assert "open" in result.columns
        assert "close" in result.columns
    
    def test_get_historical_data_crypto_success(self, alpaca_client):
        """Test successful historical data retrieval for crypto."""
        result = alpaca_client.get_historical_data(
            symbol="BTC/USD",
            timeframe="1Hour",
            start="2024-01-01",
            end="2024-01-02"
        )
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
    
    def test_get_historical_data_invalid_symbol(self, alpaca_client):
        """Test historical data with invalid symbol."""
        with patch('backend.data.alpaca_client.validate_symbol', return_value=False):
            with pytest.raises(ValueError) as exc_info:
                alpaca_client.get_historical_data("INVALID")
            
            assert "Invalid symbol format" in str(exc_info.value)
    
    def test_get_historical_data_invalid_timeframe(self, alpaca_client):
        """Test historical data with invalid timeframe."""
        with pytest.raises(ValueError) as exc_info:
            alpaca_client.get_historical_data("AAPL", timeframe="invalid")
        
        assert "Unsupported timeframe" in str(exc_info.value)
    
    def test_get_historical_data_default_dates(self, alpaca_client):
        """Test historical data with default date range."""
        result = alpaca_client.get_historical_data("AAPL")
        assert isinstance(result, pd.DataFrame)
    
    def test_get_historical_data_empty_result(self, alpaca_client):
        """Test historical data with empty result."""
        with patch.object(MockStockHistoricalDataClient, 'get_stock_bars') as mock_bars:
            mock_response = Mock()
            mock_response.df = pd.DataFrame()  # Empty DataFrame
            mock_bars.return_value = mock_response
            
            result = alpaca_client.get_historical_data("AAPL")
            assert result.empty
    
    def test_get_historical_data_api_error(self, alpaca_client):
        """Test historical data with API error."""
        with patch.object(MockStockHistoricalDataClient, 'get_stock_bars', side_effect=Exception("API Error")):
            with pytest.raises(Exception):
                alpaca_client.get_historical_data("AAPL")


class TestAlpacaClientTrading:
    """Test trading functionality."""
    
    def test_submit_market_order_buy(self, alpaca_client):
        """Test successful market buy order submission."""
        result = alpaca_client.submit_order(
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="market"
        )
        
        assert isinstance(result, OrderResult)
        assert result.order_id == "test_order_123"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.quantity == 100
    
    def test_submit_market_order_sell(self, alpaca_client):
        """Test successful market sell order submission."""
        result = alpaca_client.submit_order(
            symbol="AAPL",
            qty=50,
            side="sell",
            order_type="market"
        )
        
        assert isinstance(result, OrderResult)
        assert result.side == "sell"
        assert result.quantity == 50
    
    def test_submit_limit_order_success(self, alpaca_client):
        """Test successful limit order submission."""
        result = alpaca_client.submit_order(
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="limit",
            limit_price=150.0
        )
        
        assert isinstance(result, OrderResult)
        assert result.order_id == "test_order_123"
    
    def test_submit_limit_order_no_price(self, alpaca_client):
        """Test limit order submission without price."""
        with pytest.raises(ValueError) as exc_info:
            alpaca_client.submit_order(
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="limit"
            )
        
        assert "Limit price required" in str(exc_info.value)
    
    def test_submit_order_invalid_symbol(self, alpaca_client):
        """Test order submission with invalid symbol."""
        with patch('backend.data.alpaca_client.validate_symbol', return_value=False):
            with pytest.raises(ValueError) as exc_info:
                alpaca_client.submit_order("INVALID", 100, "buy")
            
            assert "Invalid symbol format" in str(exc_info.value)
    
    def test_submit_order_invalid_type(self, alpaca_client):
        """Test order submission with invalid order type."""
        with pytest.raises(ValueError) as exc_info:
            alpaca_client.submit_order("AAPL", 100, "buy", order_type="invalid")
        
        assert "Unsupported order type" in str(exc_info.value)
    
    def test_submit_order_api_error(self, alpaca_client):
        """Test order submission with API error."""
        with patch.object(MockTradingClient, 'submit_order', side_effect=Exception("API Error")):
            with pytest.raises(Exception):
                alpaca_client.submit_order("AAPL", 100, "buy")
    
    def test_cancel_order_success(self, alpaca_client):
        """Test successful order cancellation."""
        result = alpaca_client.cancel_order("test_order_123")
        assert result is True
    
    def test_cancel_order_failure(self, alpaca_client):
        """Test order cancellation failure."""
        with patch.object(MockTradingClient, 'cancel_order_by_id', side_effect=Exception("Not found")):
            result = alpaca_client.cancel_order("invalid_order")
            assert result is False


class TestAlpacaClientAccountManagement:
    """Test account management functionality."""
    
    def test_get_account_status_success(self, alpaca_client):
        """Test successful account status retrieval."""
        result = alpaca_client.get_account_status()
        
        assert isinstance(result, dict)
        assert "account_number" in result
        assert "equity" in result
        assert "cash" in result
        assert "buying_power" in result
        assert "positions" in result
        assert result["account_number"] == "TEST123456"
        assert result["equity"] == 75000.0
        assert len(result["positions"]) == 1
    
    def test_get_account_status_api_error(self, alpaca_client):
        """Test account status with API error."""
        with patch.object(MockTradingClient, 'get_account', side_effect=Exception("API Error")):
            with pytest.raises(Exception):
                alpaca_client.get_account_status()
    
    def test_get_recent_orders_success(self, alpaca_client):
        """Test successful recent orders retrieval."""
        result = alpaca_client.get_recent_orders(limit=10)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "test_order_456"
        assert result[0]["symbol"] == "AAPL"
    
    def test_get_recent_orders_api_error(self, alpaca_client):
        """Test recent orders with API error."""
        with patch.object(MockTradingClient, 'get_orders', side_effect=Exception("API Error")):
            with pytest.raises(Exception):
                alpaca_client.get_recent_orders()


class TestAlpacaClientPricing:
    """Test pricing functionality."""
    
    def test_get_current_price_stock_success(self, alpaca_client):
        """Test successful current price retrieval for stocks."""
        price = alpaca_client.get_current_price("AAPL")
        assert price == 152.0  # Average of bid/ask
    
    def test_get_current_price_crypto_success(self, alpaca_client):
        """Test successful current price retrieval for crypto."""
        price = alpaca_client.get_current_price("BTC/USD")
        assert price == 45750.0
    
    def test_get_current_price_not_found(self, alpaca_client):
        """Test current price when symbol not found."""
        with patch.object(MockStockHistoricalDataClient, 'get_stock_latest_quote', return_value={}):
            price = alpaca_client.get_current_price("NOTFOUND")
            assert price is None
    
    def test_get_current_price_api_error(self, alpaca_client):
        """Test current price with API error."""
        with patch.object(MockStockHistoricalDataClient, 'get_stock_latest_quote', 
                         side_effect=Exception("API Error")):
            price = alpaca_client.get_current_price("AAPL")
            assert price is None


class TestAlpacaClientStreaming:
    """Test real-time streaming functionality."""
    
    @pytest.mark.asyncio
    async def test_connect_data_stream_stocks(self, alpaca_client):
        """Test data stream connection for stocks."""
        callback = Mock()
        
        # Use a timeout to prevent hanging
        try:
            await asyncio.wait_for(
                alpaca_client.connect_data_stream(
                    symbols=["AAPL", "GOOGL"],
                    on_bar=callback
                ),
                timeout=1.0
            )
        except asyncio.TimeoutError:
            pass  # Expected for this test
        
        assert alpaca_client.connected is True
    
    @pytest.mark.asyncio
    async def test_connect_data_stream_crypto(self, alpaca_client):
        """Test data stream connection for crypto."""
        callback = Mock()
        
        try:
            await asyncio.wait_for(
                alpaca_client.connect_data_stream(
                    symbols=["BTC/USD", "ETH/USD"],
                    on_bar=callback
                ),
                timeout=1.0
            )
        except asyncio.TimeoutError:
            pass  # Expected for this test
    
    @pytest.mark.asyncio
    async def test_connect_data_stream_mixed(self, alpaca_client):
        """Test data stream connection for mixed symbols."""
        bar_callback = Mock()
        quote_callback = Mock()
        
        try:
            await asyncio.wait_for(
                alpaca_client.connect_data_stream(
                    symbols=["AAPL", "BTC/USD"],
                    on_bar=bar_callback,
                    on_quote=quote_callback
                ),
                timeout=1.0
            )
        except asyncio.TimeoutError:
            pass  # Expected for this test
    
    def test_add_data_callback(self, alpaca_client):
        """Test adding data callback."""
        callback = Mock()
        alpaca_client.add_data_callback(callback)
        assert callback in alpaca_client.data_callbacks
    
    def test_disconnect(self, alpaca_client):
        """Test disconnection from streams."""
        alpaca_client.connected = True
        alpaca_client.disconnect()
        assert alpaca_client.connected is False


class TestAlpacaClientUtilities:
    """Test utility functionality."""
    
    def test_rate_limiting(self, alpaca_client):
        """Test rate limiting mechanism."""
        start_time = time.time()
        
        # Make multiple rapid requests
        alpaca_client._rate_limit()
        alpaca_client._rate_limit()
        alpaca_client._rate_limit()
        
        elapsed = time.time() - start_time
        # Should have some delay due to rate limiting
        assert elapsed > 0.4  # At least 2 * 0.2s intervals
    
    def test_destructor_cleanup(self, alpaca_client):
        """Test cleanup on destruction."""
        alpaca_client.connected = True
        alpaca_client.__del__()
        assert alpaca_client.connected is False


class TestAlpacaDataClasses:
    """Test data classes."""
    
    def test_market_data_creation(self):
        """Test MarketData dataclass creation."""
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
        assert data.vwap == 151.5
    
    def test_order_result_creation(self):
        """Test OrderResult dataclass creation."""
        result = OrderResult(
            order_id="test123",
            symbol="AAPL",
            side="buy",
            quantity=100.0,
            filled_quantity=0.0,
            price=None,
            status="new",
            timestamp=datetime.now(UTC)
        )
        
        assert result.order_id == "test123"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.quantity == 100.0


class TestAlpacaClientObservability:
    """Test observability features."""
    
    def test_observability_imports(self):
        """Test that observability imports are available."""
        from backend.data.alpaca_client import record_alpaca_request, record_latency, trace_span
        assert record_alpaca_request is not None
        assert record_latency is not None
        assert trace_span is not None
    
    @patch('backend.data.alpaca_client.record_alpaca_request')
    @patch('backend.data.alpaca_client.trace_span')
    def test_submit_order_observability(self, mock_trace, mock_record, alpaca_client):
        """Test observability integration in submit_order."""
        mock_span = Mock()
        mock_trace.return_value.__enter__ = Mock(return_value=mock_span)
        mock_trace.return_value.__exit__ = Mock(return_value=None)
        
        result = alpaca_client.submit_order("AAPL", 100, "buy")
        
        # Verify tracing was called
        mock_trace.assert_called_once()
        
        # Verify metrics were recorded
        mock_record.assert_called()
        
        assert isinstance(result, OrderResult)
    
    @patch('backend.data.alpaca_client.record_alpaca_request')
    @patch('backend.data.alpaca_client.trace_span')
    def test_cancel_order_observability(self, mock_trace, mock_record, alpaca_client):
        """Test observability integration in cancel_order."""
        mock_span = Mock()
        mock_trace.return_value.__enter__ = Mock(return_value=mock_span)
        mock_trace.return_value.__exit__ = Mock(return_value=None)
        
        result = alpaca_client.cancel_order("test123")
        
        # Verify tracing was called
        mock_trace.assert_called_once()
        
        # Verify metrics were recorded
        mock_record.assert_called()
        
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__])
