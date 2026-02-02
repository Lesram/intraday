"""
Tests for Redis High Availability support in CacheService.

Tests cover:
- Host/port parsing for Sentinel and Cluster modes
- Redis client factory function with all modes
- CacheService initialization with HA modes
- Error handling for misconfiguration
- Metrics reporting with HA mode info
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# We need to patch redis before importing cache module in some tests
# First import just the helper function which doesn't depend on redis
import backend.services.cache as cache_module
from backend.services.cache import (
    _parse_host_port_list,
    CacheService,
    get_cache_service,
    CACHE_LAYERS,
)


class TestHostPortParsing:
    """Tests for _parse_host_port_list helper function."""

    def test_parse_empty_string(self):
        """Empty string returns empty list."""
        result = _parse_host_port_list("")
        assert result == []

    def test_parse_single_host(self):
        """Single host:port pair is parsed correctly."""
        result = _parse_host_port_list("localhost:6379")
        assert result == [("localhost", 6379)]

    def test_parse_multiple_hosts(self):
        """Multiple comma-separated host:port pairs are parsed."""
        result = _parse_host_port_list("host1:6379,host2:6380,host3:6381")
        assert result == [
            ("host1", 6379),
            ("host2", 6380),
            ("host3", 6381),
        ]

    def test_parse_with_whitespace(self):
        """Whitespace around commas and colons is stripped."""
        result = _parse_host_port_list("host1:6379 , host2:6380 ,host3 : 6381")
        assert result == [
            ("host1", 6379),
            ("host2", 6380),
            ("host3", 6381),
        ]

    def test_parse_sentinel_standard_ports(self):
        """Sentinel standard port (26379) is parsed correctly."""
        result = _parse_host_port_list("sentinel1:26379,sentinel2:26379")
        assert result == [
            ("sentinel1", 26379),
            ("sentinel2", 26379),
        ]

    def test_parse_cluster_standard_ports(self):
        """Cluster standard ports (7000+) are parsed correctly."""
        result = _parse_host_port_list("node1:7000,node2:7001,node3:7002")
        assert result == [
            ("node1", 7000),
            ("node2", 7001),
            ("node3", 7002),
        ]

    def test_parse_invalid_format_skipped(self):
        """Entries without colon are skipped."""
        result = _parse_host_port_list("valid:6379,invalid,another:6380")
        assert result == [
            ("valid", 6379),
            ("another", 6380),
        ]

    def test_parse_ipv4_addresses(self):
        """IPv4 addresses are parsed correctly."""
        result = _parse_host_port_list("192.168.1.1:6379,10.0.0.1:6380")
        assert result == [
            ("192.168.1.1", 6379),
            ("10.0.0.1", 6380),
        ]


@pytest.fixture
def mock_redis_modules():
    """Fixture to mock redis modules for testing."""
    mock_redis = MagicMock()
    mock_redis.Redis = MagicMock(return_value=MagicMock())
    mock_redis.cluster = MagicMock()
    mock_redis.cluster.ClusterNode = MagicMock()
    
    mock_sentinel = MagicMock()
    mock_cluster = MagicMock()
    
    with patch.object(cache_module, 'REDIS_AVAILABLE', True):
        with patch.object(cache_module, 'REDIS_SENTINEL_AVAILABLE', True):
            with patch.object(cache_module, 'REDIS_CLUSTER_AVAILABLE', True):
                with patch.object(cache_module, 'redis', mock_redis, create=True):
                    with patch.object(cache_module, 'Sentinel', mock_sentinel, create=True):
                        with patch.object(cache_module, 'RedisCluster', mock_cluster, create=True):
                            yield {
                                'redis': mock_redis,
                                'Sentinel': mock_sentinel,
                                'RedisCluster': mock_cluster,
                            }


class TestCreateRedisClient:
    """Tests for create_redis_client factory function."""

    @pytest.mark.asyncio
    async def test_standalone_mode_default(self, mock_redis_modules):
        """Standalone mode creates standard Redis client."""
        from backend.services.cache import create_redis_client
        
        mock_client = MagicMock()
        mock_redis_modules['redis'].Redis.return_value = mock_client
        
        client, desc = await create_redis_client(
            mode="standalone",
            host="localhost",
            port=6379,
            db=0,
        )
        
        assert client == mock_client
        assert "Standalone" in desc
        assert "localhost:6379" in desc

    @pytest.mark.asyncio
    async def test_standalone_with_password(self, mock_redis_modules):
        """Standalone mode passes password to Redis client."""
        from backend.services.cache import create_redis_client
        
        await create_redis_client(
            mode="standalone",
            host="localhost",
            port=6379,
            password="secret123",
        )
        
        call_kwargs = mock_redis_modules['redis'].Redis.call_args[1]
        assert call_kwargs["password"] == "secret123"

    @pytest.mark.asyncio
    async def test_invalid_mode_raises_error(self, mock_redis_modules):
        """Invalid mode raises ValueError with helpful message."""
        from backend.services.cache import create_redis_client
        
        with pytest.raises(ValueError) as exc_info:
            await create_redis_client(mode="invalid")
        
        assert "Invalid Redis mode" in str(exc_info.value)
        assert "'standalone'" in str(exc_info.value)
        assert "'sentinel'" in str(exc_info.value)
        assert "'cluster'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_sentinel_mode_without_hosts_raises(self, mock_redis_modules):
        """Sentinel mode without hosts raises ValueError."""
        from backend.services.cache import create_redis_client
        
        with pytest.raises(ValueError) as exc_info:
            await create_redis_client(
                mode="sentinel",
                sentinel_hosts="",
            )
        
        assert "Sentinel mode requires" in str(exc_info.value)
        assert "REDIS_SENTINEL_HOSTS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_sentinel_mode_creates_sentinel_client(self, mock_redis_modules):
        """Sentinel mode creates Sentinel master client."""
        from backend.services.cache import create_redis_client
        
        mock_sentinel = MagicMock()
        mock_client = MagicMock()
        mock_sentinel.master_for.return_value = mock_client
        mock_redis_modules['Sentinel'].return_value = mock_sentinel
        
        client, desc = await create_redis_client(
            mode="sentinel",
            sentinel_hosts="sentinel1:26379,sentinel2:26379",
            sentinel_master="mymaster",
        )
        
        assert client == mock_client
        assert "Sentinel mode" in desc
        assert "mymaster" in desc

    @pytest.mark.asyncio
    async def test_sentinel_custom_master_name(self, mock_redis_modules):
        """Sentinel mode uses custom master name."""
        from backend.services.cache import create_redis_client
        
        mock_sentinel = MagicMock()
        mock_sentinel.master_for.return_value = MagicMock()
        mock_redis_modules['Sentinel'].return_value = mock_sentinel
        
        _, desc = await create_redis_client(
            mode="sentinel",
            sentinel_hosts="sentinel1:26379",
            sentinel_master="custom-master",
        )
        
        assert "custom-master" in desc
        mock_sentinel.master_for.assert_called_with(
            "custom-master",
            db=0,
            decode_responses=False,
            socket_timeout=1.0,
        )

    @pytest.mark.asyncio
    async def test_cluster_mode_without_hosts_raises(self, mock_redis_modules):
        """Cluster mode without hosts raises ValueError."""
        from backend.services.cache import create_redis_client
        
        with pytest.raises(ValueError) as exc_info:
            await create_redis_client(
                mode="cluster",
                cluster_hosts="",
            )
        
        assert "Cluster mode requires" in str(exc_info.value)
        assert "REDIS_CLUSTER_HOSTS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cluster_mode_creates_cluster_client(self, mock_redis_modules):
        """Cluster mode creates RedisCluster client."""
        from backend.services.cache import create_redis_client
        
        mock_client = MagicMock()
        mock_redis_modules['RedisCluster'].return_value = mock_client
        
        client, desc = await create_redis_client(
            mode="cluster",
            cluster_hosts="node1:7000,node2:7001",
        )
        
        assert client == mock_client
        assert "Cluster mode" in desc
        assert "node1:7000" in desc

    @pytest.mark.asyncio
    async def test_mode_case_insensitive(self, mock_redis_modules):
        """Mode parameter is case-insensitive."""
        from backend.services.cache import create_redis_client
        
        for mode in ["STANDALONE", "Standalone", "StandAlone"]:
            client, _ = await create_redis_client(mode=mode)
            assert client is not None

    @pytest.mark.asyncio
    async def test_create_redis_not_available(self):
        """ImportError when redis module not available."""
        from backend.services.cache import create_redis_client
        
        with patch.object(cache_module, 'REDIS_AVAILABLE', False):
            with pytest.raises(ImportError) as exc_info:
                await create_redis_client(mode="standalone")
            
            assert "redis.asyncio" in str(exc_info.value)


class TestCacheServiceInit:
    """Tests for CacheService initialization."""

    def test_init_creates_memory_cache(self, mock_redis_modules):
        """Init creates memory cache structures for all layers."""
        service = CacheService()
        
        assert 'quotes' in service.memory_cache
        assert 'bars' in service.memory_cache
        assert 'indicators' in service.memory_cache

    def test_init_creates_metrics(self, mock_redis_modules):
        """Init creates metrics counters."""
        service = CacheService()
        
        assert service.metrics['hits'] == 0
        assert service.metrics['misses'] == 0
        assert service.metrics['sets'] == 0
        assert service.metrics['errors'] == 0

    @pytest.mark.asyncio
    async def test_initialize_standalone_mode(self, mock_redis_modules):
        """Async initialize with standalone mode."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        
        with patch.object(cache_module, 'create_redis_client', 
                          return_value=(mock_client, "Standalone Redis at localhost:6379")):
            with patch.dict(os.environ, {"REDIS_MODE": "standalone"}, clear=False):
                service = CacheService()
                await service.initialize()
                
                assert service.redis_available is True
                assert "Standalone" in service.redis_mode

    @pytest.mark.asyncio
    async def test_initialize_sentinel_mode(self, mock_redis_modules):
        """Async initialize with sentinel mode."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        
        with patch.object(cache_module, 'create_redis_client',
                          return_value=(mock_client, "Sentinel mode (master=mymaster)")):
            env = {
                "REDIS_MODE": "sentinel",
                "REDIS_SENTINEL_HOSTS": "sentinel1:26379",
                "REDIS_SENTINEL_MASTER": "mymaster",
            }
            with patch.dict(os.environ, env, clear=False):
                service = CacheService()
                await service.initialize()
                
                assert service.redis_available is True
                assert "Sentinel" in service.redis_mode

    @pytest.mark.asyncio
    async def test_initialize_cluster_mode(self, mock_redis_modules):
        """Async initialize with cluster mode."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        
        with patch.object(cache_module, 'create_redis_client',
                          return_value=(mock_client, "Cluster mode (nodes=node1:7000)")):
            env = {
                "REDIS_MODE": "cluster",
                "REDIS_CLUSTER_HOSTS": "node1:7000,node2:7001",
            }
            with patch.dict(os.environ, env, clear=False):
                service = CacheService()
                await service.initialize()
                
                assert service.redis_available is True
                assert "Cluster" in service.redis_mode

    @pytest.mark.asyncio
    async def test_initialize_handles_connection_error(self, mock_redis_modules):
        """Initialize handles connection failures gracefully."""
        with patch.object(cache_module, 'create_redis_client',
                          side_effect=ConnectionError("Connection refused")):
            with patch.dict(os.environ, {"REDIS_MODE": "standalone"}, clear=False):
                service = CacheService()
                await service.initialize()
                
                assert service.redis_available is False

    @pytest.mark.asyncio
    async def test_initialize_handles_config_error(self, mock_redis_modules):
        """Initialize handles configuration errors gracefully."""
        with patch.object(cache_module, 'create_redis_client',
                          side_effect=ValueError("Missing sentinel hosts")):
            with patch.dict(os.environ, {"REDIS_MODE": "sentinel"}, clear=False):
                service = CacheService()
                await service.initialize()
                
                assert service.redis_available is False


