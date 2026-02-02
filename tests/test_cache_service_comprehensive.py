"""
Comprehensive tests for backend.services.cache

Targets 70%+ coverage for CacheService:
- CacheLayer configuration
- Memory cache fallback
- Cache get/set operations
- Batch operations
- Metrics tracking
- Helper functions
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pickle

import pytest

from backend.services.cache import (
    CACHE_LAYERS,
    CacheLayer,
    CacheService,
    _parse_host_port_list,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def cache_service():
    """Create a CacheService with Redis disabled for testing"""
    with patch.dict("os.environ", {"REDIS_HOST": "nonexistent"}):
        with patch("backend.services.cache.REDIS_AVAILABLE", False):
            service = CacheService()
            return service


@pytest.fixture
def cache_with_mock_redis():
    """Create a CacheService with mock Redis"""
    with patch("backend.services.cache.REDIS_AVAILABLE", True):
        with patch("backend.services.cache.redis") as mock_redis:
            mock_client = MagicMock()
            mock_redis.Redis.return_value = mock_client
            service = CacheService()
            service.redis_client = AsyncMock()
            service.redis_available = True
            return service


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestParseHostPortList:
    """Tests for _parse_host_port_list helper"""
    
    def test_parse_single_host(self):
        """Test parsing single host:port"""
        result = _parse_host_port_list("localhost:6379")
        assert result == [("localhost", 6379)]
        
    def test_parse_multiple_hosts(self):
        """Test parsing multiple hosts"""
        result = _parse_host_port_list("host1:6379,host2:6380,host3:6381")
        assert len(result) == 3
        assert result[0] == ("host1", 6379)
        assert result[1] == ("host2", 6380)
        assert result[2] == ("host3", 6381)
        
    def test_parse_empty_string(self):
        """Test parsing empty string"""
        result = _parse_host_port_list("")
        assert result == []
        
    def test_parse_with_whitespace(self):
        """Test parsing with whitespace"""
        result = _parse_host_port_list("  host1:6379 , host2:6380  ")
        assert len(result) == 2


# ============================================================================
# CACHE LAYER TESTS
# ============================================================================

class TestCacheLayer:
    """Tests for CacheLayer configuration"""
    
    def test_create_cache_layer(self):
        """Test creating a cache layer"""
        layer = CacheLayer("test", 60, "test:")
        
        assert layer.name == "test"
        assert layer.ttl == 60
        assert layer.prefix == "test:"
        
    def test_predefined_cache_layers(self):
        """Test predefined cache layers exist"""
        assert "quotes" in CACHE_LAYERS
        assert "bars" in CACHE_LAYERS
        assert "indicators" in CACHE_LAYERS
        
    def test_quotes_layer_config(self):
        """Test quotes layer configuration"""
        layer = CACHE_LAYERS["quotes"]
        
        assert layer.name == "Hot Quotes"
        assert layer.ttl == 5
        assert layer.prefix == "quote:"
        
    def test_bars_layer_config(self):
        """Test bars layer configuration"""
        layer = CACHE_LAYERS["bars"]
        
        assert layer.ttl == 60
        
    def test_indicators_layer_config(self):
        """Test indicators layer configuration"""
        layer = CACHE_LAYERS["indicators"]
        
        assert layer.ttl == 30


# ============================================================================
# CACHE SERVICE INITIALIZATION TESTS
# ============================================================================

class TestCacheServiceInit:
    """Tests for CacheService initialization"""
    
    def test_init_without_redis(self, cache_service):
        """Test initialization when Redis is not available"""
        assert cache_service.redis_available is False
        assert cache_service.memory_cache is not None
        assert "quotes" in cache_service.memory_cache
        
    def test_init_metrics(self, cache_service):
        """Test metrics initialization"""
        assert cache_service.metrics["hits"] == 0
        assert cache_service.metrics["misses"] == 0
        assert cache_service.metrics["sets"] == 0
        assert cache_service.metrics["errors"] == 0


# ============================================================================
# MEMORY CACHE TESTS
# ============================================================================

class TestMemoryCache:
    """Tests for memory cache fallback"""
    
    @pytest.mark.asyncio
    async def test_set_get_memory_cache(self, cache_service):
        """Test set and get with memory cache"""
        await cache_service.set("quotes", "AAPL", {"price": 150.0})
        
        result = await cache_service.get("quotes", "AAPL")
        
        assert result is not None
        assert result["price"] == 150.0
        
    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, cache_service):
        """Test getting non-existent key"""
        result = await cache_service.get("quotes", "NONEXISTENT")
        
        assert result is None
        assert cache_service.metrics["misses"] > 0
        
    @pytest.mark.asyncio
    async def test_cache_expiry(self, cache_service):
        """Test cache expiry"""
        # Set with very short TTL
        await cache_service.set("quotes", "EXPIRED", {"price": 100.0}, ttl=1)
        
        # Immediately check - should exist
        result = await cache_service.get("quotes", "EXPIRED")
        assert result is not None
        
        # Manually expire the entry
        cache_service.memory_cache["quotes"]["EXPIRED"] = (
            {"price": 100.0},
            datetime.now() - timedelta(seconds=1)  # Already expired
        )
        
        # Now should be None
        result = await cache_service.get("quotes", "EXPIRED")
        assert result is None
        
    @pytest.mark.asyncio
    async def test_invalid_layer(self, cache_service):
        """Test invalid layer raises error"""
        with pytest.raises(ValueError, match="Invalid cache layer"):
            await cache_service.get("invalid_layer", "key")
            
    @pytest.mark.asyncio
    async def test_set_invalid_layer(self, cache_service):
        """Test set with invalid layer raises error"""
        with pytest.raises(ValueError, match="Invalid cache layer"):
            await cache_service.set("invalid_layer", "key", "value")


# ============================================================================
# BATCH OPERATIONS TESTS
# ============================================================================

class TestBatchOperations:
    """Tests for batch cache operations"""
    
    @pytest.mark.asyncio
    async def test_get_many_empty(self, cache_service):
        """Test get_many with no cached values"""
        result = await cache_service.get_many("quotes", ["AAPL", "GOOG", "MSFT"])
        
        assert result == {}
        
    @pytest.mark.asyncio
    async def test_get_many_with_values(self, cache_service):
        """Test get_many with cached values"""
        await cache_service.set("quotes", "AAPL", {"price": 150.0})
        await cache_service.set("quotes", "GOOG", {"price": 175.0})
        
        result = await cache_service.get_many("quotes", ["AAPL", "GOOG", "MSFT"])
        
        assert "AAPL" in result
        assert "GOOG" in result
        assert "MSFT" not in result
        
    @pytest.mark.asyncio
    async def test_set_many(self, cache_service):
        """Test set_many batch operation"""
        items = {
            "AAPL": {"price": 150.0},
            "GOOG": {"price": 175.0},
            "MSFT": {"price": 400.0},
        }
        
        await cache_service.set_many("quotes", items)
        
        # Verify all were set
        for symbol, data in items.items():
            result = await cache_service.get("quotes", symbol)
            assert result is not None
            assert result["price"] == data["price"]
            
    @pytest.mark.asyncio
    async def test_get_many_invalid_layer(self, cache_service):
        """Test get_many with invalid layer"""
        with pytest.raises(ValueError, match="Invalid cache layer"):
            await cache_service.get_many("invalid", ["key"])
            
    @pytest.mark.asyncio
    async def test_set_many_invalid_layer(self, cache_service):
        """Test set_many with invalid layer"""
        with pytest.raises(ValueError, match="Invalid cache layer"):
            await cache_service.set_many("invalid", {"key": "value"})


# ============================================================================
# METRICS TESTS
# ============================================================================

class TestMetrics:
    """Tests for cache metrics"""
    
    @pytest.mark.asyncio
    async def test_hits_tracked(self, cache_service):
        """Test cache hits are tracked"""
        await cache_service.set("quotes", "AAPL", {"price": 150.0})
        await cache_service.get("quotes", "AAPL")
        
        assert cache_service.metrics["hits"] >= 1
        
    @pytest.mark.asyncio
    async def test_misses_tracked(self, cache_service):
        """Test cache misses are tracked"""
        await cache_service.get("quotes", "NONEXISTENT")
        
        assert cache_service.metrics["misses"] >= 1
        
    @pytest.mark.asyncio
    async def test_sets_tracked(self, cache_service):
        """Test cache sets are tracked"""
        await cache_service.set("quotes", "AAPL", {"price": 150.0})
        
        assert cache_service.metrics["sets"] >= 1


# ============================================================================
# DIFFERENT CACHE LAYERS TESTS
# ============================================================================

class TestCacheLayers:
    """Tests for different cache layers"""
    
    @pytest.mark.asyncio
    async def test_quotes_layer(self, cache_service):
        """Test quotes layer operations"""
        await cache_service.set("quotes", "AAPL", {"bid": 149.99, "ask": 150.01})
        result = await cache_service.get("quotes", "AAPL")
        
        assert result["bid"] == 149.99
        
    @pytest.mark.asyncio
    async def test_bars_layer(self, cache_service):
        """Test bars layer operations"""
        bar_data = {
            "open": 150.0,
            "high": 152.0,
            "low": 149.0,
            "close": 151.0,
            "volume": 1000000,
        }
        await cache_service.set("bars", "AAPL:1D", bar_data)
        result = await cache_service.get("bars", "AAPL:1D")
        
        assert result["close"] == 151.0
        
    @pytest.mark.asyncio
    async def test_indicators_layer(self, cache_service):
        """Test indicators layer operations"""
        indicator_data = {
            "rsi": 55.5,
            "sma_20": 150.0,
            "macd": 0.5,
        }
        await cache_service.set("indicators", "AAPL", indicator_data)
        result = await cache_service.get("indicators", "AAPL")
        
        assert result["rsi"] == 55.5


# ============================================================================
# TTL TESTS
# ============================================================================

class TestTTL:
    """Tests for TTL handling"""
    
    @pytest.mark.asyncio
    async def test_default_ttl_used(self, cache_service):
        """Test default TTL from layer is used"""
        await cache_service.set("quotes", "AAPL", {"price": 150.0})
        
        # Check the expiry is around 5 seconds from now (quotes TTL)
        _, expiry = cache_service.memory_cache["quotes"]["AAPL"]
        time_diff = (expiry - datetime.now()).total_seconds()
        
        assert time_diff > 0
        assert time_diff <= 5
        
    @pytest.mark.asyncio
    async def test_custom_ttl(self, cache_service):
        """Test custom TTL overrides default"""
        await cache_service.set("quotes", "AAPL", {"price": 150.0}, ttl=120)
        
        _, expiry = cache_service.memory_cache["quotes"]["AAPL"]
        time_diff = (expiry - datetime.now()).total_seconds()
        
        assert time_diff > 60  # Should be more than default 5s


# ============================================================================
# REDIS MODE TESTS
# ============================================================================

class TestRedisModes:
    """Tests for Redis connection mode configurations"""
    
    def test_redis_mode_description(self, cache_service):
        """Test Redis mode description"""
        # Without Redis
        assert "not initialized" in cache_service.redis_mode or "sync init" in cache_service.redis_mode or cache_service.redis_mode == "not initialized"


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases"""
    
    @pytest.mark.asyncio
    async def test_set_none_value(self, cache_service):
        """Test setting None value"""
        await cache_service.set("quotes", "NULL_TEST", None)
        result = await cache_service.get("quotes", "NULL_TEST")
        
        assert result is None  # None is a valid cached value
        
    @pytest.mark.asyncio
    async def test_set_complex_value(self, cache_service):
        """Test setting complex nested value"""
        complex_data = {
            "level1": {
                "level2": {
                    "data": [1, 2, 3, 4, 5],
                    "nested": {"deep": "value"},
                }
            }
        }
        
        await cache_service.set("bars", "COMPLEX", complex_data)
        result = await cache_service.get("bars", "COMPLEX")
        
        assert result["level1"]["level2"]["data"] == [1, 2, 3, 4, 5]
        
    @pytest.mark.asyncio
    async def test_overwrite_existing_key(self, cache_service):
        """Test overwriting existing cached value"""
        await cache_service.set("quotes", "AAPL", {"price": 150.0})
        await cache_service.set("quotes", "AAPL", {"price": 160.0})
        
        result = await cache_service.get("quotes", "AAPL")
        
        assert result["price"] == 160.0
