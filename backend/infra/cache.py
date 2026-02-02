"""
In-Memory Cache for Hot Data

Provides TTL-based caching for frequently accessed data like:
- Portfolio summaries
- Position data
- Account balances
- Strategy configurations

Uses LRU eviction and automatic expiration for memory efficiency.
"""

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """Cache entry with value and metadata."""
    value: T
    created_at: float = field(default_factory=time.time)
    ttl: float = 60.0  # Default 60 seconds

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl


class MemoryCache:
    """
    Thread-safe in-memory cache with TTL and LRU eviction.

    Features:
    - Configurable TTL per entry
    - LRU eviction when max size exceeded
    - Async-safe with locks
    - Automatic expired entry cleanup
    - Cache statistics for monitoring

    Usage:
        cache = MemoryCache(max_size=1000, default_ttl=60)
        await cache.set("portfolio:user123", portfolio_data, ttl=30)
        data = await cache.get("portfolio:user123")
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float = 60.0,
        cleanup_interval: float = 300.0,  # 5 minutes
    ):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
        }
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info(f"MemoryCache started: max_size={self.max_size}, default_ttl={self.default_ttl}s")

    async def stop(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("MemoryCache stopped")

    async def get(self, key: str) -> Any | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats["misses"] += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._stats["misses"] += 1
                self._stats["expirations"] += 1
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._stats["hits"] += 1
            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
    ) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if not specified)
        """
        async with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
                self._stats["evictions"] += 1

            self._cache[key] = CacheEntry(
                value=value,
                ttl=ttl if ttl is not None else self.default_ttl,
            )

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern (simple prefix match).

        Args:
            pattern: Key prefix to match

        Returns:
            Number of keys deleted
        """
        async with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: float | None = None,
    ) -> Any:
        """
        Get value from cache or compute and cache it.

        Args:
            key: Cache key
            factory: Callable to compute value if not cached (can be async)
            ttl: Time-to-live in seconds

        Returns:
            Cached or computed value
        """
        value = await self.get(key)
        if value is not None:
            return value

        # Compute value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()

        await self.set(key, value, ttl)
        return value

    async def clear(self) -> int:
        """
        Clear all entries from cache.

        Returns:
            Number of entries cleared
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        return {
            **self._stats,
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate": self._stats["hits"] / total if total > 0 else 0,
        }

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

    async def _cleanup_expired(self) -> int:
        """Remove expired entries."""
        async with self._lock:
            expired_keys = [
                k for k, v in self._cache.items()
                if v.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
                self._stats["expirations"] += 1

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

            return len(expired_keys)


# Global cache instance for hot data
_hot_data_cache: MemoryCache | None = None


def get_hot_data_cache() -> MemoryCache:
    """Get or create the global hot data cache."""
    global _hot_data_cache
    if _hot_data_cache is None:
        _hot_data_cache = MemoryCache(
            max_size=5000,
            default_ttl=30.0,  # 30 second default for market data
            cleanup_interval=60.0,
        )
    return _hot_data_cache


# Cache key generators
def portfolio_cache_key(user_id: str) -> str:
    """Generate cache key for portfolio data."""
    return f"portfolio:{user_id}"


def positions_cache_key(user_id: str) -> str:
    """Generate cache key for positions data."""
    return f"positions:{user_id}"


def account_cache_key(user_id: str) -> str:
    """Generate cache key for account data."""
    return f"account:{user_id}"


def strategy_cache_key(strategy_id: str) -> str:
    """Generate cache key for strategy data."""
    return f"strategy:{strategy_id}"
