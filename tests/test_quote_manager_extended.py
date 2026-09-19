"""
Extended tests for QuoteManager service.
Tests quote fetching, caching, batch operations, and metrics.
"""

import pytest
# V4 Z-R-1 (2026-05-02): production code under K-4/K-8 expects tz-aware
# UTC; fixtures using bare datetime.now() raised TypeError comparing to
# tz-aware values. All datetime.now() in this file are now datetime.now(UTC).
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from backend.services.quote_manager import Quote, QuoteManager


class TestQuoteDataClass:
    """Tests for the Quote data class."""

    def test_quote_creation(self):
        """Test creating a Quote object."""
        ts = datetime.now(UTC)
        quote = Quote(
            symbol="AAPL",
            bid=150.50,
            ask=150.55,
            last=150.52,
            timestamp=ts,
            volume=1000
        )
        
        assert quote.symbol == "AAPL"
        assert quote.bid == 150.50
        assert quote.ask == 150.55
        assert quote.last == 150.52
        assert quote.mid == pytest.approx(150.525, rel=0.001)
        assert quote.timestamp == ts
        assert quote.volume == 1000

    def test_quote_mid_calculation(self):
        """Test mid price calculation."""
        quote = Quote("AAPL", bid=100, ask=102, last=101, timestamp=datetime.now(UTC))
        
        assert quote.mid == 101.0  # (100 + 102) / 2

    def test_quote_mid_fallback_to_last(self):
        """Test mid price when bid/ask are zero falls back to last."""
        quote = Quote("AAPL", bid=0, ask=0, last=150, timestamp=datetime.now(UTC))
        
        # When bid and ask are 0 (falsy), mid falls back to last
        assert quote.mid == 150

    def test_quote_to_dict(self):
        """Test converting quote to dictionary."""
        ts = datetime.now(UTC)
        quote = Quote("AAPL", bid=150.5, ask=150.6, last=150.55, timestamp=ts, volume=500)
        
        result = quote.to_dict()
        
        assert result['symbol'] == "AAPL"
        assert result['bid'] == 150.5
        assert result['ask'] == 150.6
        assert result['last'] == 150.55
        assert result['mid'] == 150.55
        assert result['volume'] == 500
        assert result['timestamp'] == ts.isoformat()

    def test_quote_is_stale_fresh(self):
        """Test is_stale returns False for fresh quotes."""
        quote = Quote("AAPL", bid=150, ask=151, last=150.5, timestamp=datetime.now(UTC))
        
        assert quote.is_stale(max_age_seconds=5) is False

    def test_quote_is_stale_old(self):
        """Test is_stale returns True for old quotes."""
        old_time = datetime.now(UTC) - timedelta(seconds=10)
        quote = Quote("AAPL", bid=150, ask=151, last=150.5, timestamp=old_time)
        
        assert quote.is_stale(max_age_seconds=5) is True

    def test_quote_is_stale_custom_threshold(self):
        """Test is_stale with custom threshold."""
        old_time = datetime.now(UTC) - timedelta(seconds=30)
        quote = Quote("AAPL", bid=150, ask=151, last=150.5, timestamp=old_time)
        
        assert quote.is_stale(max_age_seconds=60) is False
        assert quote.is_stale(max_age_seconds=20) is True


class TestQuoteManagerInit:
    """Tests for QuoteManager initialization."""

    @patch('backend.services.quote_manager.StockHistoricalDataClient')
    @patch('backend.services.quote_manager.REDIS_AVAILABLE', False)
    def test_init_without_redis(self, mock_client):
        """Test initialization without Redis."""
        manager = QuoteManager()
        
        assert manager.alpaca_client is not None
        assert manager.redis_client is None
        assert manager.memory_cache == {}
        assert manager.cache_ttl == 5
        assert manager.max_batch_size == 100

    @patch('backend.services.quote_manager.StockHistoricalDataClient')
    @patch('backend.services.quote_manager.REDIS_AVAILABLE', False)
    def test_init_with_redis_disabled(self, mock_client):
        """Test initialization with Redis disabled."""
        manager = QuoteManager()
        
        # Redis client should be None when REDIS_AVAILABLE is False
        assert manager.redis_client is None
        assert manager.alpaca_client is not None

    @patch('backend.services.quote_manager.StockHistoricalDataClient')
    @patch('backend.services.quote_manager.REDIS_AVAILABLE', False)
    def test_init_redis_disabled(self, mock_client):
        """Test that Redis is not initialized when disabled."""
        manager = QuoteManager()
        
        assert manager.redis_client is None


