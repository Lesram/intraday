"""
Phase 8: Comprehensive tests for data modules.
Coverage targets:
- alpaca_client.py: 80%+
- market_data.py: 80%+
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


# ============================================================================
# MARKET DATA PROCESSOR TESTS
# ============================================================================

class TestMarketDataPoint:
    """Test MarketDataPoint dataclass."""
    
    def test_market_data_point_creation(self):
        """Test creating MarketDataPoint."""
        from backend.data.market_data import MarketDataPoint
        
        point = MarketDataPoint(
            timestamp="2024-01-15T10:00:00Z",
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=10000
        )
        
        assert point.timestamp == "2024-01-15T10:00:00Z"
        assert point.open == 100.0
        assert point.high == 105.0
        assert point.low == 99.0
        assert point.close == 103.0
        assert point.volume == 10000


class TestMarketDataProcessorInit:
    """Test MarketDataProcessor initialization."""
    
    def test_init_defaults(self):
        """Test MarketDataProcessor with default config."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        assert processor.config == {}
        assert processor.processed_count == 0
        assert processor.error_count == 0
    
    def test_init_with_config(self):
        """Test MarketDataProcessor with custom config."""
        from backend.data.market_data import MarketDataProcessor
        
        config = {"max_price": 1000, "strict_mode": True}
        processor = MarketDataProcessor(config=config)
        
        assert processor.config == config


class TestProcessTick:
    """Test process_tick method."""
    
    def test_process_tick_valid(self):
        """Test processing valid tick."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_tick({"price": 100.0, "symbol": "AAPL"})
        
        assert result["status"] == "processed"
    
    def test_process_tick_calls_process_raw(self):
        """Test that process_tick calls process_raw_data."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_tick({"price": 50.0, "symbol": "MSFT"})
        
        assert result["status"] == "processed"


class TestProcessRawData:
    """Test process_raw_data method."""
    
    def test_process_null_data(self):
        """Test processing null data."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data(None)
        
        assert result["status"] == "rejected"
        assert result["error"] == "null_data"
    
    def test_process_dict_valid(self):
        """Test processing valid dict data."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 103.0,
            "volume": 10000
        })
        
        assert result["status"] == "processed"
        assert result["format"] == "dict"
        assert result["fields_processed"] > 0
    
    def test_process_dict_with_symbol(self):
        """Test dict preserves symbol."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"price": 100.0, "symbol": "AAPL"})
        
        assert result["symbol"] == "AAPL"
        assert result["price"] == 100.0
    
    def test_process_invalid_price_string(self):
        """Test rejecting invalid price string."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"price": "not_a_number"})
        
        assert result["status"] == "rejected"
        assert "price" in result["error"]
    
    def test_process_nan_price(self):
        """Test rejecting NaN price."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"price": float('nan')})
        
        assert result["status"] == "rejected"
    
    def test_process_infinite_price(self):
        """Test rejecting infinite price."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"price": float('inf')})
        
        assert result["status"] == "rejected"
    
    def test_process_negative_price(self):
        """Test rejecting negative price."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"price": -10.0})
        
        assert result["status"] == "rejected"
    
    def test_process_extremely_high_price(self):
        """Test rejecting extremely high price."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"price": 2000000.0})
        
        assert result["status"] == "rejected"
        assert result["error"] == "price_too_high"
    
    def test_process_invalid_symbol(self):
        """Test rejecting invalid symbol."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"symbol": ""})
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_symbol"
    
    def test_process_symbol_too_long(self):
        """Test rejecting symbol too long."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"symbol": "A" * 15})
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_symbol"
    
    def test_process_invalid_volume_string(self):
        """Test rejecting invalid volume string."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"volume": "invalid"})
        
        assert result["status"] == "rejected"
        assert "volume" in result["error"]
    
    def test_process_negative_volume(self):
        """Test rejecting negative volume."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data({"volume": -100})
        
        assert result["status"] == "rejected"