class TestCacheServiceMetrics:
    """Tests for CacheService metrics with HA mode info."""

    def test_get_metrics_includes_redis_mode(self, mock_redis_modules):
        """Metrics include redis_mode field."""
        service = CacheService()
        metrics = service.get_metrics()
        
        assert 'redis_mode' in metrics
        assert 'redis_available' in metrics

    @pytest.mark.asyncio
    async def test_metrics_reflect_ha_mode(self, mock_redis_modules):
        """Metrics show HA mode after initialization."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        
        with patch.object(cache_module, 'create_redis_client',
                          return_value=(mock_client, "Sentinel mode (master=mymaster)")):
            with patch.dict(os.environ, {"REDIS_MODE": "sentinel"}, clear=False):
                service = CacheService()
                await service.initialize()
                metrics = service.get_metrics()
                
                assert "Sentinel" in metrics['redis_mode']


class TestCacheServiceOperations:
    """Tests for CacheService get/set operations with HA."""

    @pytest.mark.asyncio
    async def test_set_and_get_with_memory_fallback(self):
        """Set and get work with memory fallback when Redis unavailable."""
        with patch.object(cache_module, 'REDIS_AVAILABLE', False):
            service = CacheService()
            service.redis_available = False
            
            await service.set('quotes', 'AAPL', {'price': 150.0})
            result = await service.get('quotes', 'AAPL')
            
            assert result == {'price': 150.0}

    @pytest.mark.asyncio
    async def test_invalid_layer_raises(self):
        """Invalid cache layer raises ValueError."""
        with patch.object(cache_module, 'REDIS_AVAILABLE', False):
            service = CacheService()
            
            with pytest.raises(ValueError) as exc_info:
                await service.get('invalid_layer', 'key')
            
            assert "Invalid cache layer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_redis_error_falls_back_to_memory(self, mock_redis_modules):
        """Redis errors cause fallback to memory cache."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = ConnectionError("Lost connection")
        
        service = CacheService()
        service.redis_client = mock_client
        service.redis_available = True
        
        # Pre-populate memory cache
        from datetime import datetime, timedelta
        service.memory_cache['quotes']['AAPL'] = (
            {'price': 150.0},
            datetime.now() + timedelta(seconds=60)
        )
        
        # Should fall back to memory after Redis error
        result = await service.get('quotes', 'AAPL')
        
        assert result == {'price': 150.0}
        assert service.redis_available is False  # Marked unavailable