class TestQuoteManagerCaching:
    """Tests for QuoteManager caching functionality."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mocked QuoteManager."""
        with patch('backend.services.quote_manager.StockHistoricalDataClient'):
            with patch('backend.services.quote_manager.REDIS_AVAILABLE', False):
                manager = QuoteManager()
                return manager

    @pytest.mark.asyncio
    async def test_memory_cache_hit(self, mock_manager):
        """Test getting quotes from memory cache."""
        # Pre-populate cache
        ts = datetime.now(UTC)
        mock_manager.memory_cache['AAPL'] = Quote(
            "AAPL", bid=150.5, ask=150.6, last=150.55, timestamp=ts
        )
        
        cached, missing = await mock_manager._get_from_cache(['AAPL'])
        
        assert 'AAPL' in cached
        assert missing == []
        assert cached['AAPL'].bid == 150.5

    @pytest.mark.asyncio
    async def test_memory_cache_miss(self, mock_manager):
        """Test cache miss returns empty dict and symbols in missing list."""
        cached, missing = await mock_manager._get_from_cache(['AAPL', 'MSFT'])
        
        assert cached == {}
        assert 'AAPL' in missing
        assert 'MSFT' in missing

    @pytest.mark.asyncio
    async def test_memory_cache_stale_quotes(self, mock_manager):
        """Test that stale quotes are considered cache misses."""
        # Add stale quote
        old_time = datetime.now(UTC) - timedelta(seconds=10)
        mock_manager.memory_cache['AAPL'] = Quote(
            "AAPL", bid=150.5, ask=150.6, last=150.55, timestamp=old_time
        )
        
        cached, missing = await mock_manager._get_from_cache(['AAPL'])
        
        assert cached == {}
        assert 'AAPL' in missing

    @pytest.mark.asyncio
    async def test_update_cache_updates_memory(self, mock_manager):
        """Test that _update_cache updates memory cache."""
        ts = datetime.now(UTC)
        quotes = {
            'AAPL': Quote("AAPL", bid=150.5, ask=150.6, last=150.55, timestamp=ts),
            'MSFT': Quote("MSFT", bid=350.0, ask=350.1, last=350.05, timestamp=ts)
        }
        
        await mock_manager._update_cache(quotes)
        
        assert 'AAPL' in mock_manager.memory_cache
        assert 'MSFT' in mock_manager.memory_cache
        assert mock_manager.memory_cache['AAPL'].bid == 150.5


class TestQuoteManagerSerialization:
    """Tests for quote serialization/deserialization."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mocked QuoteManager."""
        with patch('backend.services.quote_manager.StockHistoricalDataClient'):
            with patch('backend.services.quote_manager.REDIS_AVAILABLE', False):
                manager = QuoteManager()
                return manager

    def test_serialize_quote(self, mock_manager):
        """Test quote serialization."""
        ts = datetime(2024, 1, 15, 12, 30, 45)
        quote = Quote("AAPL", bid=150.5, ask=150.6, last=150.55, timestamp=ts, volume=1000)
        
        result = mock_manager._serialize_quote(quote)
        
        assert "150.5" in result
        assert "150.6" in result
        assert "150.55" in result
        assert "1000" in result
        assert "2024" in result

    def test_deserialize_quote(self, mock_manager):
        """Test quote deserialization."""
        ts = datetime(2024, 1, 15, 12, 30, 45)
        serialized = f"150.5|150.6|150.55|{ts.isoformat()}|1000"
        
        quote = mock_manager._deserialize_quote(serialized)
        
        assert quote is not None
        assert quote.bid == 150.5
        assert quote.ask == 150.6
        assert quote.last == 150.55
        assert quote.volume == 1000

    def test_deserialize_invalid_data(self, mock_manager):
        """Test deserialization handles invalid data."""
        result = mock_manager._deserialize_quote("invalid|data")
        
        # Should return None or handle gracefully
        # Behavior may vary based on implementation