class TestProcessStringData:
    """Test _process_string_data method."""
    
    def test_process_empty_string(self):
        """Test processing empty string."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data("")
        
        assert result["status"] == "error"
        assert result["error"] == "empty_string"
    
    def test_process_json_string(self):
        """Test processing JSON string."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data('{"price": 100.0}')
        
        assert result["status"] == "processed"
    
    def test_process_csv_like_string(self):
        """Test processing CSV-like string."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data("header\nrow1\nrow2")
        
        assert result["status"] == "processed"
        assert result["format"] == "csv_like"
        assert result["rows"] == 3


class TestProcessListData:
    """Test _process_list_data method."""
    
    def test_process_empty_list(self):
        """Test processing empty list."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data([])
        
        assert result["status"] == "error"
        assert result["error"] == "empty_list"
    
    def test_process_list_of_dicts(self):
        """Test processing list of dicts."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        data = [
            {"price": 100.0},
            {"price": 101.0},
            {"price": 102.0}
        ]
        
        result = processor.process_raw_data(data)
        
        assert result["status"] == "processed"
        assert result["format"] == "list"
        assert result["total_items"] == 3
    
    def test_process_list_of_numbers(self):
        """Test processing list of numbers."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data([100.0, 101.0, 102.0])
        
        assert result["status"] == "processed"
    
    def test_process_large_list_limited(self):
        """Test that large lists are limited."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        # Create list with 150 items
        data = [{"price": float(i)} for i in range(1, 151)]
        
        result = processor.process_raw_data(data)
        
        # Should limit processing to 100 items
        assert result["status"] == "processed"
        assert result["items_processed"] <= 100


class TestProcessIterableData:
    """Test _process_iterable_data method."""
    
    def test_process_tuple(self):
        """Test processing tuple."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        result = processor.process_raw_data((100.0, 101.0, 102.0))
        
        assert result["status"] == "processed"
    
    def test_process_generator(self):
        """Test processing generator."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        def gen():
            for i in range(5):
                yield i
        
        result = processor.process_raw_data(gen())
        
        assert result["status"] == "processed"


class TestValidateNumericField:
    """Test _validate_numeric_field method."""
    
    def test_validate_none(self):
        """Test validating None value."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        assert processor._validate_numeric_field(None, "price") is False
    
    def test_validate_valid_price(self):
        """Test validating valid price."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        assert processor._validate_numeric_field(100.0, "price") is True
        assert processor._validate_numeric_field("100.0", "close") is True
    
    def test_validate_nan(self):
        """Test validating NaN."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        assert processor._validate_numeric_field(float('nan'), "price") is False
    
    def test_validate_inf(self):
        """Test validating infinity."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        assert processor._validate_numeric_field(float('inf'), "price") is False
    
    def test_validate_volume(self):
        """Test validating volume."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        assert processor._validate_numeric_field(1000, "volume") is True
        assert processor._validate_numeric_field(0, "volume") is True
        assert processor._validate_numeric_field(-100, "volume") is False
    
    def test_validate_other_field(self):
        """Test validating other field type."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        assert processor._validate_numeric_field(100.0, "other_field") is True


class TestGetProcessingStats:
    """Test get_processing_stats method."""
    
    def test_initial_stats(self):
        """Test initial processing stats."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        stats = processor.get_processing_stats()
        
        assert stats["processed_count"] == 0
        assert stats["error_count"] == 0
        assert stats["success_rate"] == 0.0
    
    def test_stats_after_processing(self):
        """Test stats after processing data."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        # Process some data
        processor.process_raw_data({"price": 100.0})
        processor.process_raw_data({"price": 101.0})
        
        stats = processor.get_processing_stats()
        
        assert stats["processed_count"] == 2
        assert stats["success_rate"] > 0


class TestUnsupportedTypes:
    """Test handling unsupported types."""
    
    def test_unsupported_type_int(self):
        """Test processing unsupported type (int without dict/list context)."""
        from backend.data.market_data import MarketDataProcessor
        
        processor = MarketDataProcessor()
        
        # Int alone is not iterable, should be rejected
        result = processor.process_raw_data(42)
        
        assert result["status"] == "rejected"
        assert result["error"] == "unsupported_type"


# ============================================================================
# ALPACA CLIENT TESTS
# ============================================================================

class TestMarketDataDataclass:
    """Test MarketData dataclass."""
    
    def test_market_data_creation(self):
        """Test creating MarketData."""
        from backend.data.alpaca_client import MarketData
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.now(),
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=1000000.0,
            vwap=102.5
        )
        
        assert data.symbol == "AAPL"
        assert data.close == 103.0
        assert data.vwap == 102.5
    
    def test_market_data_optional_vwap(self):
        """Test MarketData with optional vwap."""
        from backend.data.alpaca_client import MarketData
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.now(),
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=1000000.0
        )
        
        assert data.vwap is None


class TestOrderResult:
    """Test OrderResult dataclass."""
    
    def test_order_result_creation(self):
        """Test creating OrderResult."""
        from backend.data.alpaca_client import OrderResult
        
        result = OrderResult(
            order_id="ord-123",
            symbol="AAPL",
            side="buy",
            quantity=100.0,
            filled_quantity=100.0,
            price=150.25,
            status="filled",
            timestamp=datetime.now()
        )
        
        assert result.order_id == "ord-123"
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.quantity == 100.0
        assert result.status == "filled"


class TestAlpacaClientInit:
    """Test AlpacaClient initialization."""
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    def test_init_paper_trading(self, mock_crypto, mock_stock, mock_trading):
        """Test initialization in paper trading mode."""
        from backend.data.alpaca_client import AlpacaClient
        
        # Mock account response
        mock_account = MagicMock()
        mock_account.buying_power = "100000"
        mock_account.account_number = "PA123456"
        mock_trading.return_value.get_account.return_value = mock_account
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            paper=True,
            test_mode=False
        )
        
        assert client.paper is True
        assert client.connected is True
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    def test_init_test_mode(self, mock_crypto, mock_stock, mock_trading):
        """Test initialization in test mode."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            paper=True,
            test_mode=True
        )
        
        # In test mode, should not call get_account
        mock_trading.return_value.get_account.assert_not_called()
        assert client.connected is False
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    def test_init_connection_failure(self, mock_crypto, mock_stock, mock_trading):
        """Test initialization with connection failure."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_trading.return_value.get_account.side_effect = Exception("Connection failed")
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            paper=True,
            test_mode=False
        )
        
        assert client.connected is False
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', False)
    def test_init_alpaca_not_available(self):
        """Test initialization when Alpaca not available."""
        from backend.data.alpaca_client import AlpacaClient
        
        with pytest.raises(ImportError):
            AlpacaClient(
                api_key="test_api_key",
                secret_key="test_secret"
            )


class TestAlpacaClientRateLimiting:
    """Test rate limiting functionality."""
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    def test_rate_limit_interval(self, mock_crypto, mock_stock, mock_trading):
        """Test rate limit interval is set."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        assert client.min_request_interval == 0.2