class TestCacheLayers:
    """Tests for cache layer configuration."""

    def test_cache_layers_defined(self):
        """All standard cache layers are defined."""
        assert 'quotes' in CACHE_LAYERS
        assert 'bars' in CACHE_LAYERS
        assert 'indicators' in CACHE_LAYERS

    def test_cache_layer_ttl_values(self):
        """Cache layers have appropriate TTL values."""
        assert CACHE_LAYERS['quotes'].ttl == 5  # Hot data, short TTL
        assert CACHE_LAYERS['bars'].ttl == 60  # Historical, longer TTL
        assert CACHE_LAYERS['indicators'].ttl == 30  # Technical indicators

    def test_cache_layer_prefixes(self):
        """Cache layers have unique prefixes."""
        prefixes = [layer.prefix for layer in CACHE_LAYERS.values()]
        assert len(prefixes) == len(set(prefixes))  # All unique


class TestGlobalCacheService:
    """Tests for global cache service singleton."""

    def test_get_cache_service_returns_same_instance(self, mock_redis_modules):
        """get_cache_service returns singleton instance."""
        # Reset global
        cache_module._cache_service = None
        
        service1 = get_cache_service()
        service2 = get_cache_service()
        
        assert service1 is service2
        
        # Cleanup
        cache_module._cache_service = None