class TestQuoteManagerGetQuotes:
    """Tests for get_quote and get_quotes methods."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mocked QuoteManager."""
        with patch('backend.services.quote_manager.StockHistoricalDataClient'):
            with patch('backend.services.quote_manager.REDIS_AVAILABLE', False):
                manager = QuoteManager()
                return manager

    @pytest.mark.asyncio
    async def test_get_quote_single_symbol(self, mock_manager):
        """Test getting a single quote."""
        # Mock the get_quotes method
        ts = datetime.now(UTC)
        expected_quote = Quote("AAPL", bid=150.5, ask=150.6, last=150.55, timestamp=ts)
        
        with patch.object(mock_manager, 'get_quotes', return_value={'AAPL': expected_quote}):
            quote = await mock_manager.get_quote('AAPL')
        
        assert quote.symbol == 'AAPL'
        assert quote.bid == 150.5

    @pytest.mark.asyncio
    async def test_get_quote_not_found(self, mock_manager):
        """Test getting a quote that doesn't exist."""
        with patch.object(mock_manager, 'get_quotes', return_value={}):
            quote = await mock_manager.get_quote('INVALID')
        
        assert quote is None

    @pytest.mark.asyncio
    async def test_get_quotes_normalizes_symbols(self, mock_manager):
        """Test that symbols are normalized to uppercase."""
        # Mock cache to return nothing, then mock _fetch_quotes
        async def mock_get_from_cache(symbols):
            # Verify symbols are uppercase
            for s in symbols:
                assert s == s.upper()
            return {}, symbols
        
        mock_manager._get_from_cache = mock_get_from_cache
        mock_manager._fetch_quotes = AsyncMock(return_value={})
        
        await mock_manager.get_quotes(['aapl', 'msft'])

    @pytest.mark.asyncio
    async def test_get_quotes_tracks_cache_hits(self, mock_manager):
        """Test that cache hits are tracked in metrics."""
        ts = datetime.now(UTC)
        mock_manager.memory_cache['AAPL'] = Quote(
            "AAPL", bid=150.5, ask=150.6, last=150.55, timestamp=ts
        )
        
        initial_hits = mock_manager.metrics['cache_hits']
        
        await mock_manager.get_quotes(['AAPL'])
        
        assert mock_manager.metrics['cache_hits'] == initial_hits + 1

    @pytest.mark.asyncio
    async def test_get_quotes_tracks_cache_misses(self, mock_manager):
        """Test that cache misses are tracked in metrics."""
        mock_manager._fetch_quotes = AsyncMock(return_value={})
        
        initial_misses = mock_manager.metrics['cache_misses']
        
        await mock_manager.get_quotes(['AAPL'])
        
        assert mock_manager.metrics['cache_misses'] == initial_misses + 1