class TestGetHistoricalData:
    """Test get_historical_data method."""
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    def test_get_historical_data_stock(self, mock_crypto, mock_stock, mock_trading):
        """Test getting historical data for stock."""
        from backend.data.alpaca_client import AlpacaClient
        
        # Create mock bars response
        mock_bars = MagicMock()
        mock_bars.df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=5, freq='D'),
            'open': [100, 101, 102, 103, 104],
            'high': [105, 106, 107, 108, 109],
            'low': [98, 99, 100, 101, 102],
            'close': [103, 104, 105, 106, 107],
            'volume': [1000, 1100, 1200, 1300, 1400]
        })
        
        mock_stock.return_value.get_stock_bars.return_value = mock_bars
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        df = client.get_historical_data("AAPL", timeframe="1Day")
        
        assert len(df) == 5
        assert "close" in df.columns
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    def test_get_historical_data_crypto(self, mock_crypto, mock_stock, mock_trading):
        """Test getting historical data for crypto."""
        from backend.data.alpaca_client import AlpacaClient
        
        # Create mock bars response
        mock_bars = MagicMock()
        mock_bars.df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=5, freq='D'),
            'open': [40000, 41000, 42000, 43000, 44000],
            'high': [41000, 42000, 43000, 44000, 45000],
            'low': [39000, 40000, 41000, 42000, 43000],
            'close': [40500, 41500, 42500, 43500, 44500],
            'volume': [100, 110, 120, 130, 140]
        })
        
        mock_crypto.return_value.get_crypto_bars.return_value = mock_bars
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        df = client.get_historical_data("BTC/USD", timeframe="1Day")
        
        assert len(df) == 5
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    def test_get_historical_data_invalid_symbol(self, mock_crypto, mock_stock, mock_trading):
        """Test getting data for invalid symbol."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        with pytest.raises(ValueError, match="Invalid symbol"):
            client.get_historical_data("INVALID!!!")
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    def test_get_historical_data_invalid_timeframe(self, mock_crypto, mock_stock, mock_trading):
        """Test getting data with invalid timeframe."""
        from backend.data.alpaca_client import AlpacaClient
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            client.get_historical_data("AAPL", timeframe="2Days")
    
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    def test_get_historical_data_empty_result(self, mock_crypto, mock_stock, mock_trading):
        """Test handling empty data result."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_bars = MagicMock()
        mock_bars.df = pd.DataFrame()
        
        mock_stock.return_value.get_stock_bars.return_value = mock_bars
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        df = client.get_historical_data("AAPL", timeframe="1Day")
        
        assert df.empty


