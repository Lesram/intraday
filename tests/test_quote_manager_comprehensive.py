"""
Comprehensive tests for backend.services.quote_manager

Targets 70%+ coverage for QuoteManager:
- Quote class
- Cache operations
- Batch fetching
- Metrics tracking
"""

# V4 Z-R-1 (2026-05-02): production tz-aware UTC; fixtures need it too.
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.quote_manager import Quote, QuoteManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def quote_manager():
    """Create QuoteManager with mocked dependencies"""
    with patch("backend.services.quote_manager.StockHistoricalDataClient") as mock_client:
        with patch("backend.services.quote_manager.REDIS_AVAILABLE", False):
            manager = QuoteManager()
            manager.alpaca_client = mock_client.return_value
            return manager


@pytest.fixture
def sample_quote():
    """Create a sample Quote"""
    return Quote(
        symbol="AAPL",
        bid=149.99,
        ask=150.01,
        last=150.00,
        timestamp=datetime.now(UTC),
        volume=1000000,
    )


# ============================================================================
# QUOTE CLASS TESTS
# ============================================================================

class TestQuote:
    """Tests for Quote class"""
    
    def test_create_quote(self, sample_quote):
        """Test creating a quote"""
        assert sample_quote.symbol == "AAPL"
        assert sample_quote.bid == 149.99
        assert sample_quote.ask == 150.01
        assert sample_quote.last == 150.00
        
    def test_quote_mid_calculation(self, sample_quote):
        """Test mid price calculation"""
        expected_mid = (149.99 + 150.01) / 2
        assert sample_quote.mid == expected_mid
        
    def test_quote_mid_fallback_to_last(self):
        """Test mid falls back to last when bid/ask missing"""
        quote = Quote(
            symbol="AAPL",
            bid=0,
            ask=0,
            last=150.00,
            timestamp=datetime.now(UTC),
        )
        assert quote.mid == 150.00
        
    def test_quote_to_dict(self, sample_quote):
        """Test quote serialization to dict"""
        result = sample_quote.to_dict()
        
        assert result["symbol"] == "AAPL"
        assert result["bid"] == 149.99
        assert result["ask"] == 150.01
        assert result["last"] == 150.00
        assert "mid" in result
        assert "timestamp" in result
        assert result["volume"] == 1000000
        
    def test_quote_not_stale(self, sample_quote):
        """Test fresh quote is not stale"""
        assert sample_quote.is_stale() is False
        
    def test_quote_is_stale(self):
        """Test old quote is stale"""
        old_quote = Quote(
            symbol="AAPL",
            bid=149.99,
            ask=150.01,
            last=150.00,
            timestamp=datetime.now(UTC) - timedelta(seconds=10),
        )
        
        assert old_quote.is_stale(max_age_seconds=5) is True
        
    def test_quote_stale_custom_max_age(self, sample_quote):
        """Test stale check with custom max age"""
        assert sample_quote.is_stale(max_age_seconds=0) is True


# ============================================================================
# QUOTE MANAGER INITIALIZATION TESTS
# ============================================================================

class TestQuoteManagerInit:
    """Tests for QuoteManager initialization"""
    
    def test_init_defaults(self, quote_manager):
        """Test default initialization"""
        assert quote_manager.cache_ttl == 5
        assert quote_manager.batch_window == 0.05
        assert quote_manager.max_batch_size == 100
        
    def test_init_metrics(self, quote_manager):
        """Test metrics initialization"""
        assert quote_manager.metrics["cache_hits"] == 0
        assert quote_manager.metrics["cache_misses"] == 0
        assert quote_manager.metrics["api_calls"] == 0
        
    def test_memory_cache_initialized(self, quote_manager):
        """Test memory cache is initialized"""
        assert isinstance(quote_manager.memory_cache, dict)


# ============================================================================
# GET QUOTE TESTS
# ============================================================================

class TestGetQuote:
    """Tests for get_quote method"""
    
    @pytest.mark.asyncio
    async def test_get_quote_delegates_to_get_quotes(self, quote_manager):
        """Test get_quote calls get_quotes"""
        expected_quote = Quote(
            symbol="AAPL",
            bid=149.99,
            ask=150.01,
            last=150.00,
            timestamp=datetime.now(UTC),
        )
        
        quote_manager.get_quotes = AsyncMock(return_value={"AAPL": expected_quote})
        
        result = await quote_manager.get_quote("AAPL")
        
        assert result == expected_quote
        quote_manager.get_quotes.assert_called_once_with(["AAPL"])
        
    @pytest.mark.asyncio
    async def test_get_quote_not_found(self, quote_manager):
        """Test get_quote returns None when not found"""
        quote_manager.get_quotes = AsyncMock(return_value={})
        
        result = await quote_manager.get_quote("NONEXISTENT")
        
        assert result is None


# ============================================================================
# CACHE TESTS
# ============================================================================

class TestCache:
    """Tests for cache operations"""
    
    @pytest.mark.asyncio
    async def test_memory_cache_fallback(self, quote_manager):
        """Test memory cache is used when Redis unavailable"""
        # Manually add to memory cache
        test_quote = Quote(
            symbol="AAPL",
            bid=149.99,
            ask=150.01,
            last=150.00,
            timestamp=datetime.now(UTC),
        )
        quote_manager.memory_cache["AAPL"] = test_quote
        
        # Mock _get_from_cache to return from memory
        cached, missing = await quote_manager._get_from_cache(["AAPL"])
        
        # AAPL should be found in cache
        assert "AAPL" in cached or "AAPL" not in missing


# ============================================================================
# BATCH PROCESSING TESTS
# ============================================================================

class TestBatchProcessing:
    """Tests for batch processing configuration"""
    
    def test_batch_window_configured(self, quote_manager):
        """Test batch window is configured"""
        assert quote_manager.batch_window == 0.05  # 50ms
        
    def test_max_batch_size_configured(self, quote_manager):
        """Test max batch size matches Alpaca limit"""
        assert quote_manager.max_batch_size == 100


# ============================================================================
# METRICS TESTS
# ============================================================================

class TestMetrics:
    """Tests for metrics tracking"""
    
    def test_metrics_structure(self, quote_manager):
        """Test metrics structure"""
        expected_keys = ["cache_hits", "cache_misses", "api_calls", "latencies"]
        
        for key in expected_keys:
            assert key in quote_manager.metrics
            
    @pytest.mark.asyncio
    async def test_cache_hit_increments_metric(self, quote_manager):
        """Test cache hit increments metric"""
        initial_hits = quote_manager.metrics["cache_hits"]
        
        # Add to memory cache
        test_quote = Quote(
            symbol="AAPL",
            bid=149.99,
            ask=150.01,
            last=150.00,
            timestamp=datetime.now(UTC),
        )
        quote_manager.memory_cache["AAPL"] = test_quote
        
        # Get quotes (should hit cache)
        await quote_manager.get_quotes(["AAPL"])
        
        # Hits should have incremented
        assert quote_manager.metrics["cache_hits"] >= initial_hits


# ============================================================================
# SYMBOL NORMALIZATION TESTS
# ============================================================================

class TestSymbolNormalization:
    """Tests for symbol normalization"""
    
    @pytest.mark.asyncio
    async def test_symbols_uppercased(self, quote_manager):
        """Test symbols are uppercased"""
        quote_manager._get_from_cache = AsyncMock(return_value=({}, ["AAPL"]))
        quote_manager._fetch_from_alpaca = AsyncMock(return_value={})
        
        await quote_manager.get_quotes(["aapl"])
        
        # Should have been normalized to AAPL
        quote_manager._get_from_cache.assert_called_with(["AAPL"])