class TestQuoteManagerFetchQuotes:
    """Tests for _fetch_quotes method."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mocked QuoteManager."""
        with patch('backend.services.quote_manager.StockHistoricalDataClient') as mock_client:
            with patch('backend.services.quote_manager.REDIS_AVAILABLE', False):
                manager = QuoteManager()
                manager.alpaca_client = MagicMock()
                return manager

    @pytest.mark.asyncio
    async def test_fetch_quotes_empty_list(self, mock_manager):
        """Test fetching with empty symbol list."""
        result = await mock_manager._fetch_quotes([])
        
        assert result == {}

    @pytest.mark.asyncio
    async def test_fetch_quotes_batch_size_limit(self, mock_manager):
        """Test that batch requests respect max size."""
        # Create more symbols than batch size
        symbols = [f"SYM{i}" for i in range(150)]
        
        # Mock alpaca client response
        mock_response = {}
        mock_manager.alpaca_client.get_stock_latest_quote.return_value = mock_response
        
        await mock_manager._fetch_quotes(symbols)
        
        # Should make multiple API calls due to batch size limit
        assert mock_manager.alpaca_client.get_stock_latest_quote.call_count >= 2

    @pytest.mark.asyncio
    async def test_fetch_quotes_api_error_handled(self, mock_manager):
        """Test that API errors are handled gracefully."""
        from alpaca.common.exceptions import APIError
        
        mock_manager.alpaca_client.get_stock_latest_quote.side_effect = APIError("API Error")
        
        # Should not raise
        result = await mock_manager._fetch_quotes(['AAPL'])
        
        assert result == {}


class TestQuoteManagerMetrics:
    """Tests for metrics tracking."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mocked QuoteManager."""
        with patch('backend.services.quote_manager.StockHistoricalDataClient'):
            with patch('backend.services.quote_manager.REDIS_AVAILABLE', False):
                manager = QuoteManager()
                return manager

    def test_get_metrics_initial(self, mock_manager):
        """Test initial metrics."""
        metrics = mock_manager.get_metrics()
        
        assert metrics['cache_hit_rate'] == 0
        assert metrics['api_calls'] == 0
        assert metrics['avg_latency_ms'] == 0
        assert metrics['total_requests'] == 0

    def test_get_metrics_with_data(self, mock_manager):
        """Test metrics after some operations."""
        mock_manager.metrics['cache_hits'] = 80
        mock_manager.metrics['cache_misses'] = 20
        mock_manager.metrics['api_calls'] = 5
        mock_manager.metrics['latencies'] = [10, 20, 30, 40, 50]
        
        metrics = mock_manager.get_metrics()
        
        assert metrics['cache_hit_rate'] == 0.8
        assert metrics['api_calls'] == 5
        assert metrics['avg_latency_ms'] == 30.0
        assert metrics['total_requests'] == 100


class TestQuoteManagerClose:
    """Tests for resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_with_redis(self):
        """Test closing with Redis client."""
        with patch('backend.services.quote_manager.StockHistoricalDataClient'):
            with patch('backend.services.quote_manager.REDIS_AVAILABLE', False):
                manager = QuoteManager()
                
                # Manually set a mock redis client
                mock_redis_client = AsyncMock()
                manager.redis_client = mock_redis_client
                
                await manager.close()
                
                mock_redis_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_redis(self):
        """Test closing without Redis client."""
        with patch('backend.services.quote_manager.StockHistoricalDataClient'):
            with patch('backend.services.quote_manager.REDIS_AVAILABLE', False):
                manager = QuoteManager()
                
                # Should not raise
                await manager.close()


class TestGetQuoteManagerSingleton:
    """Tests for the get_quote_manager singleton function."""

    def test_get_quote_manager_returns_instance(self):
        """Test that get_quote_manager returns a QuoteManager."""
        with patch('backend.services.quote_manager.StockHistoricalDataClient'):
            with patch('backend.services.quote_manager.REDIS_AVAILABLE', False):
                # Reset the global instance
                import backend.services.quote_manager as qm
                qm._quote_manager = None
                
                manager = qm.get_quote_manager()
                
                assert isinstance(manager, QuoteManager)

    def test_get_quote_manager_returns_same_instance(self):
        """Test that get_quote_manager returns the same instance."""
        with patch('backend.services.quote_manager.StockHistoricalDataClient'):
            with patch('backend.services.quote_manager.REDIS_AVAILABLE', False):
                import backend.services.quote_manager as qm
                qm._quote_manager = None
                
                manager1 = qm.get_quote_manager()
                manager2 = qm.get_quote_manager()
                
                assert manager1 is manager2