class TestSubmitOrder:
    """Test submit_order method."""
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    @patch('backend.data.alpaca_client.audit_logger')
    @patch('backend.data.alpaca_client.record_alpaca_request')
    @patch('backend.data.alpaca_client.trace_span')
    async def test_submit_market_order(self, mock_span, mock_record, mock_audit, 
                                        mock_crypto, mock_stock, mock_trading):
        """Test submitting market order."""
        from backend.data.alpaca_client import AlpacaClient
        
        # Setup mock span
        mock_span_instance = MagicMock()
        mock_span.return_value.__enter__ = MagicMock(return_value=mock_span_instance)
        mock_span.return_value.__exit__ = MagicMock(return_value=None)
        
        # Setup mock order response
        mock_order = MagicMock()
        mock_order.id = "ord-123"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = 100
        mock_order.filled_qty = 0
        mock_order.filled_avg_price = None
        mock_order.status.value = "accepted"
        mock_order.created_at = datetime.now()
        
        mock_trading.return_value.submit_order.return_value = mock_order
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        result = await client.submit_order(
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="market"
        )
        
        assert result.order_id == "ord-123"
        assert result.symbol == "AAPL"
        assert result.status == "accepted"
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    @patch('backend.data.alpaca_client.audit_logger')
    @patch('backend.data.alpaca_client.record_alpaca_request')
    @patch('backend.data.alpaca_client.trace_span')
    async def test_submit_limit_order(self, mock_span, mock_record, mock_audit,
                                       mock_crypto, mock_stock, mock_trading):
        """Test submitting limit order."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_span_instance = MagicMock()
        mock_span.return_value.__enter__ = MagicMock(return_value=mock_span_instance)
        mock_span.return_value.__exit__ = MagicMock(return_value=None)
        
        mock_order = MagicMock()
        mock_order.id = "ord-456"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "sell"
        mock_order.qty = 50
        mock_order.filled_qty = 0
        mock_order.filled_avg_price = None
        mock_order.status.value = "accepted"
        mock_order.created_at = datetime.now()
        
        mock_trading.return_value.submit_order.return_value = mock_order
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        result = await client.submit_order(
            symbol="AAPL",
            qty=50,
            side="sell",
            order_type="limit",
            limit_price=150.0
        )
        
        assert result.order_id == "ord-456"
        assert result.quantity == 50
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    @patch('backend.data.alpaca_client.trace_span')
    async def test_submit_order_invalid_symbol(self, mock_span, mock_crypto, mock_stock, mock_trading):
        """Test submitting order with invalid symbol."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_span_instance = MagicMock()
        mock_span.return_value.__enter__ = MagicMock(return_value=mock_span_instance)
        mock_span.return_value.__exit__ = MagicMock(return_value=None)
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        with pytest.raises(ValueError, match="Invalid symbol"):
            await client.submit_order(
                symbol="!!INVALID!!",
                qty=100,
                side="buy"
            )
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    @patch('backend.data.alpaca_client.trace_span')
    async def test_submit_limit_order_no_price(self, mock_span, mock_crypto, mock_stock, mock_trading):
        """Test submitting limit order without price."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_span_instance = MagicMock()
        mock_span.return_value.__enter__ = MagicMock(return_value=mock_span_instance)
        mock_span.return_value.__exit__ = MagicMock(return_value=None)
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        with pytest.raises(ValueError, match="Limit price required"):
            await client.submit_order(
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="limit"
            )


class TestCancelOrder:
    """Test cancel_order method."""
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    @patch('backend.data.alpaca_client.audit_logger')
    @patch('backend.data.alpaca_client.record_alpaca_request')
    @patch('backend.data.alpaca_client.trace_span')
    async def test_cancel_order_success(self, mock_span, mock_record, mock_audit,
                                         mock_crypto, mock_stock, mock_trading):
        """Test cancelling order successfully."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_span_instance = MagicMock()
        mock_span.return_value.__enter__ = MagicMock(return_value=mock_span_instance)
        mock_span.return_value.__exit__ = MagicMock(return_value=None)
        
        mock_trading.return_value.cancel_order_by_id.return_value = None
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        result = await client.cancel_order("ord-123")
        
        assert result is True
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    @patch('backend.data.alpaca_client.record_alpaca_request')
    @patch('backend.data.alpaca_client.trace_span')
    async def test_cancel_order_failure(self, mock_span, mock_record,
                                         mock_crypto, mock_stock, mock_trading):
        """Test cancel order failure."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_span_instance = MagicMock()
        mock_span.return_value.__enter__ = MagicMock(return_value=mock_span_instance)
        mock_span.return_value.__exit__ = MagicMock(return_value=None)
        
        mock_trading.return_value.cancel_order_by_id.side_effect = Exception("Order not found")
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        result = await client.cancel_order("ord-invalid")
        
        assert result is False


class TestGetAccountStatus:
    """Test get_account_status method."""
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    async def test_get_account_status_success(self, mock_crypto, mock_stock, mock_trading):
        """Test getting account status successfully."""
        from backend.data.alpaca_client import AlpacaClient
        
        # Mock account
        mock_account = MagicMock()
        mock_account.account_number = "PA123456"
        mock_account.equity = "100000"
        mock_account.cash = "50000"
        mock_account.buying_power = "200000"
        mock_account.portfolio_value = "100000"
        mock_account.daytrade_count = 2
        
        mock_trading.return_value.get_account.return_value = mock_account
        mock_trading.return_value.get_all_positions.return_value = []
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        result = await client.get_account_status()
        
        assert result["account_number"] == "PA123456"
        assert result["equity"] == 100000.0
        assert result["cash"] == 50000.0
        assert result["positions"] == {}
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    async def test_get_account_status_with_positions(self, mock_crypto, mock_stock, mock_trading):
        """Test getting account status with positions."""
        from backend.data.alpaca_client import AlpacaClient
        
        # Mock account
        mock_account = MagicMock()
        mock_account.account_number = "PA123456"
        mock_account.equity = "100000"
        mock_account.cash = "50000"
        mock_account.buying_power = "200000"
        mock_account.portfolio_value = "100000"
        mock_account.daytrade_count = 0
        
        # Mock position
        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.qty = "100"
        mock_position.market_value = "15000"
        mock_position.avg_entry_price = "140"
        mock_position.unrealized_pl = "1000"
        mock_position.unrealized_plpc = "0.0714"
        
        mock_trading.return_value.get_account.return_value = mock_account
        mock_trading.return_value.get_all_positions.return_value = [mock_position]
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        client.test_mode = False  # Enable position iteration
        
        result = await client.get_account_status()
        
        assert "AAPL" in result["positions"]
        assert result["positions"]["AAPL"]["quantity"] == 100.0
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    async def test_get_account_status_error(self, mock_crypto, mock_stock, mock_trading):
        """Test get_account_status with API error."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_trading.return_value.get_account.side_effect = Exception("API Error")
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        with pytest.raises(Exception, match="API Error"):
            await client.get_account_status()


