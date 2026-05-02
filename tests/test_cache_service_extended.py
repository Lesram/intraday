"""
Extended tests for CacheService
Tests Redis cache, memory fallback, and cache layers
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os

from backend.services.cache import (
    CacheService,
    CacheLayer,
    CACHE_LAYERS,
    _parse_host_port_list,
)


class TestParseHostPortList:
    """Test _parse_host_port_list utility function"""
    
    def test_empty_string(self):
        """Test empty string returns empty list"""
        result = _parse_host_port_list("")
        assert result == []
        
    def test_none_like_empty(self):
        """Test None-like values"""
        result = _parse_host_port_list("")
        assert result == []
        
    def test_single_host_port(self):
        """Test single host:port pair"""
        result = _parse_host_port_list("localhost:6379")
        assert result == [("localhost", 6379)]
        
    def test_multiple_host_ports(self):
        """Test multiple host:port pairs"""
        result = _parse_host_port_list("host1:6379,host2:6380,host3:6381")
        assert result == [
            ("host1", 6379),
            ("host2", 6380),
            ("host3", 6381)
        ]
        
    def test_with_whitespace(self):
        """Test handles whitespace"""
        result = _parse_host_port_list(" host1:6379 , host2:6380 ")
        assert result == [
            ("host1", 6379),
            ("host2", 6380)
        ]


class TestCacheLayer:
    """Test CacheLayer configuration class"""
    
    def test_cache_layer_creation(self):
        """Test creating a cache layer"""
        layer = CacheLayer("Test Layer", 10, "test:")
        
        assert layer.name == "Test Layer"
        assert layer.ttl == 10
        assert layer.prefix == "test:"
        
    def test_predefined_layers(self):
        """Test predefined cache layers"""
        assert 'quotes' in CACHE_LAYERS
        assert 'bars' in CACHE_LAYERS
        assert 'indicators' in CACHE_LAYERS
        
        # Check quotes layer config
        assert CACHE_LAYERS['quotes'].ttl == 5
        assert CACHE_LAYERS['quotes'].prefix == 'quote:'
        
        # Check bars layer config
        assert CACHE_LAYERS['bars'].ttl == 60
        assert CACHE_LAYERS['bars'].prefix == 'bars:'
        
        # Check indicators layer config
        assert CACHE_LAYERS['indicators'].ttl == 30
        assert CACHE_LAYERS['indicators'].prefix == 'indicators:'


class TestCacheServiceInit:
    """Test CacheService initialization"""
    
    @patch.dict(os.environ, {}, clear=True)
    @patch("backend.services.cache.REDIS_AVAILABLE", False)
    def test_init_without_redis(self):
        """Test initialization when Redis not available"""
        service = CacheService()
        
        assert service.redis_available == False
        assert 'quotes' in service.memory_cache
        assert 'bars' in service.memory_cache
        assert 'indicators' in service.memory_cache
        
    def test_metrics_initialized(self):
        """Test metrics are initialized"""
        with patch("backend.services.cache.REDIS_AVAILABLE", False):
            service = CacheService()
        
        assert service.metrics['hits'] == 0
        assert service.metrics['misses'] == 0
        assert service.metrics['sets'] == 0
        assert service.metrics['errors'] == 0


class TestCacheServiceOperations:
    """Test CacheService get/set operations"""
    
    @pytest.fixture
    def cache_service(self):
        """Create cache service with mocked Redis"""
        with patch("backend.services.cache.REDIS_AVAILABLE", False):
            service = CacheService()
        return service
        
    @pytest.mark.asyncio
    async def test_memory_cache_set_and_get(self, cache_service):
        """Test memory cache set and get"""
        test_data = {"price": 150.0, "volume": 1000}
        
        await cache_service.set('quotes', 'AAPL', test_data)
        result = await cache_service.get('quotes', 'AAPL')
        
        assert result == test_data
        
    @pytest.mark.asyncio
    async def test_memory_cache_miss(self, cache_service):
        """Test memory cache miss returns None"""
        result = await cache_service.get('quotes', 'NONEXISTENT')
        
        assert result is None
        
    @pytest.mark.asyncio
    async def test_memory_cache_expired(self, cache_service):
        """Test expired memory cache returns None"""
        # V4 Z-R-2 (2026-05-02): production wave-8d K-8 made cache TTL
        # tz-aware UTC; fixtures must match.
        from datetime import UTC, datetime, timedelta

        # Manually insert expired data
        cache_service.memory_cache['quotes']['EXPIRED'] = (
            {"price": 100},
            datetime.now(UTC) - timedelta(seconds=100)  # Expired
        )
        
        result = await cache_service.get('quotes', 'EXPIRED')
        
        # Should return None for expired data
        assert result is None
        
    @pytest.mark.asyncio
    async def test_metrics_update_on_hit(self, cache_service):
        """Test metrics updated on cache hit"""
        initial_hits = cache_service.metrics['hits']
        
        await cache_service.set('quotes', 'TEST', {"data": 1})
        await cache_service.get('quotes', 'TEST')
        
        assert cache_service.metrics['hits'] > initial_hits
        
    @pytest.mark.asyncio
    async def test_metrics_update_on_miss(self, cache_service):
        """Test metrics updated on cache miss"""
        initial_misses = cache_service.metrics['misses']
        
        await cache_service.get('quotes', 'MISSING_KEY')
        
        assert cache_service.metrics['misses'] > initial_misses


class TestCacheServiceDelete:
    """Test cache delete operations"""
    
    @pytest.fixture
    def cache_service(self):
        with patch("backend.services.cache.REDIS_AVAILABLE", False):
            service = CacheService()
        return service
        
    @pytest.mark.asyncio
    async def test_delete_existing_key(self, cache_service):
        """Test deleting an existing key"""
        await cache_service.set('quotes', 'DELETE_ME', {"data": 1})
        
        # Verify it exists
        result = await cache_service.get('quotes', 'DELETE_ME')
        assert result is not None
        
        # Delete it
        await cache_service.delete('quotes', 'DELETE_ME')
        
        # Verify it's gone
        result = await cache_service.get('quotes', 'DELETE_ME')
        assert result is None
        
    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, cache_service):
        """Test deleting a nonexistent key doesn't raise"""
        # Should not raise
        await cache_service.delete('quotes', 'NONEXISTENT')