class TestEnvironmentVariableHandling:
    """Tests for environment variable parsing."""

    @pytest.mark.asyncio
    async def test_password_from_env(self, mock_redis_modules):
        """Password is read from REDIS_PASSWORD env var."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_redis_modules['redis'].Redis.return_value = mock_client
        
        with patch.dict(os.environ, {"REDIS_PASSWORD": "secret123"}, clear=False):
            from backend.services.cache import create_redis_client
            
            await create_redis_client(
                mode="standalone",
                host="localhost",
                port=6379,
                password=os.getenv('REDIS_PASSWORD'),
            )
            
            call_kwargs = mock_redis_modules['redis'].Redis.call_args[1]
            assert call_kwargs["password"] == "secret123"

    @pytest.mark.asyncio
    async def test_default_port_parsing(self, mock_redis_modules):
        """Port is parsed correctly from env var string."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        
        with patch.object(cache_module, 'create_redis_client',
                          return_value=(mock_client, "Standalone")) as mock_create:
            with patch.dict(os.environ, {"REDIS_PORT": "6380"}, clear=False):
                service = CacheService()
                await service.initialize()
                
                # Verify port was parsed as int
                call_kwargs = mock_create.call_args[1]
                assert call_kwargs["port"] == 6380
                assert isinstance(call_kwargs["port"], int)