class TestGetRecentOrders:
    """Test get_recent_orders method."""
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    async def test_get_recent_orders_success(self, mock_crypto, mock_stock, mock_trading):
        """Test getting recent orders successfully."""
        from backend.data.alpaca_client import AlpacaClient
        
        # Mock order
        mock_order = MagicMock()
        mock_order.id = "ord-123"
        mock_order.symbol = "AAPL"
        mock_order.side.value = "buy"
        mock_order.qty = 100
        mock_order.filled_qty = 100
        mock_order.order_type.value = "market"
        mock_order.status.value = "filled"
        mock_order.submitted_at = datetime.now()
        mock_order.filled_at = datetime.now()
        mock_order.limit_price = None
        mock_order.filled_avg_price = 150.0
        
        mock_trading.return_value.get_orders.return_value = [mock_order]
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        result = await client.get_recent_orders(limit=10)
        
        assert len(result) == 1
        assert result[0]["id"] == "ord-123"
        assert result[0]["symbol"] == "AAPL"


class TestSubmitOrderError:
    """Test submit_order error handling."""
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    @patch('backend.data.alpaca_client.record_alpaca_request')
    @patch('backend.data.alpaca_client.trace_span')
    async def test_submit_order_api_error(self, mock_span, mock_record,
                                           mock_crypto, mock_stock, mock_trading):
        """Test submit_order with API error."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_span_instance = MagicMock()
        mock_span.return_value.__enter__ = MagicMock(return_value=mock_span_instance)
        mock_span.return_value.__exit__ = MagicMock(return_value=None)
        
        mock_trading.return_value.submit_order.side_effect = Exception("Insufficient funds")
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        with pytest.raises(Exception, match="Insufficient funds"):
            await client.submit_order(
                symbol="AAPL",
                qty=100,
                side="buy"
            )
    
    @pytest.mark.asyncio
    @patch('backend.data.alpaca_client.ALPACA_AVAILABLE', True)
    @patch('backend.data.alpaca_client.TradingClient')
    @patch('backend.data.alpaca_client.StockHistoricalDataClient')
    @patch('backend.data.alpaca_client.CryptoHistoricalDataClient')
    @patch('backend.data.alpaca_client.trace_span')
    async def test_submit_order_unsupported_type(self, mock_span, mock_crypto, mock_stock, mock_trading):
        """Test submit_order with unsupported order type."""
        from backend.data.alpaca_client import AlpacaClient
        
        mock_span_instance = MagicMock()
        mock_span.return_value.__enter__ = MagicMock(return_value=mock_span_instance)
        mock_span.return_value.__exit__ = MagicMock(return_value=None)
        
        client = AlpacaClient(
            api_key="test_api_key",
            secret_key="test_secret",
            test_mode=True
        )
        
        with pytest.raises(ValueError, match="Unsupported order type"):
            await client.submit_order(
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="stop_limit"
            )