class TestCacheServiceClear:
    """Test cache clear operations"""
    
    @pytest.fixture
    def cache_service(self):
        with patch("backend.services.cache.REDIS_AVAILABLE", False):
            service = CacheService()
        return service
        
    @pytest.mark.asyncio
    async def test_clear_layer(self, cache_service):
        """Test clearing a specific layer"""
        await cache_service.set('quotes', 'KEY1', {"data": 1})
        await cache_service.set('quotes', 'KEY2', {"data": 2})
        await cache_service.set('bars', 'KEY1', {"data": 3})
        
        # Clear quotes layer
        await cache_service.clear_layer('quotes')
        
        # Quotes should be gone
        assert await cache_service.get('quotes', 'KEY1') is None
        assert await cache_service.get('quotes', 'KEY2') is None
        
        # Bars should remain
        assert await cache_service.get('bars', 'KEY1') is not None


class TestCacheServiceWithMockedRedis:
    """Test CacheService behavior patterns (without actual Redis)"""
    
    def test_redis_available_flag(self):
        """Test redis_available flag behavior"""
        with patch("backend.services.cache.REDIS_AVAILABLE", False):
            service = CacheService()
            
        # Without Redis, should use memory cache
        assert service.redis_available == False
        
    def test_memory_fallback_active(self):
        """Test memory cache is used when Redis unavailable"""
        with patch("backend.services.cache.REDIS_AVAILABLE", False):
            service = CacheService()
            
        assert 'quotes' in service.memory_cache
        assert 'bars' in service.memory_cache
        assert 'indicators' in service.memory_cache
        
    def test_redis_mode_not_initialized(self):
        """Test redis_mode shows status correctly"""
        with patch("backend.services.cache.REDIS_AVAILABLE", False):
            service = CacheService()
            
        # Should indicate not using Redis
        assert 'not' in service.redis_mode.lower() or service.redis_mode == ""


class TestCacheLayerValidation:
    """Test cache layer validation"""
    
    @pytest.fixture
    def cache_service(self):
        with patch("backend.services.cache.REDIS_AVAILABLE", False):
            service = CacheService()
        return service
        
    @pytest.mark.asyncio
    async def test_invalid_layer_raises(self, cache_service):
        """Test get with invalid layer raises ValueError"""
        with pytest.raises(ValueError, match="Invalid cache layer"):
            await cache_service.get('invalid_layer', 'KEY')
        
    @pytest.mark.asyncio
    async def test_valid_layers(self, cache_service):
        """Test all valid layers work"""
        for layer in ['quotes', 'bars', 'indicators']:
            await cache_service.set(layer, 'TEST', {"data": layer})
            result = await cache_service.get(layer, 'TEST')
            assert result == {"data": layer}
