"""
Multi-Layer Redis Cache Service

Provides high-performance caching for:
- L1: Hot quotes (5 second TTL)
- L2: Historical bars (1 minute TTL)
- L3: Indicators (30 second TTL)

Features:
- Connection pooling (50 connections)
- Automatic serialization/deserialization
- Fallback to memory cache if Redis unavailable
- Performance metrics
- High Availability support:
  - Standalone: Single Redis server
  - Sentinel: Redis Sentinel for automatic failover
  - Cluster: Redis Cluster for horizontal scaling

Security Note:
    Cache uses pickle for serialization of internal data only.
    Cache data is ephemeral (5-60s TTL) and only stores numeric/dict data.
    For persistent model storage, use backend.utils.secure_pickle instead.
"""

from datetime import datetime, timedelta
import logging
import os
import pickle
from typing import Any

try:
    import redis.asyncio as redis
    from redis.asyncio.cluster import RedisCluster
    from redis.asyncio.sentinel import Sentinel

    from backend.utils.secure_pickle import secure_loads
    REDIS_AVAILABLE = True
    REDIS_SENTINEL_AVAILABLE = True
    REDIS_CLUSTER_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    REDIS_SENTINEL_AVAILABLE = False
    REDIS_CLUSTER_AVAILABLE = False

logger = logging.getLogger(__name__)


def _parse_host_port_list(hosts_str: str) -> list[tuple[str, int]]:
    """
    Parse comma-separated host:port pairs.
    
    Args:
        hosts_str: e.g., 'host1:6379,host2:6380'
        
    Returns:
        List of (host, port) tuples
    """
    if not hosts_str:
        return []

    result = []
    for pair in hosts_str.split(','):
        pair = pair.strip()
        if ':' in pair:
            host, port = pair.rsplit(':', 1)
            result.append((host.strip(), int(port.strip())))
    return result


async def create_redis_client(
    mode: str = "standalone",
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: str | None = None,
    sentinel_hosts: str = "",
    sentinel_master: str = "mymaster",
    cluster_hosts: str = "",
    max_connections: int = 50,
    socket_timeout: float = 1.0,
    socket_connect_timeout: float = 1.0,
    retry_on_timeout: bool = True,
) -> tuple[Any, str]:
    """
    Create Redis client based on the configured mode.
    
    Supported modes:
    - standalone: Single Redis server connection
    - sentinel: Redis Sentinel for automatic master/slave failover
    - cluster: Redis Cluster for horizontal scaling
    
    Args:
        mode: 'standalone', 'sentinel', or 'cluster'
        host: Redis host (for standalone mode)
        port: Redis port (for standalone mode)
        db: Redis database number (not used in cluster mode)
        password: Redis password (optional)
        sentinel_hosts: Comma-separated sentinel host:port pairs
        sentinel_master: Sentinel master name
        cluster_hosts: Comma-separated cluster node host:port pairs
        max_connections: Maximum connection pool size
        socket_timeout: Socket timeout in seconds
        socket_connect_timeout: Connection timeout in seconds
        retry_on_timeout: Whether to retry on timeout
        
    Returns:
        Tuple of (redis_client, mode_description)
        
    Raises:
        ValueError: If mode is invalid or required configuration is missing
    """
    if not REDIS_AVAILABLE:
        raise ImportError("redis.asyncio module not available")

    mode = mode.lower()
    connection_kwargs = {
        "decode_responses": False,
        "socket_timeout": socket_timeout,
        "socket_connect_timeout": socket_connect_timeout,
        "max_connections": max_connections,
        "retry_on_timeout": retry_on_timeout,
    }

    if password:
        connection_kwargs["password"] = password

    if mode == "standalone":
        # Simple single-server connection
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            **connection_kwargs
        )
        return client, f"Standalone Redis at {host}:{port} (db={db})"

    elif mode == "sentinel":
        if not REDIS_SENTINEL_AVAILABLE:
            raise ImportError("Redis Sentinel support not available")

        sentinel_nodes = _parse_host_port_list(sentinel_hosts)
        if not sentinel_nodes:
            raise ValueError(
                "Redis Sentinel mode requires at least one sentinel host. "
                "Set REDIS_SENTINEL_HOSTS env var (e.g., 'sentinel1:26379,sentinel2:26379')"
            )

        sentinel = Sentinel(
            sentinels=sentinel_nodes,
            socket_timeout=socket_timeout,
            password=password,
        )

        # Get master client from Sentinel
        client = sentinel.master_for(
            sentinel_master,
            db=db,
            decode_responses=False,
            socket_timeout=socket_timeout,
        )

        sentinel_desc = ",".join(f"{h}:{p}" for h, p in sentinel_nodes)
        return client, f"Sentinel mode (master={sentinel_master}, sentinels={sentinel_desc})"

    elif mode == "cluster":
        if not REDIS_CLUSTER_AVAILABLE:
            raise ImportError("Redis Cluster support not available")

        cluster_nodes = _parse_host_port_list(cluster_hosts)
        if not cluster_nodes:
            raise ValueError(
                "Redis Cluster mode requires at least one cluster node. "
                "Set REDIS_CLUSTER_HOSTS env var (e.g., 'node1:7000,node2:7001')"
            )

        # Build startup nodes for cluster
        startup_nodes = [
            redis.cluster.ClusterNode(host=h, port=p)
            for h, p in cluster_nodes
        ]

        client = RedisCluster(
            startup_nodes=startup_nodes,
            password=password,
            decode_responses=False,
            socket_timeout=socket_timeout,
            retry_on_timeout=retry_on_timeout,
        )

        cluster_desc = ",".join(f"{h}:{p}" for h, p in cluster_nodes)
        return client, f"Cluster mode (nodes={cluster_desc})"

    else:
        raise ValueError(
            f"Invalid Redis mode '{mode}'. "
            "Must be 'standalone', 'sentinel', or 'cluster'"
        )


class CacheLayer:
    """Cache layer configuration"""
    def __init__(self, name: str, ttl_seconds: int, prefix: str):
        self.name = name
        self.ttl = ttl_seconds
        self.prefix = prefix


# Cache layers
CACHE_LAYERS = {
    'quotes': CacheLayer('Hot Quotes', 5, 'quote:'),
    'bars': CacheLayer('Historical Bars', 60, 'bars:'),
    'indicators': CacheLayer('Technical Indicators', 30, 'indicators:')
}


class CacheService:
    """
    High-performance multi-layer cache service
    
    Supports multiple Redis deployment modes:
    - Standalone: Single Redis server (default)
    - Sentinel: Automatic failover with Redis Sentinel
    - Cluster: Horizontal scaling with Redis Cluster

    Usage:
        cache = CacheService()
        await cache.initialize()  # Initialize async Redis client
        await cache.set('quotes', 'AAPL', quote_data, ttl=5)
        data = await cache.get('quotes', 'AAPL')
    """

    def __init__(self):
        """Initialize cache service (sync part only)"""
        self.redis_client = None
        self.redis_available = False
        self.redis_mode = "not initialized"

        # Memory cache (fallback)
        self.memory_cache: dict[str, dict[str, tuple]] = {
            'quotes': {},
            'bars': {},
            'indicators': {}
        }

        # Metrics
        self.metrics = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'errors': 0
        }

        # Attempt sync initialization for backward compatibility
        self._init_sync_fallback()

    def _init_sync_fallback(self):
        """
        Synchronous fallback initialization for backward compatibility.
        
        This creates a standalone connection if async initialization
        hasn't been called yet. For HA modes, use initialize() instead.
        """
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=os.getenv('REDIS_HOST', 'localhost'),
                    port=int(os.getenv('REDIS_PORT', '6379')),
                    db=int(os.getenv('REDIS_DB', '0')),
                    password=os.getenv('REDIS_PASSWORD') or None,
                    decode_responses=False,
                    socket_timeout=1,
                    socket_connect_timeout=1,
                    max_connections=50,
                    retry_on_timeout=True
                )
                self.redis_available = True
                self.redis_mode = "standalone (sync init)"
                logger.info("Redis cache service initialized (standalone mode)")
            except Exception as e:
                logger.warning(f"Redis sync initialization failed: {e}. Using memory cache only.")
                self.redis_available = False
        else:
            logger.warning("Redis module not available. Using memory cache only.")

    async def initialize(self):
        """
        Async initialization for Redis HA modes.
        
        Call this during application startup for full HA support:
        
        ```python
        cache = get_cache_service()
        await cache.initialize()
        ```
        
        Environment variables:
        - REDIS_MODE: 'standalone', 'sentinel', or 'cluster'
        - REDIS_HOST: Redis host (standalone mode)
        - REDIS_PORT: Redis port (standalone mode)
        - REDIS_DB: Redis database number
        - REDIS_PASSWORD: Redis password (optional)
        - REDIS_SENTINEL_HOSTS: 'host1:26379,host2:26379' (sentinel mode)
        - REDIS_SENTINEL_MASTER: Master name (sentinel mode, default: 'mymaster')
        - REDIS_CLUSTER_HOSTS: 'node1:7000,node2:7001' (cluster mode)
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis module not available. Using memory cache only.")
            return

        mode = os.getenv('REDIS_MODE', 'standalone').lower()

        try:
            self.redis_client, mode_desc = await create_redis_client(
                mode=mode,
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', '6379')),
                db=int(os.getenv('REDIS_DB', '0')),
                password=os.getenv('REDIS_PASSWORD') or None,
                sentinel_hosts=os.getenv('REDIS_SENTINEL_HOSTS', ''),
                sentinel_master=os.getenv('REDIS_SENTINEL_MASTER', 'mymaster'),
                cluster_hosts=os.getenv('REDIS_CLUSTER_HOSTS', ''),
                max_connections=50,
                socket_timeout=1.0,
                socket_connect_timeout=1.0,
                retry_on_timeout=True,
            )

            # Test connection
            await self.redis_client.ping()

            self.redis_available = True
            self.redis_mode = mode_desc
            logger.info(f"Redis cache service initialized: {mode_desc}")

        except ValueError as e:
            logger.error(f"Redis configuration error: {e}")
            self.redis_available = False
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}. Using memory cache only.")
            self.redis_available = False

    async def get(self, layer: str, key: str) -> Any | None:
        """
        Get value from cache

        Args:
            layer: Cache layer ('quotes', 'bars', 'indicators')
            key: Cache key (e.g., 'AAPL', 'AAPL:1D:20231201')

        Returns:
            Cached value or None
        """
        if layer not in CACHE_LAYERS:
            raise ValueError(f"Invalid cache layer: {layer}")

        cache_layer = CACHE_LAYERS[layer]
        full_key = f"{cache_layer.prefix}{key}"

        # Try Redis first
        if self.redis_available:
            try:
                data = await self.redis_client.get(full_key)
                if data:
                    self.metrics['hits'] += 1
                    return secure_loads(data, allow_unsigned=True)
                else:
                    self.metrics['misses'] += 1
                    return None
            except Exception as e:
                logger.warning(f"Redis get error for {full_key}: {e}")
                self.metrics['errors'] += 1
                self.redis_available = False  # Fallback to memory

        # Fallback to memory cache
        if key in self.memory_cache[layer]:
            value, expiry = self.memory_cache[layer][key]
            if datetime.now() < expiry:
                self.metrics['hits'] += 1
                return value
            else:
                # Expired
                del self.memory_cache[layer][key]

        self.metrics['misses'] += 1
        return None

    async def get_many(self, layer: str, keys: list[str]) -> dict[str, Any]:
        """
        Get multiple values from cache (batch operation)

        Args:
            layer: Cache layer
            keys: List of cache keys

        Returns:
            Dictionary {key: value} for found keys
        """
        if layer not in CACHE_LAYERS:
            raise ValueError(f"Invalid cache layer: {layer}")

        cache_layer = CACHE_LAYERS[layer]
        full_keys = [f"{cache_layer.prefix}{key}" for key in keys]

        results = {}

        # Try Redis first
        if self.redis_available:
            try:
                pipeline = self.redis_client.pipeline()
                for full_key in full_keys:
                    pipeline.get(full_key)

                values = await pipeline.execute()

                for key, data in zip(keys, values, strict=False):
                    if data:
                        results[key] = secure_loads(data, allow_unsigned=True)
                        self.metrics['hits'] += 1
                    else:
                        self.metrics['misses'] += 1

                return results

            except Exception as e:
                logger.warning(f"Redis get_many error: {e}")
                self.metrics['errors'] += 1
                self.redis_available = False

        # Fallback to memory cache
        for key in keys:
            if key in self.memory_cache[layer]:
                value, expiry = self.memory_cache[layer][key]
                if datetime.now() < expiry:
                    results[key] = value
                    self.metrics['hits'] += 1
                else:
                    del self.memory_cache[layer][key]
                    self.metrics['misses'] += 1
            else:
                self.metrics['misses'] += 1

        return results

    async def set(self, layer: str, key: str, value: Any, ttl: int | None = None):
        """
        Set value in cache

        Args:
            layer: Cache layer
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses layer default if None)
        """
        if layer not in CACHE_LAYERS:
            raise ValueError(f"Invalid cache layer: {layer}")

        cache_layer = CACHE_LAYERS[layer]
        full_key = f"{cache_layer.prefix}{key}"
        ttl = ttl or cache_layer.ttl

        # Store in Redis
        if self.redis_available:
            try:
                serialized = pickle.dumps(value)
                await self.redis_client.setex(full_key, ttl, serialized)
                self.metrics['sets'] += 1
            except Exception as e:
                logger.warning(f"Redis set error for {full_key}: {e}")
                self.metrics['errors'] += 1
                self.redis_available = False

        # Always store in memory cache
        expiry = datetime.now() + timedelta(seconds=ttl)
        self.memory_cache[layer][key] = (value, expiry)
        self.metrics['sets'] += 1

    async def set_many(self, layer: str, items: dict[str, Any], ttl: int | None = None):
        """
        Set multiple values in cache (batch operation)

        Args:
            layer: Cache layer
            items: Dictionary {key: value}
            ttl: Time-to-live in seconds
        """
        if layer not in CACHE_LAYERS:
            raise ValueError(f"Invalid cache layer: {layer}")

        cache_layer = CACHE_LAYERS[layer]
        ttl = ttl or cache_layer.ttl

        # Store in Redis
        if self.redis_available:
            try:
                pipeline = self.redis_client.pipeline()
                for key, value in items.items():
                    full_key = f"{cache_layer.prefix}{key}"
                    serialized = pickle.dumps(value)
                    pipeline.setex(full_key, ttl, serialized)

                await pipeline.execute()
                self.metrics['sets'] += len(items)
            except Exception as e:
                logger.warning(f"Redis set_many error: {e}")
                self.metrics['errors'] += 1
                self.redis_available = False

        # Store in memory cache
        expiry = datetime.now() + timedelta(seconds=ttl)
        for key, value in items.items():
            self.memory_cache[layer][key] = (value, expiry)
        self.metrics['sets'] += len(items)

    async def delete(self, layer: str, key: str):
        """Delete key from cache"""
        if layer not in CACHE_LAYERS:
            raise ValueError(f"Invalid cache layer: {layer}")

        cache_layer = CACHE_LAYERS[layer]
        full_key = f"{cache_layer.prefix}{key}"

        # Delete from Redis
        if self.redis_available:
            try:
                await self.redis_client.delete(full_key)
            except Exception as e:
                logger.warning(f"Redis delete error for {full_key}: {e}")

        # Delete from memory
        self.memory_cache[layer].pop(key, None)

    async def clear_layer(self, layer: str):
        """Clear entire cache layer"""
        if layer not in CACHE_LAYERS:
            raise ValueError(f"Invalid cache layer: {layer}")

        cache_layer = CACHE_LAYERS[layer]

        # Clear Redis
        if self.redis_available:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor,
                        match=f"{cache_layer.prefix}*",
                        count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Redis clear_layer error: {e}")

        # Clear memory
        self.memory_cache[layer].clear()
        logger.info(f"Cleared cache layer: {layer}")

    def get_metrics(self) -> dict:
        """Get cache performance metrics"""
        total = self.metrics['hits'] + self.metrics['misses']
        hit_rate = self.metrics['hits'] / total if total > 0 else 0

        return {
            'hit_rate': hit_rate,
            'hits': self.metrics['hits'],
            'misses': self.metrics['misses'],
            'sets': self.metrics['sets'],
            'errors': self.metrics['errors'],
            'redis_available': self.redis_available,
            'redis_mode': self.redis_mode
        }

    async def close(self):
        """Cleanup resources"""
        if self.redis_client:
            await self.redis_client.close()


# Global instance
_cache_service = None

def get_cache_service() -> CacheService:
    """Get global CacheService instance"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
